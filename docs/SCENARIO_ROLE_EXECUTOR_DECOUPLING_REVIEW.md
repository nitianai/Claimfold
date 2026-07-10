# Scenario / Role / Executor Decoupling Review

**项目：** Claimfold Council Engine  
**阶段：** P0 耦合审查（实施前）  
**日期：** 2026-07-10  
**结论：** **可以实施** — 在保留旧路径的前提下，以增量方式接入四层分离，风险可控。

---

## 1. 执行摘要

Council Engine 已具备多模型调用、Research Semantic Loop、Meeting State、Claim Lifecycle、Owner Gate、并行执行与报告留痕。当前瓶颈不是缺功能，而是 **Guest ID、Role、Executor、Scenario 混为一体**：

| 概念 | 今天实际承载 | 问题 |
|------|-------------|------|
| **Guest** (`guests.yaml` 键) | 角色 + 模型 CLI + 实例 ID + 路径前缀 | 换模型要改 YAML 且常改 `role` 文案 |
| **Scenario** | `meeting_mode` 三值 + Python 硬编码 `INVESTMENT_AGENDA` | 新场景必须改代码 |
| **Role** | `role_id` 字段存在但未独立；`role` 文本含品牌名 | 同 Role 无法绑不同 Executor |
| **Executor** | `command` 字符串；`model` 字段引擎不读 | 命令与模型双写、易漂移 |

**关键发现：**

1. Python 中 **无** `if guest == "grok"` 分支，但大量 **Guest ID 硬编码**（议程、焦点规则、fallback、报告模板）。
2. **`model` 字段从未被引擎读取**；实际调用只看 `command`（`cli_runner.invoke_cli`）。
3. **Investment 模式 Prompt 路由 Bug**：`output_format=json` 优先于 `investment.md`，导致 `prompts/guest/investment.md` 在当前默认路径下 **不可达**。
4. `role_id` 已部分用于 JSON challenge 路由，但未成为独立配置层。
5. 旧会议数据（25+ meetings、`claims.jsonl`）与新架构 **可兼容**，不必迁移历史。

---

## 2. 当前耦合点清单

### 2.1 Guest = Role = Executor 三合一体（P0）

**位置：** `config/guests.yaml`

每条 guest 记录同时包含：

```yaml
codex:
  role_id: logic_auditor          # 语义角色
  role: "Codex Local — …"         # 人类标签 + 品牌
  model: "codex/gpt-5.6-sol"      # 未使用
  command: "bash scripts/run_codex_guest.sh"  # 实际执行
  guest_type: llm
  model_tier: local
  timeout_seconds: 180
  allow_parallel: true
```

**影响：** 更换 Codex 模型或把 `logic_auditor` 绑到 Qoder，必须编辑 guest 记录或新增 guest 键；无法「同 Role、不同 Executor」仅靠启动参数完成。

**功能型 Guest 键名耦合：**

| 特殊键 | 用途 | 文件 |
|--------|------|------|
| `summarizer` | 摘要器 | `parsers/summary.py:271` |
| `reporter` | 终稿报告 | `lifecycle.py:62` |
| `context_collector` | 市场上下文 | `daily_context.py:55-57` |

`guest_roster()` 通过键名跳过 `summarizer`/`reporter`（`guests.py:25-31`），属于隐式角色约定。

---

### 2.2 场景逻辑硬编码（P0）

| 耦合点 | 文件 | 说明 |
|--------|------|------|
| 投资议程 10 轮 | `lib/council/config.py:26-109` | 每轮绑定 `guest: qwen/laguna/north/mimo/nemo` |
| 投资精炼问题 | `config.py:103-109` | `INVESTMENT_REFINE_QUESTIONS` |
| 模式→状态映射 | `commands/meeting_start.py:35-51` | `standard/investment/research` 决定 `output_format`、`round_mode`、`max_rounds` |
| 投资自动停止 | `prompts.py:59-92` | 情景关键词、`stale_round_limit` |
| 投资报告生成 | `runtime_ext.py:555-736` | Scenario A/B/C、硬编码委员 ID |
| 实验报告叙事 | `runtime_ext.py:739-916` | 提及 qwen/north/mimo |
| 日频默认嘉宾 | `config.py:24` | `DAILY_DEFAULT_GUESTS = ("grok", "codex", "qoder")` |

**模式矩阵（当前）：**

| `--mode` | `meeting_mode` | `output_format` | `round_mode` | 主 Runner | Prompt 模板 |
|----------|----------------|-----------------|--------------|-----------|---------------|
| `standard` | standard | json | serial | `run` | `json.md` |
| `investment` | investment | json | serial | `run-auto` | `json.md`（非 investment.md） |
| `research` | research | research | parallel | `run-parallel` | `research.md` |

---

### 2.3 Guest ID 参与业务决策（P0）

| 类型 | 文件 | 示例 |
|------|------|------|
| 别名映射 | `runtime_ext.py:25-47` | `grok→laguna`, `macro→qwen`, `geo→laguna` |
| 遗留映射 | `config.py:131-139` | `LEGACY_GUEST_MAP` |
| 焦点选嘉宾 | `runtime_ext.py:49-103` | 关键词→`("qwen","nemo","north")` 等 |
| 议程指定发言人 | `config.py` INVESTMENT_AGENDA | `"guest": "qwen"` |
| Fallback 链 | `lifecycle.py:62` | `reporter` → fallback `qwen` |
| | `daily_context.py:55-57` | `context_collector` → `mimo` → `nemo` |
| | `daily.py:161-164` | 日频结论优先 `qoder` → `codex` → `laguna` |
| artifact 迁移 | `state_store.py:97-159` | 按 guest 名重命名 raw/summary |
| CLI select | `meeting_run.py`, `daily_run.py` | `resolve_guest_alias` |

**说明：** 无 `if guest == "grok"`，但 **Guest ID 等价于参会实例 + 角色 + 执行器**，业务层到处引用 ID。

---

### 2.4 Prompt 与模型/场景耦合（P0/P1）

**模板路由**（`prompts.py:39-46`）：

```python
def guest_template_path(state):
    if is_research_mode(state):      return research.md
    if is_json_mode(state):          return json.md      # ← investment 也走这里
    if is_investment_mode(state):    return investment.md  # 不可达
    return template.md
```

**Prompt 组装链：**

```
meeting_state → guest_template_path(mode)
             → build_prompt_context / build_research_prompt_context
             → render_template({ guest_role, role_id, topic, state… })
             → invoke_cli(guest_cfg["command"])
```

- `guest_role` 来自 `guests.yaml` 的 `role` 字段（常含模型品牌）。
- **同一 `role_id` 不因 Executor 变化而改变职责文本** — 因为职责写在 guest 记录里。
- `prompts/reports/investment_report.md` 硬编码 `qwen/hy3/north/mimo/nemo`（`hy3` 已过时）。

**Parallel runner 假设**（`runners/parallel.py:90`）：LLM guest 一律 `generate_research_prompt()`，与 scenario 无关。

---

### 2.5 模型名参与行为选择（P1 — 仅在配置层）

Python **不读** `model` 字段。但配置层双重绑定：

```yaml
model: "hermes-grok/grok-4.3"
command: "opencode run -m hermes-grok/grok-4.3 --auto"
role: "Grok 4.3 — 地缘与政策风险"
```

换模型 = 改 `command` + 通常改 `role` 文案。脚本型 Executor（`run_codex_guest.sh`）将模型藏在脚本内，配置层不可见。

---

### 2.6 数据结构与留痕耦合（P1）

| 结构 | Guest 耦合方式 |
|------|----------------|
| `meeting_state.json` | `next_speaker`, `guest_summaries` 键为 guest ID |
| `history[].guest` | 发言记录按 guest ID |
| `raw/round-NNN-<guest>.md` | 文件名含 guest ID |
| `selected_guests` | 并行轮次显式 guest 列表 |
| Claim `actor` | `guest:codex` 格式 |

新架构需：**artifact 路径可继续用 participant_id 或保留 guest_id 作兼容别名**；`meeting_plan.json` 记录 `role_id + executor_id` 冻结绑定。

---

## 3. 最小迁移方案

### 3.1 原则

1. **不删除旧模式**：`--mode standard|investment|research` 继续工作。
2. **新路径叠加**：`--scenario <id>` 走 Scenario 引擎；无 `--scenario` 时走现有逻辑。
3. **guests.yaml 保留为兼容入口**，通过 **LegacyAdapter** 在启动时展开为 `Executor + Participant`。
4. **不大改 Runner 骨架**：Serial/Parallel 改为读 `meeting_plan.json` 的 participants，而非 `guests.yaml` 键。
5. **Prompt 组装抽一层**：`PromptComposer(scenario, role, stage, state)` 替代 `guest_template_path` + guest `role` 字段。

### 3.2 分阶段实施（与任务书对齐）

| 阶段 | 内容 | 预估改动量 |
|------|------|-----------|
| **P1** | 配置模型 + loader + 校验 | ~6 新模块，~400 行 |
| **P2** | `--scenario` / `--bind` / `--bindings` + `meeting_plan.json` | `meeting_start.py`, `builder.py` |
| **P3** | `PromptComposer` 动态组装 | `prompts.py` 重构（保留旧函数作 wrapper） |
| **P4** | 三个场景 YAML + roles 目录 | 纯配置 + 少量 stage 驱动逻辑 |
| **P5** | LegacyAdapter + 测试 | `guests.py` 扩展，tests/fixtures |

### 3.3 旧模式 → 新架构映射

| 旧 | 新 |
|----|-----|
| `guests.yaml` 键 `codex` | Executor `codex` + 默认绑定 `logic_auditor→codex` |
| `role_id: logic_auditor` | `roles/common/logic_auditor.yaml` |
| `--mode investment` | Scenario `fund-investment`（或 legacy alias） |
| `--mode research` | 通用 research scenario 或 `fund-investment` 子集 |
| `select codex qoder` | `selected_participants` 或 `--bind` 已冻结在 plan 中 |
| `GUEST_ALIASES` | 仅 CLI 解析层；映射到 `executor_id` 而非 guest 键 |

### 3.4 修复项（随 P3 一并处理）

- **Prompt 路由**：Scenario 指定 `prompt_template`；不被 `output_format` 覆盖。
- **Investment agenda**：迁入 `scenarios/fund-investment.yaml` 的 `stages`；阶段引用 `role_id`，不引用 `qwen`。
- **`model` 字段**：Executor 配置为唯一来源；`command` 由 `type + command[]` 组装。

---

## 4. 数据结构

### 4.1 ExecutorDefinition

```python
@dataclass
class ExecutorDefinition:
    executor_id: str
    type: Literal["cli", "script", "opencode"]
    command: list[str]          # 数组，非 shell 字符串
    model: str | None           # 展示/日志用；opencode 类可写入 -m
    capabilities: list[str]
    timeout_seconds: int
    enabled: bool
    cwd: str | None = None      # 默认项目 ROOT
```

### 4.2 RoleDefinition

```python
@dataclass
class RoleDefinition:
    role_id: str
    name: str
    purpose: str
    responsibilities: list[str]
    boundaries: list[str]
    required_inputs: list[str]
    output_contract: dict       # format, max_chars, required_fields
    authority: dict             # can_recommend, can_decide, can_execute
    prompt_fragment: str | None # 可选；或指向 roles/<id>.md
```

### 4.3 ScenarioDefinition

```python
@dataclass
class ScenarioDefinition:
    scenario_id: str
    name: str
    purpose: str
    required_roles: list[str]
    optional_roles: list[str]
    stages: list[StageDefinition]
    decision_policy: dict
    owner_actions: list[str]
    termination: dict
    prompt_base: str | None     # 场景级约束（如「不得执行交易」）
    legacy_mode: str | None     # 兼容：investment/research/standard
```

```python
@dataclass
class StageDefinition:
    id: str
    name: str
    actors: list[str]           # role_id 或 "owner"
    stage_prompt: str | None
```

### 4.4 ParticipantBinding & MeetingPlan

```python
@dataclass
class ParticipantBinding:
    role_id: str
    executor_id: str

@dataclass
class MeetingPlan:
    meeting_id: str
    scenario_id: str
    topic: str
    participants: list[dict]    # participant_id, role_id, executor_id
    stages: list[dict]          # 自 scenario 复制并冻结
    decision_policy: dict
    bindings_source: str        # cli | file | legacy
    created_at: str
```

**冻结规则：** 会议启动后 `meeting_plan.json` 不变；全局 `executors.yaml` 改动不影响进行中的会议。

### 4.5 运行时：Participant vs Guest

```python
# 会议运行时
participant_id: str           # "architect-01" — artifact 前缀
role: RoleDefinition          # 职责、契约
executor: ExecutorDefinition  # CLI 调用
legacy_guest_id: str | None   # 兼容旧 artifact 命名（可选）
```

---

## 5. 目录结构

```
config/
  guests.yaml              # 保留：legacy 入口 + max_parallel
  executors.yaml           # 新增：Executor 定义（command 数组）
  bindings/                # 可选默认绑定
    fund-default.yaml
    embedded-default.yaml
    project-default.yaml

roles/
  common/
    moderator.yaml
    adversarial_reviewer.yaml
    recorder.yaml
  investment/
    macro_analyst.yaml
    fund_analyst.yaml
    portfolio_recommender.yaml
    ...
  embedded/
    embedded_architect.yaml
    firmware_engineer.yaml
    ...
  project/
    architect.yaml
    implementation_engineer.yaml
    ...

scenarios/
  fund-investment.yaml
  embedded-development.yaml
  project-development.yaml

lib/council/
  plan/                    # 新增包
    models.py              # dataclass 定义
    loaders.py             # YAML 加载 + 校验
    composer.py            # PromptComposer
    legacy.py              # guests.yaml → Executor + Binding
    validators.py          # 启动校验（required role、enabled executor）
  commands/
    meeting_start.py       # 扩展 --scenario --bind --bindings

meetings/<id>/
  meeting_state.json       # 保留
  meeting_plan.json        # 新增：冻结计划

tests/
  fixtures/
    fund-bindings.yaml
    embedded-bindings.yaml
    project-bindings.yaml
  test_plan_loaders.py
  test_scenario_start.py
  test_decoupling.py
  test_legacy_compat.py
```

---

## 6. 兼容策略

### 6.1 旧会议

- 无 `meeting_plan.json` 的会议：继续用 `meeting_state.json` 中的 `meeting_mode` / `next_speaker` / guest ID。
- `migrate_guest_names()` 保留，用于 artifact 重命名。
- Claim `actor: guest:codex` 格式保留；新会议可写 `actor: participant:architect-01` 或双写。

### 6.2 旧 CLI

| 命令 | 行为 |
|------|------|
| `./council.sh start -t "..."` | 不变（standard） |
| `./council.sh start --mode investment` | 不变；内部可委托 `scenario=fund-investment` + legacy bindings |
| `./council.sh start --mode research` | 不变 |
| `./council.sh select codex qoder` | 解析为 executor/participant；无 scenario 时等同 legacy |
| `./council.sh run` / `run-parallel` | 读 `meeting_plan.json`（有则新路径，无则旧路径） |

### 6.3 LegacyAdapter（guests.yaml → Plan）

启动时若未指定 `--scenario` 且无 `--bind`：

1. 从 `guests.yaml` 为每个 enabled guest 生成默认 `ParticipantBinding(role_id=guest.role_id, executor_id=guest_id)`。
2. `executor_id` 同名条目写入虚拟 executor 表（`command` 从字符串拆分为数组）。
3. `meeting_plan.json` 标记 `bindings_source: legacy`。

这样 **旧测试与旧会议脚本无需立即修改**。

### 6.4 三个新场景与旧模式关系

| 新 Scenario | 可映射旧模式 | 备注 |
|-------------|-------------|------|
| `fund-investment` | `--mode investment` | 议程从 `INVESTMENT_AGENDA` 迁入 stages |
| `embedded-development` | 无 | 纯新场景 |
| `project-development` | 无 | 纯新场景；可覆盖最近一次 P0 审阅类会议 |

Research 模式保留为 **通用 parallel semantic loop**，不强制对应单一 scenario。

---

## 7. 修改文件清单

### 7.1 新增

| 文件 | 用途 |
|------|------|
| `config/executors.yaml` | Executor 定义 |
| `scenarios/*.yaml` ×3 | 场景 |
| `roles/**/*.yaml` ×~25 | 角色（common + 三场景最小集） |
| `lib/council/plan/models.py` | 数据结构 |
| `lib/council/plan/loaders.py` | 加载器 |
| `lib/council/plan/validators.py` | 启动校验 |
| `lib/council/plan/composer.py` | Prompt 组装 |
| `lib/council/plan/legacy.py` | 兼容层 |
| `tests/fixtures/*-bindings.yaml` | 验收夹具 |
| `tests/test_decoupling.py` 等 | 验收测试 |

### 7.2 修改（最小触及）

| 文件 | 改动 |
|------|------|
| `lib/council/cli_parser/builder.py` | `start` 增加 `--scenario`, `--bind`, `--bindings` |
| `lib/council/commands/meeting_start.py` | 生成 `meeting_plan.json` |
| `lib/council/prompts.py` | `PromptComposer` 接入；修复 template 优先级 |
| `lib/council/guests.py` | `load_executors()`, `resolve_participant()` |
| `lib/council/runners/serial.py` | 读 plan participants |
| `lib/council/runners/parallel.py` | 读 plan；按 role 而非 guest 选 prompt |
| `lib/council/cli_runner.py` | `invoke_executor(command: list[str])` |
| `lib/runtime_ext.py` | `FOCUS_RULES` 改为 role 关键词（P5 可选） |

### 7.3 暂不修改

| 文件 | 原因 |
|------|------|
| `lib/claim_lifecycle.py` | Claim 逻辑与解耦正交 |
| `lib/council/lifecycle.py` | 报告生成可后续按 scenario 分支 |
| `scripts/run_*_guest.sh` | 已是 Executor 适配器；迁入 executors.yaml 引用 |
| 历史 `meetings/*` | 只读兼容 |

### 7.4 配置演进（guests.yaml）

短期：**保留** `guests.yaml` 作为 `max_parallel` + legacy guest 入口。  
中期：新增 `executors.yaml`；guest 记录逐步瘦身为 `{ executor_id, default_role_id }` 或弃用。  
不在本次删除 `guests.yaml`。

---

## 8. 测试计划

### 8.1 解耦测试（任务书 §十二）

| # | 测试 | 实现方式 |
|---|------|----------|
| 1 | 同 `architect` Role 绑 Claude / Qwen，代码不变 | `test_decoupling.py::test_same_role_different_executors` |
| 2 | 同 `claude` Executor 绑 architect / macro_analyst / adversarial_reviewer | `test_same_executor_multiple_roles` |
| 3 | 改 bindings YAML 无需改 Python | 夹具文件 + 启动断言 |
| 4 | Scenario 文件无模型名 | `test_scenario_no_model_names` |
| 5 | Role 文件无 CLI 命令 | `test_role_no_commands` |
| 6 | Executor 无会议流程 | `test_executor_no_stages` |

### 8.2 场景启动测试

```bash
./council.sh start --scenario fund-investment \
  --topic "某基金未来一周研究" \
  --bindings tests/fixtures/fund-bindings.yaml

./council.sh start --scenario embedded-development \
  --topic "SAMD21 VD 中断实验设计" \
  --bindings tests/fixtures/embedded-bindings.yaml

./council.sh start --scenario project-development \
  --topic "Owner Dashboard 开发" \
  --bindings tests/fixtures/project-bindings.yaml
```

断言：

- `meeting_plan.json` 存在且 required_roles 均已绑定
- 生成的 `prompts/round-001-*.prompt.md` 含 scenario 名、role purpose、stage 名
- 不同 executor 的 prompt 中 **role 职责段落相同**
- `decision_policy.council_can_decide == false`
- stages 含 `owner_gate` 或等效阶段

### 8.3 错误测试

| 输入 | 期望 |
|------|------|
| 缺少 required role | `SystemExit` + 明确错误 |
| 绑定不存在 executor | 拒绝 |
| executor `enabled: false` | 拒绝 |
| 不存在 role_id / scenario_id | 拒绝 |
| 重复 `--bind role=ex` | 拒绝 |
| role 缺 `output_contract` | 拒绝（校验器） |
| scenario 设 `council_can_execute: true` 于不可逆操作 | 拒绝或降级为 recommend |

### 8.4 回归测试

- 现有 `tests/run_tests.py` 25 项全部通过
- `./council.sh start --mode research` + `run-parallel` smoke（mock relax 可选）
- `./council.sh start --mode investment` 议程轮次不回归
- `claim verify` 仍通过

---

## 9. 风险与缓解

| 风险 | 严重性 | 缓解 |
|------|--------|------|
| Runner 双路径（plan vs legacy）分支膨胀 | 中 | `resolve_runtime_plan()` 单入口；旧逻辑收敛到 LegacyAdapter |
| artifact 路径从 guest ID 改为 participant ID | 中 | 保留 `legacy_guest_id` 字段；或 `round-001-architect-01` 命名 |
| Investment 议程迁移遗漏轮次 | 中 | 对照测试：旧 `INVESTMENT_AGENDA` 与新 stages 文本 hash 一致 |
| Prompt 组装回归 | 高 | 快照测试：对比 research 模式 prompt 结构（节标题） |
| executors.yaml 与 scripts 重复 | 低 | 脚本型 executor 仅 `command: ["bash","scripts/run_codex_guest.sh"]` |
| FOCUS_RULES 仍指向 guest ID | 低 | P5 改为 role 关键词；短期保留 legacy |
| 实施范围膨胀 | 中 | 严格禁止模板继承、DB、DI 框架；三场景最小角色集 |

---

## 10. 是否可以实施

**结论：可以实施。**

**理由：**

1. 引擎骨架（Runner、State、Claim、CLI invoke）已稳定，解耦是 **配置抽取 + 启动冻结**，不需重写 Engine。
2. `role_id` 与 `meeting_mode` 已是半成品抽象，迁移有锚点。
3. 兼容策略清晰：旧会议只读、旧 CLI 默认路径不变、`guests.yaml` 保留。
4. P0 路径修复已完成，测试基础设施（25 tests）可承接新用例。
5. 已知 Bug（investment.md 不可达）可在 P3 一并修复。

**建议实施顺序：**

```
P1 loaders + validators（无行为变更）
  → P2 meeting_plan.json + CLI 参数（可启动、可校验、尚未跑轮）
  → P3 PromptComposer（接入 research 场景先试）
  → P4 三场景 YAML + roles
  → P5 LegacyAdapter + 全量验收测试
```

**预估工作量：** 2–3 个集中实施会话（不含模板扩写与报告美化）。

---

## 附录 A：耦合矩阵速查

| 类型 | 严重度 | 主要位置 |
|------|--------|----------|
| Guest=Role=Executor 混合 | P0 | `config/guests.yaml` |
| 议程绑 Guest ID | P0 | `config.py` INVESTMENT_AGENDA |
| 焦点规则绑 Guest ID | P0 | `runtime_ext.py` FOCUS_RULES |
| 别名参与解析 | P0 | `runtime_ext.py`, `config.py` |
| 模式/template 顺序 Bug | P0 | `prompts.py` |
| 投资报告硬编码 | P0 | `runtime_ext.py` |
| Guest fallback 链 | P1 | `lifecycle.py`, `daily.py` |
| `model` 字段闲置 | P1 | `guests.yaml` |
| Serial 轮换忽略 agenda speaker | P1 | `serial.py` |

## 附录 B：启动接口（目标态）

```bash
# 场景 + 绑定文件
./council.sh start \
  --scenario project-development \
  --topic "Owner Dashboard 开发" \
  --bindings config/bindings/project-default.yaml

# 场景 + 内联绑定
./council.sh start \
  --scenario fund-investment \
  --topic "未来一周半导体基金走势" \
  --bind moderator=qwen_local \
  --bind macro_analyst=claude \
  --bind adversarial_reviewer=grok

# 旧路径（继续有效）
./council.sh start --mode research --topic "..."
```

## 附录 C：核心原则（实施检查清单）

- [ ] Scenario 决定会议怎么推进
- [ ] Role 决定席位必须完成什么
- [ ] Executor 决定由哪个模型/工具执行
- [ ] Binding 决定本场谁坐哪个席位
- [ ] Council 只能 Recommendation，Owner 才能 Decision
- [ ] 场景文件不含 Claude/Grok/Codex 等模型名
- [ ] Role 文件不含 CLI 命令
- [ ] Executor 配置不含会议流程
- [ ] 新代码不扩大 `Guest = Role = Model` 耦合

---

*审查完成。确认后可按 P1→P5 顺序实施。*