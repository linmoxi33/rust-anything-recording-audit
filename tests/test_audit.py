import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin", "rust-anything-recording-audit")
CASES = os.path.join(ROOT, "examples", "in", "cases.jsonl")
PROBLEM = os.path.join(ROOT, "examples", "in", "problem.jsonl")


def run(*args):
    p = subprocess.run(
        [sys.executable, BIN] + list(args), capture_output=True, text=True, timeout=60
    )
    return p.returncode, p.stdout, p.stderr


def write_tmp(content):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def report(*args):
    rc, out, _ = run("--json", *args)
    return rc, json.loads(out)


class BehaviorTests(unittest.TestCase):
    def test_clean_recording_exits_zero(self):
        rc, out, _ = run(CASES)
        self.assertEqual(rc, 0)
        self.assertIn("findings: 0 error, 0 warn", out)

    def test_effective_case_count_on_real_excerpt(self):
        rc, rep = report(CASES)
        self.assertEqual(rc, 0)
        self.assertEqual(rep["records"], 80)
        self.assertEqual(rep["effective_cases"], 80)
        self.assertEqual(rep["duplicate_cases"], 0)
        self.assertEqual(rep["functions"], 1)

    def test_json_output_is_parseable_and_stable(self):
        rc1, out1, _ = run("--json", CASES)
        rc2, out2, _ = run("--json", CASES)
        self.assertEqual(json.loads(out1), json.loads(out2))
        self.assertEqual(rc1, rc2)

    def test_problem_fixture_exit_one_and_counts(self):
        rc, rep = report(PROBLEM)
        self.assertEqual(rc, 1)
        self.assertEqual(rep["duplicate_cases"], 1)
        codes = {f["code"] for f in rep["findings"]}
        self.assertIn("contradictory_cases", codes)
        self.assertIn("constant_output", codes)
        self.assertIn("wildcard_assertion", codes)

    def test_contradiction_is_error_not_just_duplicate(self):
        rc, rep = report(PROBLEM)
        errs = [f for f in rep["findings"] if f["severity"] == "error"]
        self.assertTrue(any(f["code"] == "contradictory_cases" for f in errs))

    def test_parse_error_reports_real_line_number(self):
        path = write_tmp(
            '{"fn":"f","args":[1],"ok":1}\n'
            '{"fn":"f","args":[2],"ok":2}\n'
            'not json at all\n'
        )
        try:
            rc, rep = report(path)
        finally:
            os.unlink(path)
        self.assertEqual(rc, 1)
        hit = [f for f in rep["findings"] if f["code"] == "parse_error"]
        self.assertEqual(hit[0]["line"], 3)

    def test_missing_result_arm(self):
        path = write_tmp('{"fn":"f","args":[1]}\n{"fn":"g","args":[1],"ok":1}\n')
        try:
            rc, rep = report(path)
        finally:
            os.unlink(path)
        self.assertEqual(rc, 1)
        self.assertIn("missing_result", {f["code"] for f in rep["findings"]})

    def test_both_arms_is_error(self):
        path = write_tmp('{"fn":"f","args":[1],"ok":1,"error":"x"}\n')
        try:
            rc, rep = report(path)
        finally:
            os.unlink(path)
        self.assertEqual(rc, 1)
        self.assertEqual(rep["summary"]["error"], 1)

    def test_no_error_cases_warns(self):
        path = write_tmp('{"fn":"f","args":[1],"ok":1}\n{"fn":"f","args":[2],"ok":2}\n')
        try:
            rc, rep = report(path)
        finally:
            os.unlink(path)
        self.assertEqual(rc, 1)
        self.assertIn("missing_error_cases", {f["code"] for f in rep["findings"]})

    def test_only_error_cases_warns(self):
        path = write_tmp('{"fn":"f","args":[1],"error":"boom"}\n')
        try:
            rc, rep = report(path)
        finally:
            os.unlink(path)
        self.assertIn("missing_ok_cases", {f["code"] for f in rep["findings"]})

    def test_null_only_arguments_warn(self):
        path = write_tmp(
            '{"fn":"f","args":[null],"ok":1}\n{"fn":"f","args":[null,2],"error":"x"}\n'
        )
        try:
            rc, rep = report(path)
        finally:
            os.unlink(path)
        self.assertEqual(rc, 1)
        self.assertIn("null_only_args", {f["code"] for f in rep["findings"]})

    def test_min_cases_flag_raises_exit_code(self):
        path = write_tmp('{"fn":"f","args":[1],"ok":1}\n{"fn":"f","args":[2],"error":"x"}\n')
        try:
            rc0, rep0 = report(path)
            rc1, rep1 = report("--min-cases", "3", path)
        finally:
            os.unlink(path)
        self.assertEqual(rc0, 0)
        self.assertEqual(rc1, 1)
        self.assertIn("thin_recording", {f["code"] for f in rep1["findings"]})
        self.assertEqual(rep0["summary"]["total"], 0)

    def test_coverage_flags_on_real_non_ascii_data(self):
        rc, rep = report(CASES)
        cov = rep["coverage"]["normalize"]
        self.assertTrue(cov["non_ascii"])
        self.assertTrue(cov["empty_input"])
        self.assertEqual(cov["ok"], 66)
        self.assertEqual(cov["error"], 14)


class InputErrorTests(unittest.TestCase):
    def test_missing_file_is_exit_two(self):
        rc, out, err = run("/tmp/definitely-not-here-12345.jsonl")
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", err)

    def test_empty_recording_is_exit_two(self):
        path = write_tmp("\n\n")
        try:
            rc, out, err = run(path)
        finally:
            os.unlink(path)
        self.assertEqual(rc, 2)
        self.assertIn("no valid cases", err)

    def test_bad_flag_is_exit_two(self):
        rc, out, err = run("--min-cases", "-1", CASES)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()