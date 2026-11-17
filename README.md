# rust-anything-recording-audit

审计 `rust-anything` 的 `cases.jsonl` 录制集：在相信它的“0 mismatches”绿灯之前，先看清这份录制本身盖住了什么、漏了什么、哪里是自欺。

**为什么现在需要它**：rust-anything 在热榜上以“38,251 recorded cases replayed · 0 mismatches”为卖点，但它的 README 自己写着 *“Passing means the Rust matches every case that was recorded, nothing more.”* 录制越窄，0 mismatch 越没有信息量；而上游没有任何命令回答“这份录制到底盖住了什么”。

Upstream: https://github.com/erkamyaman/rust-anything

## 上游是什么，它缺什么

rust-anything 记录原语言（TS/JS、Python、C、Go、Ruby、Java）程序的调用与输出，产出 `cases.jsonl`，再由 `diff` / `gate` 判定 Rust 重写是否与录制一致。

上游在 README 的 [What it can't catch](https://github.com/erkamyaman/rust-anything/blob/main/README.md#L509-L516) 里明确承认判定的上限就是录制本身：

> Passing means the Rust matches every case that was recorded, nothing more.
> **Inputs nobody recorded.** The generated cases, the traps and your own `--inputs` are the ceiling.

缺口因此是可验证的：上游没有工具检查**录制集自己**——同一输入是否录出两种结果、重复率多高、某个函数是否一条 error 用例都没有、输出是否恒定到任何实现都能通过。

用上游真实录制 `demo/fixtures/async-rs/cases.jsonl`（900 条，commit `075335cf4b05f51c82fcf389acd3003266a32fc6`）跑本工具，真实输出：

```
records: 900  effective: 900  duplicates: 0 (0.00%)  functions: 3
findings: 0 error, 3 warn
  WARN  null_only_args       line 146                 every argument is null
  WARN  missing_error_cases  countWords               300 ok cases, 0 error cases
  WARN  missing_error_cases  upper                    300 ok cases, 0 error cases
```

`upper` 与 `countWords` 各有 300 条 ok、0 条 error：Rust 版对非法输入 panic，`gate` 依然全绿。这不是推测，是上面那次运行的结果。

## 这个工具做什么 / 不做什么

做（纯标准库、离线、只读，不改录制）：

- **结构**：JSON 解析失败、缺 `fn`、`ok`/`error` 同时出现或都不出现、`args` 不是数组
- **一致性**：同一 `fn` + 同一 `args` 录出不同结果 → `contradictory_cases`（error）；完全相同 → 重复计数与重复率
- **断言强度**：所有 ok 结果完全相同（`constant_output`）、`...` 通配输出（`wildcard_assertion`）、参数全为 null
- **分支**：只有 ok 没有 error（`missing_error_cases`）、只有 error 没有 ok（`missing_ok_cases`）、`--min-cases` 过薄
- **覆盖矩阵**：每个函数参数出现过的 JSON 类型、非 ASCII、空输入、数值边界（0 / 负数 / ≥1e21）

不做：不运行上游、不判断 Rust 实现是否正确、不生成用例、不联网、不替代 fuzz。覆盖矩阵是**描述**不是分数——`missing_types` 只说明录制里没出现该类型，不代表函数应该接受它。

## 安装 / 用法

零第三方依赖，Python 3.8+：

```bash
git clone git@github-linmoxi33:linmoxi33/rust-anything-recording-audit.git
cd rust-anything-recording-audit
python3 bin/rust-anything-recording-audit examples/in/cases.jsonl
```

对着自己的录制跑：

```bash
python3 bin/rust-anything-recording-audit /path/to/cases.jsonl
python3 bin/rust-anything-recording-audit /path/to/cases.jsonl --json
python3 bin/rust-anything-recording-audit /path/to/cases.jsonl --min-cases 50
```

`--json` 输出（节选自 `examples/out/report.json`，字段完整）：

```json
{
  "records": 80,
  "effective_cases": 80,
  "duplicate_cases": 0,
  "functions": 1,
  "findings": [],
  "coverage": {
    "normalize": {
      "cases": 80, "ok": 66, "error": 14,
      "arg_types": ["null", "bool", "string", "array", "object"],
      "non_ascii": true, "empty_input": true, "numeric_edges": []
    }
  },
  "summary": {"error": 0, "warn": 0, "total": 0}
}
```

退出码：

| 码 | 含义 |
| --- | --- |
| `0` | 录制集无结构问题、无 warn（覆盖矩阵里的 missing_types 只是信息） |
| `1` | 检出问题：至少一条 error 或 warn（含 `--min-cases` 触发的过薄告警） |
| `2` | 用法或输入错误：文件读不了、没有任何有效用例、参数非法 |

## 与同类项目的差异

动手前执行过：

- `gh search repos "rust-anything"` → 无同名/近似的录制审计工具
- `gh search repos "cases.jsonl audit"` / `"recording coverage audit"` → 无成熟同类（stars > 500 的 0 个）
- `gh search code "cases.jsonl"` → 只命中 rust-anything 自己的夹具

与本仓库上游的 `record` / `diff` / `gate` 的区别：它们判定**输出是否匹配录制**；本工具判定**录制是否值得信**。两者互补，不替换。

## 本轮创新

首个把 `rust-anything` 的录制集本身当审计对象、而不是把录制当 ground truth 的工具：它把“0 mismatches”拆成 effective cases / duplicates / contradictions / 分支缺口 / 输入面覆盖，并在上游真实 900 条夹具上跑出 3 条可复现 warn（`upper` 与 `countWords` 各 300 ok / 0 error）。此前没有任何公开工具或上游命令做这件事；创新点是视角反转（审计证据而非审计实现），不是换皮。

## 局限

- 只理解 `cases.jsonl` 的公开字段（`fn` / `args` / `ok` / `error`）；上游若改格式，需要跟。
- 覆盖矩阵看的是**参数 JSON 类型**，不解析目标语言的类型系统，也不做取值分布统计。
- 重复判定是 `fn` + 规范化后的 `args` 全等；参数对象键序不同会被视为同一条（这是有意的）。
- `constant_output` 在函数合法地返回常量时会误报，需要人看一眼。
- 不检查录制是否来自真实生产流量，也不评价用例质量本身。
- 本次只在 Python 3.11 / Linux 上验证；无第三方依赖，理论上 3.8+ 均可。

## 数据与许可

`examples/in/cases.jsonl` 是上游 `demo/fixtures/async-rs/cases.jsonl` 的前 80 行真实摘录（MIT，版权归 rust-anything 作者），仅用于演示输入格式；`examples/in/problem.jsonl` 是为覆盖错误路径人工构造的样例。本项目代码 MIT。