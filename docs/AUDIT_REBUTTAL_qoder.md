# 对 Qoder 审查报告（`AUDIT_REPORT.md`）的反驳与补充意见

**撰写日期：** 2026-07-10  
**撰写人：** Grok（基于代码复核 + `meet-20260710-043201` 等真实 CLI 实验）  
**对应文档：** `docs/AUDIT_REPORT.md`

---

## 总体立场

Qoder 报告技术细节扎实，多数条目**成立**。但部分优先级、健康度评分与个别证据链，与当前 working tree 和已跑通的实验结果不一致。下文按「认同 / 部分认同 / 反驳」分类，并给出修正后的优先级建议。

---

## 认同（无需反驳，应尽快修复）

| # | 问题 | 说明 |
|---|------|------|
| 2 | 并发写 `claims.jsonl` | `process_parallel_guest` 线程内 `append_event` + `rebuild_index` 确无锁，应改为主线程合并写入。**认同风险，仅反驳 P0 定级（见下）。** |
| 3 | tmux `shell=True` | `lib/engine.py:3009` 应改为 argv 列表。 |
| 8 | 无测试、无依赖声明 | 仓库仍无 `tests/`、`pyproject.toml`，回归风险真实。 |
| 12 | `cmd_init` 引用已下线模型 | `engine.py:1502-1537` 与当前 `guests.yaml` 脱节，新用户 `init` 会踩坑。 |
| 14 | `save_state` 非原子写 | 直接 `open("w")` 覆盖，断电可损坏 JSON。 |
| 1 | `engine.py` 上帝文件 | 3171 行、职责混杂，长期维护成本高。 |
| 5 | 硬编码投资报告 | `runtime_ext.py` 中 Scenario/资产段落为占位符，不反映真实会议。 |
| 7 | Guest 别名三处重复 | `LEGACY_GUEST_MAP` / `GUEST_ALIASES` / `cmd_init` 不一致。 |
| 6 | `utc_now()` 重复 | 应抽到 `lib/utils.py`。 |

---

## 部分认同（风险成立，但优先级或表述需修正）

### 问题 4：CLI 失败静默降级为 Mock

**Qoder 判断：** 成立，P1。

**补充：**

- 认同 `invoke_cli` 在失败时静默返回 mock（`engine.py:365-388`），且 `used_mock_guest` 主要进 `metrics.json`，终端无显著警告。
- **但 state 污染路径已被部分封堵（审计后新增）：**
  - `apply_summary_json_to_state` 经 `is_mock_semantic_item` 过滤（`runtime_ext.py:192`）
  - `run_summarizer_for_guest` 在 summarizer mock 时走 `fallback_summary_from_research_raw` 启发式摘要，而非 `[MOCK/...]` 模板（`engine.py:967-969`）
  - `verify_research_semantic_loop` 跳过 mock prior_items（`runtime_ext.py:417`）
- **剩余真实缺口：** Guest **raw** 若为 mock，启发式 fallback 仍可能从 raw 提取条目进入 state；`metrics.json` 中 `mock_guest_rate_pct: 0` 不等于「语义项零污染」。

**修正优先级：** 仍为 P1，但应区分「静默 mock」（P1）与「summarizer mock 污染 state」（已由近期补丁大幅缓解，降为 P2 跟踪）。

**证据：** `meet-20260710-043201/metrics.json` — `mock_guest_rate_pct: 0.0`，`guest_failure_rate_pct: 0.0`，7 次 guest 发言全部真实 CLI。

---

### 问题 2：并发写账本 — P0 定级过高

**Qoder 判断：** P0。

**反驳：**

1. **触发面窄：** 竞态仅在「并行轮 + 注入 claim + guest raw 含 claim_responses」时发生；普通 `run-parallel` 研究轮不写 ledger。
2. **Codex 同级审计定为 P1**（`AUDIT_REPORT_codex.md` §1），更符合「内部实验原型、单用户本地」的风险模型。
3. **Linux 小行 append 常为行级原子**；真正危险的是多线程交错 `rebuild_index` 覆盖写索引，而非 JSONL 行内字节交错（虽不能完全排除）。

**建议定级：** P1（必须修，但不应阻塞「内部继续实验」）。

---

### 问题 10：并行 guest 无交叉引用

**Qoder 判断：** 成立，P2，建议交错并行。

**反驳（架构层面）：**

这不是疏漏，而是 **Research 模式的两阶段设计**：

```
Round 1（并行）：同 state 快照 → 追求多样性基线（独立视角）
Round 2（并行）：携带 Round 1 的 CP/CF/OQ → 语义闭环（交叉引用）
```

- `docs/EXPERIMENTS.md` §0 明确流程：`context → parallel → semantic loop → claim`
- `verify_research_semantic_loop` 专门验证 Round N 是否携带 Round N-1 语义项
- 实验 A（`meet-20260710-015200`）两轮并行后语义闭环 **通过**

同轮内互不可见会牺牲「实时辩论感」，但换取 **更低延迟 + 更低同质化 prompt**（若串行注入前者发言，后者 prompt 膨胀且锚定前者错误）。实验 B 已证明「人数 ≠ 质量」，同轮交叉引用不是当前瓶颈。

**建议：** 文档补一句「Round 1 并行 guest 互不可见」即可；**不应列为架构缺陷**，最多是「可选增强模式」（P3）。

---

### 问题 9：模板注入风险

**Qoder 判断：** 成立，P2。

**反驳（风险被高估）：**

- `render_template` 的 `{{key}}` 替换中，**key 由引擎模板定义**，非 guest 可控。
- 风险场景是：guest 输出或 owner 输入文本中恰好含 `{{confirmed_points}}` 等字面量，在**下一轮**被误替换——需恶意或极低概率碰撞。
- 当前为 **单用户本地研究工具**，非多租户对外服务；prompt 注入面远低于 tmux `shell=True`。

**建议定级：** P3（有空再做转义），不应与账本竞态同级。

---

### 问题 15：Yahoo Finance 非公开 API

**认同不稳定风险**，但这是 **context 证据层** 问题，有脚本 fallback 和「数据缺失」标注；不阻塞核心会议流程。维持 P2 合理。

---

### 问题 18：`dedupe_guest_output.py` 脆弱

**认同**，但仅影响 codex/qoder 等本地 guest 脚本的 **输出后处理**；dedupe 失败时最坏情况是保留重复文本，不会损坏 state。P3 合理。

---

## 明确反驳（证据不成立或结论错误）

### 问题 17：`__pycache__` 被提交

**Qoder 判断：** 成立。

**反驳：**

```bash
cd /home/cnhanbing/Claimfold && git ls-files | grep -E 'pycache|\.pyc'
# 输出为空
```

- `.gitignore` 已含 `__pycache__/`
- 本地存在 `lib/__pycache__/` 是 **Python 运行时产物**，未被 Git 跟踪
- Qoder 用 `find` 发现目录存在 ≠ 被提交；建议的 `git rm --cached` **当前不需要**

**应改为：** 「不成立 — 仅本地缓存，未入库」。

---

### 问题 13：`select_guests_for_focus` 过于简单

**认同算法简陋**，但这是 **可选自动推荐**；`EXPERIMENTS.md` §8 生产流程明确使用 `./council.sh select ...` 手动选人。不应影响健康度主评分。

---

## 健康度评分反驳

| 维度 | Qoder 评分 | 建议修正 | 理由 |
|------|-----------|----------|------|
| 整体健康度 | **42/100** | **55–62/100** | Phase 2（E1–E5）全链真实 CLI 通过；`meet-20260710-043201` 四模型并行 0% mock；Claim CHALLENGE 跨会验证通过 |
| 架构成熟度 | **35/100** | **48–55/100** | Claim ledger/index 分离、artifact 全链路、semantic loop 已交付且实验验证 |
| 安全风险 | 中 | 中（认同） | tmux 注入 + 账本竞态属实，但无外部攻击面 |

42 分隐含「尚不可做内部实验」，与 `EXPERIMENTS.md` §11「Phase 2 已完成」矛盾。Codex 给的 58/100 更接近现状；本报告建议取 **中间值 ~58**，并注明「生产发布仍不建议」。

---

## 对 Qoder「最值得称赞」部分的补充

Qoder 对 Claim Lifecycle、审计链路、Owner 控制、Mock 模式设计的表扬 **完全认同**。额外补充：

- **`run-daily` + `daily_decision.md`** 已在 `meet-20260710-043201` 验证（71–84s，真实多模型输出）
- **`guest_type: script`**（`tsla_feed` 0.3s）ROI 高于再堆 LLM 嘉宾
- **mock 过滤补丁**（`is_mock_semantic_item`、`run_summarizer_for_guest`）应在下一版审计中单独列为「已缓解项」

---

## 修正后的必须修复清单（相对 Qoder 原表）

| 优先级 | 问题 | 与 Qoder 差异 |
|--------|------|---------------|
| P1 | 账本并发写 | 自 P0 降为 P1 |
| P1 | CLI 静默 mock + `--strict` | 保留；另跟踪 summarizer 污染（已部分修复） |
| P1 | 无测试 | 保留 |
| P1 | `cmd_init` 过期模型 | 保留 |
| P1 | 非原子 `save_state` | 保留 |
| P1 | tmux `shell=True` | 保留 |
| P2 | 硬编码投资报告 | 保留 |
| P3 | 并行同轮无交叉引用 | 自 P2 降为 P3（文档化即可） |
| ~~P3~~ | ~~`__pycache__` 已提交~~ | **撤销** — 未跟踪 |

---

---

## 修复状态（2026-07-10 第二轮）

### 已修复（认同项）

| # | 问题 | 修复 |
|---|------|------|
| 2 | 并发写 claims.jsonl | `respond_events` 延迟到主线程合并写入 + `fcntl.flock` |
| 3 | tmux shell=True | 改为 argv 列表调用 |
| 4 | CLI 静默 mock | stderr 警告 + `--strict` / `COUNCIL_STRICT=1` |
| 8 | 无测试 | `tests/` + `tests/run_tests.py`（8 项） |
| 12 | cmd_init 过期模型 | 从 `config/guests.yaml.template` 复制 |
| 14 | save_state 非原子 | `utils.atomic_write_json` |
| 5 | 硬编码投资报告 | `runtime_ext` 从 state/metrics 动态汇编 |
| 7 | Guest 别名重复 | `LEGACY_GUEST_MAP` 合并 `GUEST_ALIASES` |
| 6 | utc_now 重复 | 统一到 `lib/utils.py` |
| — | 配置边界 | `max_parallel` 1–8，timeout 10–900s |
| — | meeting_id 校验 | `^meet-\d{8}-\d{6}$` + path 边界 |
| — | .qoder/ ignore | 已加入 `.gitignore` |

### 维持反驳（不修改设计）

| # | 问题 | 立场 |
|---|------|------|
| 10 | 并行同轮无交叉引用 | **架构设计**：Round1 多样性 + Round2 语义闭环，仅文档化 |
| 17 | __pycache__ 已提交 | **不成立**，未被 git 跟踪 |
| 9 | 模板注入 | 风险低于 tmux，维持 P3 延期 |
| 13 | select_guests 简单 | 可选辅助，生产用手动 `select` |
| 1 | engine.py 拆分 | 认同技术债，但不在本轮大改（P2 延期） |
| 2 定级 | P0 → | 维持 **P1**，非阻塞内部实验 |

---

*本文件为对 `AUDIT_REPORT.md` 的独立反驳意见；认同项已落盘修复，反驳项维持原立场。*