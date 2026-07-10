# Claimfold Codex Audit Report

审计日期：2026-07-10

审计范围：当前 working tree。审计过程中未执行会写入 `__pycache__`、安装依赖、提交、拉取或推送的操作。最初按只读审计执行；本文件是在 Owner 后续明确要求落盘后新增。

## 总体判断

未发现 P0。项目设计理念清楚，审计留痕意识强，但实现仍是实验原型：核心文件过大、测试缺失、并发写账本和 Mock 污染会影响可信度。不建议作为生产/对外发布版本立即发布。

## 1. 并行 RESPOND 写账本没有同步

### 判断

成立

### 证据

- `lib/engine.py:1989` 并行执行 Guest。
- `lib/engine.py:1431` 线程内 `append_event` 后立即 `rebuild_index`。
- `lib/claim_lifecycle.py:82` 直接 append ledger。
- `lib/claim_lifecycle.py:226` 直接覆盖写 index。

### 风险

多 Guest 同时回应 claim 时，`claims.jsonl` 和 `claims_index.json` 可能出现竞态、丢事件、索引短暂不一致。

### 建议

账本写入集中到主线程；或引入文件锁、原子临时文件替换索引、单轮结束后统一 rebuild。

### 优先级

P1

## 2. Mock 输出会进入状态，影响研究结论

### 判断

成立

### 证据

- `lib/engine.py:341`、`lib/engine.py:354` CLI 不可用或失败会生成 Mock。
- `lib/engine.py:462` JSON 模式直接 merge 到 state。
- `lib/engine.py:912` Research fallback 可能生成非 `[MOCK]` 文案。
- `docs/EXPERIMENTS.md:79` 文档已记录 “mock -> state 污染” 风险。

### 风险

Mock 被当作事实或语义项沉淀，污染后续 `confirmed_points`、`conflicts`、`open_questions` 和 Claim 生命周期。

### 建议

默认 fail-fast；Mock 仅在显式 `COUNCIL_MOCK=1` 且标记 `mock_excluded_from_state=true` 时允许，不参与 state 或 claim。

### 优先级

P1

## 3. Claim 晋升校验未完全实现规范

### 判断

成立

### 证据

- `docs/CLAIM_LIFECYCLE.md:29` 规范禁止活跃 `conflicts`、projection-only、single-round singleton 晋升。
- `lib/claim_lifecycle.py:148` 实现只拒绝 `open_questions`。
- `lib/claim_lifecycle.py:160` 实现只校验证据文件是否存在。

### 风险

弱证据、未解决分歧或仅摘要投影可被注册为跨会主张，削弱 Claim Lifecycle 可信度。

### 建议

校验证据必须位于 meeting raw/summary 允许目录，且 raw 中能定位陈述锚点；对 active conflict/singleton 默认拒绝，只有 `--owner-override` 可绕过。

### 优先级

P1

## 4. RESPOND 解析不限制注入主张，证据引用粒度不足

### 判断

成立

### 证据

- `lib/claim_lifecycle.py:343` 解析器接受 raw 中任意 `clm-\d+`。
- `lib/claim_lifecycle.py:386` 事件证据只写目录 `meet-id/raw/`，不是具体 raw 文件。

### 风险

Guest 可无意或恶意回应未注入 claim；审计时难以定位具体证据文件。

### 建议

只接受本轮注入 claim 集合；事件写入精确 `raw/round-XXX-guest.md`，并记录解析行或片段哈希。

### 优先级

P1

## 5. 报告生成硬编码 Mock/黄金占位内容

### 判断

成立

### 证据

- `lib/runtime_ext.py:651` 固定输出“市场数据层全部为 Mock/缺失”。
- `lib/runtime_ext.py:588` 固定黄金 Scenario。
- `lib/runtime_ext.py:688` 固定“仅 1 轮 Mock 发言”。

### 风险

真实会议也可能生成误导性报告，影响投资或研究判断。

### 建议

报告完全由 `state + metrics + context` 渲染；Mock 文案只在 metrics 判定存在 Mock 时出现。

### 优先级

P1

## 6. `run-daily` 绕过 Owner pause

### 判断

成立

### 证据

`lib/engine.py:2301` 在 `owner_required` 时直接清除并继续。

### 风险

违反 README 中 Owner 控制原则，自动日频任务可能越过人工接管点。

### 建议

要求先执行 `continue`，或为 `run-daily` 增加显式 `--force-owner-continue` 并写入审计记录。

### 优先级

P1

## 7. 并行轮全部失败仍推进轮次

### 判断

成立

### 证据

- `lib/engine.py:1999` 失败 entry 仅打印后跳过。
- `lib/engine.py:2033` 随后无条件 `state["round"] = round_num` 并清空 `selected_guests`。

### 风险

一次外部 CLI 故障会消耗轮次、破坏可重放性，并让后续语义闭环基于空轮推进。

### 建议

若成功数为 0，保留轮次和 selected_guests，返回失败；部分失败时明确记录 degraded round。

### 优先级

P1

## 8. 路径边界校验不足

### 判断

部分成立

### 证据

- `lib/engine.py:283` `.current_meeting` 直接拼接 meeting 路径。
- `lib/engine.py:2829`、`lib/engine.py:2309` `--meeting`、`--prior-meeting` 直接拼接。
- `lib/engine.py:2566` artifact 路径从 state 读取后拼接。
- `lib/engine.py:3009` TUI 使用 shell 拼接路径执行。

### 风险

若 meeting state 或本地文件被篡改，可能读取或引用仓库外文件；TUI 路径拼接也扩大命令注入面。

### 建议

限制 meeting_id 正则 `^meet-\d{8}-\d{6}$`，所有 resolved path 必须 `is_relative_to(MEETINGS_DIR)`；TUI 改为 argv list。

### 优先级

P2

## 9. `engine.py` 职责过重

### 判断

成立

### 证据

`lib/engine.py` 单文件包含 CLI、调度、模板、状态迁移、Claim 命令、TUI、报告生成，函数延伸到 `lib/engine.py:3141`。

### 风险

修改任一功能容易影响其他路径，测试与审计成本高，架构腐化已经出现。

### 建议

拆分为 `cli.py`、`meeting_state.py`、`runner.py`、`claims_cli.py`、`reports.py`、`prompts.py`。

### 优先级

P2

## 10. 测试体系缺失

### 判断

成立

### 证据

仓库无 `tests/`、无 pytest/unittest 命名测试、无 CI/依赖锁；只发现脚本入口。

### 风险

Claim fold、Mock 过滤、summary parser、路径校验等核心契约无法防回归。

### 建议

先补纯函数单测：`validate_promotion_candidate`、`parse_claim_responses_from_raw`、`apply_summary_json_to_state`、`select_claims_for_injection`；再做一条 mock-free 集成验收。

### 优先级

P1

## 11. 配置缺少边界保护

### 判断

成立

### 证据

- `lib/runtime_ext.py:73` `max_parallel` 直接 `int` 返回。
- `lib/engine.py:1989` 直接进入 ThreadPoolExecutor。
- `lib/engine.py:1366` timeout 直接转 int。

### 风险

配置为 0、负数或过大时导致崩溃或资源耗尽。

### 建议

集中校验配置 schema：`1 <= max_parallel <= 8`，timeout 限定合理区间，启动时 fail-fast。

### 优先级

P2

## 12. 文档与实现存在不一致

### 判断

成立

### 证据

- `docs/CLAIM_LIFECYCLE.md:337` 文档称 `claims_index.json`、`final.md`、`investment_report.md` “Never writable”。
- `lib/claim_lifecycle.py:226`、`lib/engine.py:2637` 实现会写这些文件。
- `README.md:157` 示例 `max_parallel: 3`，当前 `config/guests.yaml:2` 为 6。

### 风险

运维和审计人员会误判权威数据源和运行行为。

### 建议

改成“不可作为独立真相源/不可手工编辑”；配置文档由实际 YAML 生成或保持同步。

### 优先级

P2

## 13. 时间处理有硬编码和时区错误

### 判断

成立

### 证据

- `lib/engine.py:74` 投资议程硬编码“截至2026年7月9日”。
- `lib/engine.py:2148`、`lib/engine.py:2172` `run-daily` 标注 UTC+8，但使用本地 `datetime.now()`。

### 风险

过期 prompt 和错误时区会污染市场研究上下文。

### 建议

所有相对日期由当前 UTC/目标市场时区计算；明确 `America/New_York`、`Asia/Shanghai` 或 UTC。

### 优先级

P2

## 14. 本地代理权限文件未忽略

### 判断

成立

### 证据

- `.qoder/settings.local.json:3` 允许 `Bash(git:*)` 等本地命令。
- `.gitignore` 未忽略 `.qoder/`。

### 风险

本地代理权限策略可能被误提交，扩大其他工具执行面。

### 建议

将 `.qoder/` 加入 ignore；只保留无权限的示例配置。

### 优先级

P2

## 最终总结

1. 项目整体健康度：58/100
2. 架构成熟度：55/100
3. 技术债等级：高
4. 安全风险等级：中
5. 是否建议立即发布：不建议生产/对外发布；可继续内部实验
6. 必须修复：并发账本写入、Mock 污染、Claim 校验、硬编码报告、全失败轮推进、测试缺失
7. 可以延期：文件拆分、配置 schema、文档同步、时区规范、`.qoder/` ignore
8. 最值得称赞的设计：prompt/raw/summary/metrics 留痕链路，以及 Claim ledger/index 分离思路
9. 最需要重构的模块：`lib/engine.py`
