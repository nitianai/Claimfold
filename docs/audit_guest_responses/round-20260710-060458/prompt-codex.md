# Claimfold 审计复核 — 嘉宾 codex

你是 Claimfold 多模型会议的一名嘉宾。请**只读**审阅下列材料，不要执行仓库命令。

## 你的任务

1. 对「反驳文档」中**维持反驳**的条目：同意或提出反反驳（需证据）
2. 对「已修复」条目：评价修复是否充分，有无遗漏回归点
3. 给出修订后健康度（0–100）与 3 条最高优先级后续动作
4. 保持简洁，用中文，≤800 字

## 角色侧重

你审的是 **Codex 原始审计 + 对 Codex 的反驳**。重点：Mock 污染是否仍 P1、run-daily owner 策略、全失败轮次。

---

## 已落地修复摘要（2026-07-10）

- 账本：claim RESPOND 主线程合并写 + fcntl.flock
- save_state 原子写（lib/utils.py）
- CLI mock：stderr 警告 + --strict / COUNCIL_STRICT=1
- 并行轮全失败不推进 round
- Claim 晋升/RESPOND 校验收紧
- tmux argv 列表；meeting_id 正则校验
- cmd_init 从 config/guests.yaml.template 复制
- 投资报告从 state/metrics 动态汇编
- tests/run_tests.py 8 项通过；pyproject.toml；.qoder/ gitignore
- run-daily 需 --force-owner-continue 并写 daily_owner_override 审计

---

## 原始审查报告

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

---

## Grok 反驳意见

# 对 Codex 审查报告（`AUDIT_REPORT_codex.md`）的反驳与补充意见

**撰写日期：** 2026-07-10  
**撰写人：** Grok（基于代码复核 + `meet-20260710-043201` 等真实 CLI 实验）  
**对应文档：** `docs/AUDIT_REPORT_codex.md`

---

## 总体立场

Codex 报告 **整体校准优于 Qoder 报告**：无 P0、账本竞态定 P1、健康度 58/100 更贴近「可继续内部实验、不可生产发布」的定位。以下仅对**过时判断、意图误判、优先级偏差**提出反驳；其余条目认同。

---

## 完全认同（直接纳入 backlog）

| § | 问题 | 备注 |
|---|------|------|
| 1 | 并行 RESPOND 写账本无同步 | 应主线程合并写 + 单次 `rebuild_index` |
| 3 | Claim 晋升校验不完整 | 仅拦 `open_questions`，未拦 active conflicts / projection-only |
| 4 | RESPOND 解析不限制注入 claim | 可回应任意 `clm-\d+`，证据粒度粗 |
| 5 | 报告硬编码 Mock/黄金占位 | `runtime_ext.py:588-688` |
| 7 | 并行轮全失败仍推进轮次 | `engine.py:2033` 无条件 `state["round"] = round_num` |
| 8 | 路径边界 / TUI 注入 | 部分成立；`shell=True` 应修 |
| 9 | `engine.py` 职责过重 | 认同拆分方向 |
| 10 | 测试体系缺失 | 认同；建议先测纯函数 |
| 11–14 | 配置边界、文档不一致、时区、`.qoder/` ignore | 均为有效技术债 |

---

## 部分认同 / 需修正表述

### §2 Mock 输出进入状态 — 审计快照已过时

**Codex 判断：** 成立，P1。

**反驳（程度）：** 风险**仍部分成立**，但 Codex 引用的证据链未覆盖 **审计后新增的缓解层**：

| 机制 | 位置 | 作用 |
|------|------|------|
| `is_mock_semantic_item()` | `runtime_ext.py:16-22` | 过滤 `[MOCK` 前缀 + `NON_PROMOTION_MARKERS` |
| `apply_summary_json_to_state` | `runtime_ext.py:192` | merge 前过滤 mock 语义项 |
| `run_summarizer_for_guest` | `engine.py:967-969` | summarizer mock → `fallback_summary_from_research_raw`，不走 MOCK 模板 |
| `filter_semantic_items` | `engine.py:852-853` | rebuild state 时过滤 |
| `verify_research_semantic_loop` | `runtime_ext.py:417` | 验证时跳过 mock prior_items |

**仍存在的真实缺口（认同 Codex）：**

1. `invoke_cli` guest 失败仍静默 mock raw（`engine.py:365-388`）
2. `fallback_summary_from_research_raw` 从 **真实格式但内容空洞的 mock raw** 仍可能抽出条目（`engine.py:912` 兜底行）
3. JSON 模式 `merge_guest_json_to_state` 路径需单独确认 mock 过滤（Codex 指 `engine.py:462`）

**修正结论：**

- 「Mock 污染 state」从 **P1 主风险** 调整为：**「Guest 静默 mock」仍为 P1；「Summarizer mock → state」已缓解，降为 P2 回归测试项**
- `meet-20260710-043201`：`mock_guest_rate_pct: 0.0`，R4 summarizer **无 MOCK**（相对 EXPERIMENTS.md §79 记录的 38% mock 污染基线，已是实质改进）

---

### §6 `run-daily` 绕过 Owner pause — 意图误判为缺陷

**Codex 判断：** 成立，违反 README Owner 控制原则，P1。

**反驳：**

1. **有意设计：** `cmd_run_daily` 文档字符串写明 `14:30 日频`（`engine.py:2288`）；`build_daily_context` 标题为 `Market Context — Daily (14:30)`（`engine.py:2170`）。自动清除 `owner_required` 是为 **定时日频任务无人值守**，不是疏漏。
2. **README 未涵盖 run-daily：** README 只描述每 3 轮 `owner_required` 的 **研究会议** 流程，未声明日频模式也受此约束。称「违反 README」**证据不足**。
3. **审计留痕已有：** 清除时打印 `Auto-continue: owner_required cleared for daily run.`（`engine.py:2305`）。

**认同的改进方向：**

- 应增加显式 `--force-owner-continue`（默认 run-daily 行为不变），并在 `daily_decision.md` 或 `meeting_state.json` 写入 `owner_override_reason`
- README 应新增「日频模式」小节，说明与研究会话的 Owner 策略差异

**修正定级：** 自 P1「缺陷」→ **P2「文档与显式 flag 缺失」**；行为本身可保留为默认。

**实验证据：** `meet-20260710-043201` 通过 `run-daily` 生成 `daily_decision.md`，内容为真实多模型合议，非 mock 占位。

---

### §7 并行轮全失败仍推进 — 危害被部分夸大

**Codex 判断：** 破坏可重放性，P1。

**部分反驳：**

- 失败 entry **不会** `apply_summary_json_to_state`（`engine.py:2000-2003` `continue` 跳过），state 语义项不被空轮污染
- 真实损害是：**round 计数器 +1**、`selected_guests` 清空、history 记录 degraded round——影响的是「轮次编号连续性」，非「state 内容被伪造」
- 对研究场景，用户可 `stop` 后新建会议；对 automation，应 fail-fast

**建议：** 维持 P1，但风险描述应区分「轮次消耗」与「结论污染」。

---

### §8 路径边界 — 「部分成立」认同，但威胁模型需收窄

**Codex 判断：** 部分成立，P2。

**补充：**

- `meeting_id` 由引擎生成 `meet-YYYYMMDD-HHMMSS`，非用户自由输入
- `.current_meeting`、artifact 路径来自本地 state，攻击前提为 **本机 state 文件已被篡改**
- 在单用户本地研究工具语境下，P2 合理；**不应升级为 P1**

**TUI `shell=True` 部分仍认同为 P1**（与路径遍历不同类）。

---

### §12 文档与实现不一致 — 语义问题，非功能错误

**Codex 证据：** `CLAIM_LIFECYCLE.md` 写 index/final/report 「Never writable」，但引擎会写。

**反驳：**

规范意图是 **「人类不可手工编辑 / 非独立真相源」**（引擎可重建），而非「进程不可写」。这是 **文档措辞错误**，不是实现违背设计。

**建议：** 改文档为「不可作为手工编辑的权威源；由引擎自动生成/重建」，而非改引擎行为。维持 P2。

---

### §13 时区硬编码 — 认同，但对 run-daily 影响有限

`datetime.now()` 用于本地 14:30 触发时，在 **单机 cron 与操作者同一时区** 的前提下可工作；问题在于 **prompt 内「截至2026年7月9日」硬编码**（`engine.py:74`）会过期，与 run-daily 动态 context 是不同路径。

**建议：** 硬编码议程日期为 P2；run-daily 时区标注为 P3（除非跨时区部署）。

---

## 明确反驳

### 健康度 58/100 — 略偏低，但未严重失真

Codex 评分比 Qoder（42）合理。考虑到：

- Phase 2 E1–E5 全完成
- 四模型（grok/codex/qoder/claude_sonnet）并行 0% mock（`meet-20260710-043201`）
- Claim 跨会 CHALLENGE 链验证通过

**建议区间：** 60–65/100（内部实验平台），「不建议生产发布」结论 **保持不变**。

---

### 「无 P0」— 完全认同

Codex 未将账本竞态标 P0，与我们对 Qoder P0 定级的反驳一致。这是 Codex 报告最值得肯定的校准点。

---

## Codex 未覆盖、应补充的正面项

以下能力在 Codex 14 条之外，且已被实验验证，应在下一轮审计中列为「已交付」：

| 能力 | 证据 |
|------|------|
| `run-daily` 日频流水线 | `engine.py:2288-2337`，`daily_decision.md` 产出 |
| Summarizer 防 MOCK 链 | `run_summarizer_for_guest` + heuristic fallback |
| 本地 guest 去重 | `scripts/dedupe_guest_output.py` + codex/qoder wrapper |
| `context_collector` script-first | 减轻 context 阶段 LLM 依赖 |
| `claude_sonnet` / `qoder` 嘉宾扩展 | `config/guests.yaml`，并行 `allow_parallel: true` |

---

## 修正后的优先级建议（相对 Codex 原表）

| 原优先级 | 条目 | 建议调整 |
|----------|------|----------|
| P1 | Mock 污染 | 拆为：Guest 静默 mock（P1）+ summarizer 污染（P2，已缓解） |
| P1 | run-daily owner bypass | → P2（补文档 + `--force-owner-continue` flag） |
| P1 | 全失败仍推进 | 保持 P1，但改写风险为「轮次消耗」 |
| P1 | 账本并发 | 保持 P1 |
| P1 | 测试缺失 | 保持 P1 |
| P2 | 文档 never writable | 保持 P2，改文档不改代码 |

---

## 与 Qoder 审计的分歧对照（供 Owner 裁决）

| 议题 | Codex | Qoder | Grok 立场 |
|------|-------|-------|-----------|
| 账本竞态 | P1 | P0 | **认同 Codex P1** |
| 健康度 | 58 | 42 | **58 附近合理**（可微调 +2~7） |
| 并行同轮无交叉引用 | 未单列 | P2 缺陷 | **非缺陷，是两轮语义闭环设计** |
| `__pycache__` 入库 | 未提 | 成立 | **不成立** |
| run-daily owner | P1 缺陷 | 未提 | **P2 文档化，非行为缺陷** |

---

---

## 修复状态（2026-07-10 第二轮）

### 已修复（认同项）

| § | 问题 | 修复 |
|---|------|------|
| 1 | 并行 RESPOND 写账本 | 主线程合并 + `fcntl.flock` |
| 2 | Mock 污染（部分） | `--strict`、stderr 警告；summarizer 过滤链保留 |
| 3 | Claim 晋升校验 | active conflict / singleton / evidence 锚点 / 允许目录 |
| 4 | RESPOND 解析 | 仅接受注入 claim 集；精确 raw 文件 evidence |
| 5 | 硬编码报告 | state + metrics 动态汇编 |
| 7 | 全失败仍推进 | `success_count==0` 时 exit 1，不 increment round |
| 8 | 路径/TUI | meeting_id 校验；tmux argv |
| 10 | 测试缺失 | `tests/` 8 项 + `pyproject.toml` |
| 11 | 配置边界 | max_parallel / timeout clamp |
| 12 | 文档 never writable | `CLAIM_LIFECYCLE.md` 措辞修正 |
| 13 | 议程日期硬编码 | `investment_question()` 动态替换 |
| 14 | .qoder/ | `.gitignore` |

### 维持反驳（不修改设计 / 行为调整有边界）

| § | 问题 | 立场 |
|---|------|------|
| 6 | run-daily owner bypass | **非缺陷**：日频无人值守场景；现改为需 `--force-owner-continue` 并写 `daily_owner_override` 审计记录（比「默认静默清除」更严，符合 Codex 建议） |
| 9 | engine.py 拆分 | 认同，P2 延期 |
| 2 程度 | summarizer mock 污染 | 审计快照过时；Guest 静默 mock 仍 P1，已由 `--strict` 覆盖 |
| 8 威胁模型 | 路径遍历 | 单用户本地工具，维持 P2 |

### run-daily 新用法

```bash
./council.sh run-daily "TSLA、VIX、美债" --force-owner-continue
```

---

*本文件为对 `AUDIT_REPORT_codex.md` 的独立反驳意见；认同项已落盘修复，反驳项维持原立场。*

---

## 输出格式（必须遵守）

判断：
已确认事实：
合理推断：
反方视角：
建议：
是否需要下一轮：
