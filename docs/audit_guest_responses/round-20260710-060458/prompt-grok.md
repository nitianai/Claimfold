# Claimfold 审计复核 — 嘉宾 grok/laguna

你是 Claimfold 多模型会议的一名嘉宾。请**只读**审阅下列材料，不要执行仓库命令。

## 你的任务

1. 对「反驳文档」中**维持反驳**的条目：同意或提出反反驳（需证据）
2. 对「已修复」条目：评价修复是否充分，有无遗漏回归点
3. 给出修订后健康度（0–100）与 3 条最高优先级后续动作
4. 保持简洁，用中文，≤800 字

## 角色侧重

你是第三方仲裁。同时看到 Qoder 审计与 Codex 反驳文档。请裁决：P0 定级、健康度 42 vs 58、并行无交叉引用是否缺陷。

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

# Claimfold 仓库全面审核报告

**审核日期：** 2026-07-10  
**审核人：** Qoder (Software Architect / Security Auditor / Code Reviewer)  
**审核范围：** 全仓库只读审核  
**项目描述：** Claimfold — 多模型研究实验平台，确定性多模型会议工作流运行时

---

## 问题 1：engine.py 上帝文件（God File）— 3171 行单文件承载全部逻辑

### 判断

成立

### 证据

`lib/engine.py:1` — 3171 行。包含：
- CLI 参数解析（`build_parser`，~200 行）
- 26 个 `cmd_*` 命令处理函数
- 子进程管理（`invoke_cli`、`invoke_script`）
- Mock 数据生成（`generate_mock_*`，~150 行）
- 报告生成（`generate_council_investment_report` ~200 行、`generate_council_experiment_report` ~180 行）
- 状态管理（`load_state`、`save_state`、`merge_*`）
- 模板渲染、JSON 校验、摘要解析、文件迁移

### 风险

- 任何修改都可能引入回归
- 新开发者无法快速定位代码
- 无法对单个功能独立测试
- 违反单一职责原则（SRP）

### 建议

按职责拆分为：
- `cli.py` — argparse 与命令路由
- `commands/` — 每个 `cmd_*` 独立模块
- `subprocess_runner.py` — `invoke_cli`/`invoke_script`
- `mock.py` — 所有 mock 生成
- `reports.py` — 报告生成
- `state.py` — 状态管理
- `parsers.py` — JSON/Markdown 解析

### 优先级

P2

---

## 问题 2：并发写入 claims.jsonl 无文件锁保护

### 判断

成立

### 证据

`lib/engine.py:1430-1433`：`process_parallel_guest` 中，每个并行 guest 线程可能调用 `append_event(ROOT, ev)` 写入 `claims/claims.jsonl`。

`lib/claim_lifecycle.py:80-83`：`append_event` 直接 `open("a")` 追加写入，无任何锁机制：

```python
def append_event(root: Path, event: dict[str, Any]) -> None:
    ensure_claims_dir(root)
    with ledger_path(root).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
```

`lib/engine.py:1433`：多个线程随后各自调用 `rebuild_index(ROOT)`，读-写 `claims_index.json` 存在竞态。

### 风险

- **P0 级数据损坏**：多线程并发追加可能导致 JSONL 行交错（partial line），`load_events` 会静默跳过损坏行，丢失主张回应事件
- `rebuild_index` 的并发调用可能产生不完整的索引

### 建议

1. 在 `process_parallel_guest` 中将 claim respond 事件的写入延迟到线程合并后，在主线程中顺序写入
2. 或使用 `fcntl.flock` 保护 `append_event`
3. `rebuild_index` 应只在所有并行任务完成后调用一次

### 优先级

P0

---

## 问题 3：tmux TUI 命令注入

### 判断

成立

### 证据

`lib/engine.py:2996-3009`：

```python
cmds = [
    f"tmux new-session -d -s {session} -n council",
    f"tmux send-keys -t {session} 'watch -n2 cat {state_file}' C-m",
    ...
]
for c in cmds[:-1]:
    subprocess.run(c, shell=True, check=True)
```

`session` 来自 `meeting_dir.name`（`meet-20260709-222257`），`state_file` 来自 `meeting_dir / "meeting_state.json"`。虽然当前命名规范使注入概率低，但 `shell=True` + f-string 拼接本质上是命令注入漏洞面。如果会议 ID 被构造为含 shell 元字符的值，即可执行任意命令。

### 风险

本地提权 / 任意命令执行。当前攻击面有限（需要控制会议 ID），但违反安全编码原则。

### 建议

将所有 tmux 命令改为列表形式调用，避免 `shell=True`：

```python
subprocess.run(["tmux", "new-session", "-d", "-s", session, "-n", "council"], check=True)
```

### 优先级

P1

---

## 问题 4：CLI 失败静默降级为 Mock — 用户无感知

### 判断

成立

### 证据

`lib/engine.py:365-389`：`invoke_cli` 中，当 CLI 返回非零退出码、超时或输出为空时，均静默返回 mock 输出：

```python
if result.returncode != 0:
    ...
    return generate_mock_output(..., label=f"{mock_label} (CLI failed: {stderr[:200]})"), True
```

`lib/engine.py:1402-1418`：`process_parallel_guest` 使用 `invoke_cli`，若真实 CLI 失败，guest 收到的是伪造数据但流程继续。返回值中的 `used_mock_guest=True` 被记录但不会被用户注意到（除非主动检查 metrics）。

### 风险

- 用户可能认为获得的是真实模型分析，实际全部是 mock 模板数据
- 在投资委员会模式下，可能基于 mock 数据生成"资产配置建议"

### 建议

1. CLI 失败时默认打印显著警告（如 `⚠ WARNING: Guest qwen returned mock data — CLI failed`）
2. 添加 `--strict` 模式：CLI 失败时终止而非降级
3. 在 `final.md` 和报告的开头显著标注 mock 比例

### 优先级

P1

---

## 问题 5：硬编码投资报告内容 — 不反映真实会议

### 判断

成立

### 证据

`lib/runtime_ext.py:588-637`：`generate_council_investment_report` 中，Scenario A/B/C、资产配置表、各资产分析段落均为硬编码字符串：

```python
scenario_block = """### Scenario A — 基准：黄金区间震荡
- **概率：** 40–50%（待复核...）
..."""

asset_section = """### 美股
待复核。共享 market_context 无有效数据..."""
```

这些内容与真实会议数据无关。无论会议讨论了什么，报告都输出相同的占位文本。

### 风险

- 报告无信息价值，浪费生成和阅读时间
- 用户可能误认为这些是真实分析结论
- 违反 "Engine 不推理，只汇编" 的设计原则

### 建议

1. 若数据不足，报告应明确标注"数据不足，未生成"而非输出硬编码占位
2. Scenario 应从 `state["confirmed_points"]` 和 `state["conflicts"]` 动态提取
3. 资产配置表应从 guest 的 JSON 输出中提取

### 优先级

P2

---

## 问题 6：代码重复 — `utc_now()` 定义两次

### 判断

成立

### 证据

- `lib/engine.py:186`：`def utc_now() -> str:`
- `lib/claim_lifecycle.py:51`：`def utc_now() -> str:`

两处实现完全相同。

### 风险

修改一处忘改另一处导致时间戳不一致。

### 建议

抽取到 `lib/utils.py`，两处统一引用。

### 优先级

P3

---

## 问题 7：Guest 别名映射三处重复且不一致

### 判断

成立

### 证据

| 位置 | 变量名 | 内容 |
|------|--------|------|
| `lib/engine.py:175-183` | `LEGACY_GUEST_MAP` | `{"claude": "qwen", "grok": "laguna", ...}` |
| `lib/runtime_ext.py:25-47` | `GUEST_ALIASES` | `{"claude": "qwen", "grok": "laguna", "logic": "codex", ...}` |
| `lib/engine.py:1502-1537` | `cmd_init` defaults | 硬编码旧模型名（`mimo-v2.5-free`, `laguna-m.1:free` 等已下线模型） |

`GUEST_ALIASES` 比 `LEGACY_GUEST_MAP` 多出了 `"logic"`, `"auditor"`, `"macro"`, `"fx"` 等别名。`cmd_init` 中的默认配置引用了已过期的模型标识符。

### 风险

- 新 `init` 生成的配置文件无法工作（模型已下线）
- 别名解析行为在不同代码路径不一致

### 建议

统一别名表为单一数据源。`cmd_init` 默认配置应从 `guests.yaml` 模板生成而非硬编码。

### 优先级

P2

---

## 问题 8：无测试、无依赖声明、无项目配置

### 判断

成立

### 证据

- 无 `tests/` 目录
- 无 `requirements.txt`、`pyproject.toml`、`setup.py`、`setup.cfg`
- 无 `Makefile`、`Dockerfile`
- 依赖 PyYAML（`import yaml`）但未声明
- README 仅写 "依赖：bash, python3, PyYAML"

### 风险

- 无法 `pip install` 或 `pipx install`
- CI/CD 无法集成
- 无法验证代码正确性
- 新环境部署靠猜测

### 建议

1. 添加 `pyproject.toml` 声明依赖与 Python 版本
2. 为核心模块（`claim_lifecycle`、`parse_summary_sections`、`select_guests_for_focus`）添加单元测试
3. 添加 mock 模式端到端冒烟测试

### 优先级

P1

---

## 问题 9：模板注入风险 — 字符串替换无转义

### 判断

成立

### 证据

`lib/engine.py:306-310`：

```python
def render_template(template_path: Path, variables: dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text
```

若 guest 输出或 owner 输入包含 `{{confirmed_points}}` 等占位符文本，在下一轮模板渲染时会被错误替换。

### 风险

prompt 注入：恶意 guest 输出或 owner 输入可篡改后续 prompt 结构。

### 建议

使用 Jinja2 或添加转义机制；或至少对变量值中的 `{{`/`}}` 进行转义。

### 优先级

P2

---

## 问题 10：并行 guest 的 prompt 基于相同 state 快照 — 无交叉引用

### 判断

成立

### 证据

`lib/engine.py:1355-1481`：`process_parallel_guest` 中，每个并行 guest 收到的 `state` 是同一个对象引用。但 prompt 生成（`generate_research_prompt`）在各自线程中调用，读取同一份 `state["confirmed_points"]`、`state["conflicts"]` 等。

问题：并行 guest 看到的状态完全相同，无法看到同轮其他 guest 的发言。这意味着 N 个 guest 可能产生高度同质化的输出（尤其是对相同 question 的回答）。

### 风险

- 降低多模型多样性增益
- 实验报告中"三位专家 Mock 输出高度同质"的结论部分源于此设计

### 建议

1. 文档中明确说明此限制（并行轮内 guest 互相不可见）
2. 考虑"交错并行"模式：先完成的 guest 结果注入后续 guest 的 prompt

### 优先级

P2

---

## 问题 11：Magic Numbers 散布

### 判断

成立

### 证据

| 数值 | 位置 | 含义 |
|------|------|------|
| 6000 | `engine.py:864` | `truncate_for_summarizer` max_chars |
| 1200 | `runtime_ext.py:660` | context 截断长度 |
| 240 | `engine.py:898` | fallback summary 条目截断 |
| 500 | `claim_lifecycle.py:389` | claim response statement 截断 |
| 1500 | `engine.py:1189` | state_digest 长度阈值 |
| 0.82 | `meeting_quality.py:25` | 相似度阈值 |
| 50 | `engine.py:432` | position 最大字符数 |
| 15 | `runtime_ext.py:469` | final.md 展示条目上限 |

### 风险

无法通过配置调整行为；修改需要搜索全部硬编码位置。

### 建议

抽取为模块级常量或配置文件字段。

### 优先级

P3

---

## 问题 12：`cmd_init` 默认配置引用已下线模型

### 判断

成立

### 证据

`lib/engine.py:1502-1537`：`cmd_init` 写入的默认 `guests.yaml` 引用了：
- `openrouter/poolside/laguna-m.1:free`
- `opencode/mimo-v2.5-free`
- `opencode/nemotron-3-ultra-free`

而实际 `config/guests.yaml` 已更新为 `hermes-grok/grok-4.3`、`opencode/deepseek-v4-flash-free` 等。

### 风险

新用户 `init` 后无法正常工作。

### 建议

`cmd_init` 应从仓库中的模板文件（如 `config/guests.yaml.template`）复制，而非硬编码。

### 优先级

P1

---

## 问题 13：`select_guests_for_focus` 评分算法过于简单

### 判断

成立

### 证据

`lib/runtime_ext.py:77-101`：基于关键词匹配的评分规则：

```python
FOCUS_RULES = [
    (("黄金", "美元", ...), ("qwen", "nemo", "north")),
    (("原油", "能源", ...), ("north", "laguna", "qwen")),
    (("a股", "美股", ...), ("mimo", "qwen", "north")),
]
```

- 仅 3 条规则，覆盖不全
- 当无匹配时回退到 `roster[:3]`（按 YAML 顺序取前 3 个），与议题无关
- 无法处理多主题混合的 focus

### 风险

自动选嘉宾质量低，用户被迫手动 `select`。

### 建议

可扩展 FOCUS_RULES 或允许在 `guests.yaml` 中声明每个 guest 的 `keywords` 字段。

### 优先级

P3

---

## 问题 14：`meeting_state.json` 无原子写入

### 判断

成立

### 证据

`lib/engine.py:273-277`：

```python
def save_state(meeting_dir: Path, state: dict[str, Any]) -> None:
    path = meeting_dir / "meeting_state.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
```

直接写入目标文件，非 atomic write（先写临时文件再 rename）。若写入过程中断（断电/kill），`meeting_state.json` 可能变为空文件或不完整 JSON。

### 风险

会议状态损坏，无法恢复。

### 建议

使用 atomic write 模式：

```python
import tempfile
with tempfile.NamedTemporaryFile(dir=meeting_dir, suffix=".tmp", delete=False) as tmp:
    json.dump(state, tmp, ...)
    tmp_path = tmp.name
os.replace(tmp_path, path)
```

### 优先级

P1

---

## 问题 15：`fetch_equity.py` 使用 Yahoo Finance 非公开 API

### 判断

成立

### 证据

`scripts/fetch_equity.py:22-23`：

```python
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?..."
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
```

Yahoo Finance 已在 2024 年起限制此类非官方 API 访问（添加 consent/cookie 验证、rate limit）。当前可能已不稳定。

### 风险

数据获取随时可能失败，触发 fallback 到"数据缺失"模式。

### 建议

1. 添加 retry + exponential backoff
2. 考虑切换到 yfinance 库或备用数据源
3. 缓存最近一次成功获取的数据

### 优先级

P2

---

## 问题 16：`INVESTMENT_AGENDA` 硬编码 10 轮固定议程

### 判断

成立

### 证据

`lib/engine.py:70-145`：`INVESTMENT_AGENDA` 为硬编码的 10 轮问题列表，每轮指定固定 guest（`qwen`、`laguna`、`north`、`mimo`、`nemo`）。日期引用 `"截至2026年7月9日"` 已过期。

### 风险

- 议程无法通过配置修改
- 日期硬编码导致每次运行都引用过期时间
- guest 名称变更（如别名重构）需修改代码

### 建议

迁移到 `config/investment_agenda.yaml`，日期使用动态注入（`{{current_date}}`）。

### 优先级

P2

---

## 问题 17：`__pycache__` 被提交

### 判断

成立

### 证据

`.gitignore` 包含 `__pycache__/`，但 `find` 结果显示 `lib/__pycache__/` 目录存在多个 `.pyc` 文件。虽然 `.gitignore` 规则存在，但若这些文件在 `.gitignore` 添加前已被跟踪，则仍存在于 Git 历史中。

### 风险

仓库膨胀、无关噪音。

### 建议

确认 `__pycache__` 未被 Git 跟踪（`git ls-files | grep pycache`）。如已跟踪，执行 `git rm -r --cached lib/__pycache__`。

### 优先级

P3

---

## 问题 18：`dedupe_guest_output.py` 的去重逻辑脆弱

### 判断

成立

### 证据

`scripts/dedupe_guest_output.py:10-25`：

```python
def dedupe(text: str) -> str:
    for marker in MARKERS:
        first = text.find(marker)
        if first == -1:
            continue
        second = text.find(marker, first + len(marker))
        if second != -1:
            return text[:second].rstrip() + "\n"
    half = len(text) // 2
    if half > 80 and text[:half].strip() == text[half:].strip():
        return text[:half].rstrip() + "\n"
```

- 仅检查"判断："标记的第二次出现就截断 — 如果模型合理地两次使用"判断："（如不同子段落），会错误截断
- 精确对半比较仅在完全重复时有效，部分重复不处理

### 风险

真实 guest 输出被错误截断，丢失有效内容。

### 建议

改为检测连续重复块而非标记匹配；或添加置信度阈值。

### 优先级

P3

---

## 最终总结

| 维度 | 评分 |
|------|------|
| **项目整体健康度** | **42 / 100** |
| **架构成熟度** | **35 / 100** |
| **技术债等级** | **高** |
| **安全风险等级** | **中**（无外部攻击面，但本地命令注入和数据损坏风险存在） |
| **是否建议立即发布** | **否** — 需先修复 P0/P1 问题 |

### 必须修复的问题（P0/P1）

| # | 问题 | 优先级 |
|---|------|--------|
| 2 | 并发写入 claims.jsonl 无锁保护 | P0 |
| 3 | tmux TUI 命令注入 | P1 |
| 4 | CLI 失败静默降级为 Mock | P1 |
| 8 | 无测试、无依赖声明 | P1 |
| 12 | `cmd_init` 默认配置引用已下线模型 | P1 |
| 14 | `meeting_state.json` 无原子写入 | P1 |

### 可以延期处理的问题（P2/P3）

| # | 问题 | 优先级 |
|---|------|--------|
| 1 | engine.py 上帝文件拆分 | P2 |
| 5 | 硬编码投资报告内容 | P2 |
| 7 | Guest 别名映射重复 | P2 |
| 9 | 模板注入风险 | P2 |
| 10 | 并行 prompt 无交叉引用 | P2 |
| 15 | Yahoo Finance API 不稳定 | P2 |
| 16 | INVESTMENT_AGENDA 硬编码 | P2 |
| 6 | `utc_now()` 重复定义 | P3 |
| 11 | Magic Numbers | P3 |
| 13 | 自动选嘉宾算法简单 | P3 |
| 17 | `__pycache__` 可能已跟踪 | P3 |
| 18 | dedupe 逻辑脆弱 | P3 |

### 最值得称赞的设计

1. **Claim Lifecycle V0.2**（`claim_lifecycle.py`）：append-only ledger + rebuildable index 的设计非常干净，事件溯源（event sourcing）模式正确，`fold_claims` 折叠逻辑清晰
2. **审计链路完整性**：每个 guest 的 prompt / raw / summary.md / summary.json / error 独立存储，可追溯
3. **Owner 控制权设计**：`owner_required` 暂停机制、`continue`/`stop`/`view`/`ask` 交互设计合理
4. **Mock 模式**（`COUNCIL_MOCK=1`）：允许离线测试流程，设计意图正确

### 最需要重构的模块

**`lib/engine.py`** — 3171 行的上帝文件必须拆分。建议按问题 1 的方案分阶段进行：先拆出 `reports.py`（最大的独立代码块）和 `mock.py`（与真实路径无耦合），再拆 `commands/` 和 `subprocess_runner.py`。拆分过程中补充测试，确保不引入回归。

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
