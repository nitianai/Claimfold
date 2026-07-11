# Claimfold Platform（平台层）/ App（应用层）拆分方案

> **状态：** Phase 4（阶段 4）已交付（shim 销毁 + `focus_rules` / `executor-guest` 配置化）；Platform / App 拆分完成
> **日期：** 2026-07-11  
> **评审：** CONDITIONAL GO（有条件通过）— 契约先行，禁止直接大规模 `git mv`  
> **目标：** 将 Claimfold 拆分为 Mission OS（任务操作系统）最小基础 Platform（平台层）与 Research Council（研究委员会）会议 App（应用层），拆分后 `./council.sh` 仍可正常运行。

**文档规范：** 见 [`docs/STRUCTURE.md`](STRUCTURE.md) — 正文中文，专用术语须标注 `English（中文）`。

---

## 0. 现状摘要

| 维度 | 现状 |
|------|------|
| 入口 | `council.sh` → `lib/engine.py` → `council.cli` |
| 代码量 | `lib/` 约 50 个 Python 文件；`lib/council/` 已是主包 |
| 核心横切能力 | Event Sourcing（事件溯源）账本（`claim_lifecycle.py`）、Session（会话）状态（`state_store.py`）、Plan Compiler（计划编译器）（`council/plan/`）、Executor（执行器）（`cli_runner.py`） |
| 领域逻辑 | 会议工作流（`commands/`、`runners/`）、Prompt（提示词）路由（`prompts.py`）、投资议程（`config.py: INVESTMENT_AGENDA`）、Guest（嘉宾）选择（`runtime_ext.py: FOCUS_RULES`） |
| 测试基线 | **12 个测试模块**（`tests/run_tests.py`），约 **86 个 `test_*` 函数**；以 `make ci` 输出为准 |
| 已有方向 | `docs/SCENARIO_ROLE_EXECUTOR_DECOUPLING_REVIEW.md` 与 `council/plan/` 是 Platform（平台层）化的 PR1 成果 |

**关键耦合点（必须在拆分中处理）：**

1. `lib/council/config.py` 同时承担 ROOT 路径、投资议程、嘉宾别名 — 需拆为 Platform 路径抽象 + App 领域配置
2. `claim_lifecycle.py` 混合通用 Ledger（账本）与 Claim（主张）Projection（投影）/晋升策略 — 纵向切分，**禁止**把 `fold_claims` 固化进 Platform
3. `state_store.py` 的 `rebuild_state_from_summaries` 依赖 Council（委员会）语义解析器 — 通用 JSON 读写归 Platform，重建逻辑留 App
4. `lib/council/plan/runtime.py` 反向依赖 `council.guests` — **不得**迁入 Platform
5. `cli_runner.py` / `mock.py` 含 Guest/Mock/Fallback Policy（降级策略）— 归 App，Platform 只提供 Subprocess（子进程）原语
6. `runtime_ext.py`（931 行）是 App 巨石；`artifact_paths_research` 是 Council Artifact（制品）契约，不归 Platform

**拆分原则：**

- Platform 层极简、稳定、确定性强，只包含其他 App 也可能复用的核心能力
- App 层负责具体业务（会议工作流、角色体系、研究模式等）
- 拆分后 Claimfold 必须仍然能正常运行（通过 import 或依赖 platform）
- 优先考虑可审计性、Event Sourcing（事件溯源）、Session/Context（会话/上下文）管理、Claim Lifecycle（主张生命周期）等现有特性
- **禁止复制实现**：全仓库每个核心写路径只能有一个真实实现（Single Source of Truth，单一事实源）
- **契约先行**：`platform/README.md` 与事实源矩阵在 Phase 0 冻结，再动代码

**进入实施的前置条件（CONDITIONAL GO，有条件通过）：**

1. `missionos.plan` 不含 `runtime.py`，且不 import `council.*` / `runtime_ext`
2. `missionos.ledger` 只有 Append-Only Store（只追加存储）/ Envelope（事件封套）/ Lock（锁）/ Replay（重放）接口，不含 Claim Projection State Machine（主张投影状态机）
3. Phase 1 禁止「复制 + Shim（兼容层）」双实现；旧路径只能 Thin Wrapper（薄封装）/ Re-export（重导出）
4. Platform README / API Boundary（API 边界）表 / 事实源矩阵已完成（中文文档）
5. Import Boundary（导入边界）、Single Source of Truth（单一事实源）、Schema Resource（模式资源）测试已加入 CI 骨架

---

## 1. 事实源矩阵（Single Source of Truth，单一事实源）

| 对象 | 唯一事实源 | 投影/派生 | 写入权 | 备注 |
|------|-----------|----------|--------|------|
| Claim（主张）事件 | `claims/claims.jsonl` | `claims/claims_index.json` | 仅 App 经 `missionos.ledger.append_event` 写 JSONL | Index（索引）可删除重建，**无独立写路径** |
| Meeting Plan（会议计划） | `meetings/<id>/meeting_plan.json` | — | 启动时冻结写入 | 已启动 Session 不受全局 Config 变更影响 |
| Meeting State（会议状态） | `meetings/<id>/meeting_state.json` | 由 `summary.json` + `history` 派生 | App merge/rebuild | 允许 Owner 命令直接编辑部分字段 |
| 全局 Config（配置） | `config/roles.yaml`、`executors.yaml`、`scenarios/`、`bindings/` | — | 启动前输入 | 不得追溯性改变已冻结 Plan |
| Session Pointer（会话指针） | `.current_meeting` | — | App start/stop | Platform 只提供 Pointer 读写原语 |
| Guest Artifact（嘉宾制品） | `prompts/`、`raw/`、`summaries/`、`errors/` | — | Runner 写入 | Council Artifact 契约，非 Platform 通用 |

---

## 2. 目标总体架构图

### 2.1 Phase 1–2 过渡期（代码仍在根 `lib/`，Adapter 先落地）

```
Claimfold/
├── council.sh                          # 入口不变
├── platform/
│   ├── pyproject.toml                    # name = "missionos"
│   ├── README.md                         # ★ Phase 0 冻结的 API 契约
│   └── missionos/
│       ├── utils.py
│       ├── formatting.py                 # 仅 round_tag / render_template / format_list
│       ├── ledger/
│       │   ├── store.py                  # append/load/lock/envelope
│       │   └── replay.py                 # replay(events, projector) 接口
│       ├── session/
│       │   ├── store.py                  # SessionStore 参数化原语
│       │   └── paths.py                  # safe_artifact_path 原语（无 guest 语义）
│       ├── executor/
│       │   └── invoke.py                 # CommandInvoker → InvokeResult
│       └── plan/                         # compile/read/write/validate ONLY
│           ├── models.py, compiler.py, loader.py
│           ├── reader.py, writer.py, validators.py
│           ├── paths.py, start.py, cli_bindings.py
│           └── (不含 runtime.py)
├── lib/                                  # App 仍在根目录（Phase 3 再搬迁）
│   ├── engine.py
│   ├── runtime_ext.py
│   ├── meeting_quality.py
│   ├── claim_lifecycle.py                # Phase 1: thin wrapper；Phase 2: 拆入 council/claims/
│   └── council/
│       ├── adapters/                     # ★ Phase 2 新增
│       │   ├── claim_ledger.py           # ClaimLedgerAdapter, fold_claims, rebuild_claim_index
│       │   ├── plan_runtime.py           # ← lib/council/plan/runtime.py
│       │   ├── executor_policy.py        # invoke_cli + mock/strict fallback
│       │   └── session_adapter.py        # get_current_meeting_dir 等 App 语义封装
│       ├── plan/runtime.py               # Phase 1 前移至 adapters/plan_runtime.py
│       ├── mock.py                       # 留 App（Council 输出结构）
│       ├── cli_runner.py                 # CouncilExecutorPolicy + fetch_equity
│       ├── claims/                       # policy / injection / respond / index
│       ├── commands/, runners/, parsers/, ...
│       └── ...
├── config/, prompts/, scenarios/, scripts/
├── claims/, meetings/, .current_meeting   # ★ Phase 3 前不搬家
└── tests/
    ├── platform/                         # missionos + boundary tests
    └── app/                              # council integration tests
```

### 2.2 终态（Phase 3 后）

```
Claimfold/
├── council.sh                            # 转发 → apps/research_council/council.sh
├── platform/missionos/                   # 同上
├── apps/research_council/                # App 物理归拢
│   ├── council.sh
│   ├── lib/council/...
│   ├── config/, prompts/, scenarios/, scripts/
│   └── pyproject.toml                    # depends: missionos
├── claims/, meetings/, .current_meeting   # 仍在仓库根（或 COUNCIL_DATA_ROOT）
└── tests/platform/ + tests/app/
```

**依赖方向（严格单向）：**

```
apps/research_council  →  platform/missionos
platform/missionos     ↗  不依赖 council / runtime_ext / claim_lifecycle
```

---

## 3. Platform 层模块（Mission OS）

| 模块 | 职责 | 为什么放 Platform |
|------|------|-------------------|
| `missionos.utils` | `utc_now`、`atomic_write_json`、`validate_meeting_id`、`resolve_meeting_path`、`strict_cli_enabled` | 原子写、路径安全、fail-closed |
| `missionos.ledger.store` | append-only JSONL、`fcntl` 锁、event envelope 校验 | 通用 Event Sourcing 存储 |
| `missionos.ledger.replay` | `replay(events, projector) -> projection` 接口 | 投影逻辑由 App 注入，Platform 不固化 Claim 状态机 |
| `missionos.session.store` | `SessionStore(root, pointer_name, sessions_dir, state_filename)` 参数化 JSON 读写 | 与 `meeting_state` 字段语义无关 |
| `missionos.session.paths` | `safe_artifact_path(session_dir, kind, participant_id, round_id)` | 安全路径拼接，不含 research/guest 目录约定 |
| `missionos.executor.invoke` | `CommandInvoker(command, stdin, cwd, timeout) -> InvokeResult` | 纯 subprocess，无 mock/strict/guest |
| `missionos.plan` | compile / read / write / validate / `resolve_plan_inputs(root, ...)` | PR1 场景无关编译器；**不含 runtime.py** |
| `missionos.formatting` | `round_tag`、`render_template`、`format_list` | 无领域词的最小格式化 |
| `schemas/meeting_plan.schema.json` | Plan JSON Schema（`importlib.resources` 读取） | 平台契约 |

**Platform 明确不包含：**

- `plan/runtime.py`、`resolve_executor_to_guest`、`plan_actor_queue`
- `fold_claims`、`rebuild_claim_index`、`next_claim_id`、`append_promote_event`
- `mock.py`、`generate_mock_*`、`COUNCIL_MOCK` policy
- `invoke_cli` 的 guest/kind/round_num 参数与 fallback 逻辑
- `artifact_paths_research`、`.current_meeting` 硬编码语义
- `guests.yaml`、嘉宾别名、`FOCUS_RULES`、`INVESTMENT_AGENDA`
- `confirmed_points` / `conflicts` / `open_questions` 语义
- Prompt 模板、报告叙事、Claim 晋升/注入规则

---

## 4. App 层模块（Research Council）

| 模块 | 职责 | 迁移来源 |
|------|------|----------|
| `council.sh` + `engine.py` | CLI 入口 | 根 `council.sh`、`lib/engine.py` |
| `council.adapters.claim_ledger` | `ClaimLedgerAdapter`、`fold_claims`、`rebuild_claim_index`、`append_promote_event` | `lib/claim_lifecycle.py` |
| `council.adapters.plan_runtime` | `build_plan_actor_queue`、`plan_guest_roster`、`advance_plan_speaker` | `lib/council/plan/runtime.py` |
| `council.adapters.executor_policy` | `invoke_cli`、strict/mock fallback、`mock_mode_enabled` | `lib/council/cli_runner.py` |
| `council.adapters.session_adapter` | `get_current_meeting_dir`、`artifact_paths_research` | `state_store` + `runtime_ext` |
| `council.claims.*` | 晋升策略、注入契约、RESPOND 解析、`verify_three_meeting_chain` | `lib/claim_lifecycle.py` 领域部分 |
| `council.mock` | Council JSON/research/market mock 生成 | `lib/council/mock.py` |
| `council.config` | ROOT、议程、模板路径、`LEGACY_GUEST_MAP` | `lib/council/config.py` |
| `council.guests` | roster、mode、`resolve_executor_to_guest` | `lib/council/guests.py` |
| `council.commands.*` | 全部 CLI 命令 | `lib/council/commands/*` |
| `council.runners.*` | 串行/并行执行 | `lib/council/runners/*` |
| `council.parsers.*` | summary/JSON 解析、state merge | `lib/council/parsers/*` |
| `council.prompts` | prompt 路由、prior_claims 注入 | `lib/council/prompts.py` |
| `council.state_store` | `rebuild_state_from_summaries`、legacy guest 修复 | `lib/council/state_store.py` |
| `runtime_ext.py` | metrics、报告、嘉宾选择、`GUEST_ALIASES`、`FOCUS_RULES` | `lib/runtime_ext.py` |
| `meeting_quality.py` | 实验质量对比 | `lib/meeting_quality.py` |
| `config/`、`prompts/`、`scenarios/`、`scripts/` | 领域配置与工具 | 根目录对应路径 |

---

## 5. 关键文件切分细则

### 5.1 `claim_lifecycle.py`

| 函数/常量 | 归属 |
|-----------|------|
| `load_events`, `append_event`, `_with_ledger_lock`, `ensure_claims_dir`, `ledger_path`, `claims_dir` | **Platform** `missionos/ledger/store.py` |
| `replay` 通用接口 | **Platform** `missionos/ledger/replay.py` |
| `next_claim_id`, `append_promote_event`, `fold_claims`, `rebuild_index`, `load_index` | **App** `council/adapters/claim_ledger.py` + `council/claims/index.py` |
| `NON_PROMOTION_MARKERS`, `validate_promotion_candidate`, `select_claims_for_injection`, `format_prior_claims_for_prompt`, `parse_claim_responses_from_raw`, `verify_three_meeting_chain` | **App** `council/claims/` |

App 晋升流程：校验（`claims/policy`）→ ID 分配 + append（`ClaimLedgerAdapter`）→ `missionos.ledger.append_event`。

### 5.2 `state_store.py`

| 函数 | 归属 |
|------|------|
| 参数化 `load_json_state` / `save_json_state` / `read_pointer` / `resolve_session_dir` | **Platform** `missionos/session/store.py` |
| `get_current_meeting_dir`, `rebuild_state_from_summaries`, `repair_legacy_guest_names` | **App** `council/adapters/session_adapter.py` + `council/state_store.py` |

### 5.3 `cli_runner.py`

| 函数 | 归属 |
|------|------|
| `CommandInvoker`（纯 subprocess，返回 returncode/stdout/stderr/timeout） | **Platform** `missionos/executor/invoke.py` |
| `invoke_cli`, `invoke_script`, `mock_mode_enabled`, `_fail_or_mock_cli`, `fetch_equity_context_block` | **App** `council/adapters/executor_policy.py` + `council/cli_runner.py` |

### 5.4 `plan/` 包

| 文件 | 归属 |
|------|------|
| `models`, `compiler`, `loader`, `reader`, `writer`, `validators`, `paths`, `start`, `cli_bindings` | **Platform** `missionos/plan/` |
| `runtime.py`（依赖 `council.guests`） | **App** `council/adapters/plan_runtime.py` |

`validators.py` schema 路径改为：

```python
from importlib.resources import files
_SCHEMA = files("missionos").joinpath("schemas/meeting_plan.schema.json")
```

### 5.5 `formatting.py`

| 函数 | 归属 |
|------|------|
| `round_tag`, `render_template`, `format_list` | **Platform** |
| `format_guest_summaries`, `artifact_paths`（json_mode guest 命名） | **App** |

---

## 6. 迁移执行步骤

### Phase 0 — Contract Freeze（契约冻结）/ Dependency Audit（依赖审计）（阻塞项，不动业务代码）

**目标：** 冻结 Platform API（平台 API），建立架构 Boundary Test（边界测试）骨架；文档须为中文并标注术语。

| 步骤 | 具体操作 |
|------|----------|
| 0.1 | 编写 `platform/README.md`：ledger / session / executor / plan 最小 API |
| 0.2 | 本文档 §1 事实源矩阵写入 `platform/README.md` |
| 0.3 | 依赖审计：确认 `plan/runtime.py`、`fold_claims`、`mock.py` 归属 App |
| 0.4 | 新增 `tests/platform/test_import_boundary.py`：`import missionos` 不得触发 `council` |
| 0.5 | 新增 `tests/platform/test_single_impl.py`：骨架（Phase 1 后启用） |
| 0.6 | 新增 `scripts/check_platform_boundary.sh`：`rg "from council\|import council\|runtime_ext" platform/` 必须为空 |
| 0.7 | Owner（所有者）评审确认 → 进入 Phase 1 |
| 0.8 | `docs/STRUCTURE.md` 写入文档书写规范（中文 + 术语标注） |

**完成标准：** `platform/README.md`（中文）合入；Boundary Test 骨架存在；无大规模文件移动。

---

### Phase 1 — Extract Pure Platform Core（抽取纯平台核心，只抽无 App 依赖的纯核）

**目标：** `pip install -e platform/` 可用；`./council.sh` 路径与行为不变。

| 步骤 | 具体操作 |
|------|----------|
| 1.1 | `mkdir -p platform/missionos/{ledger,session,executor,plan}` |
| 1.2 | 创建 `platform/pyproject.toml`（含 `package-data` 打包 schemas） |
| 1.3 | `git mv lib/utils.py platform/missionos/utils.py` |
| 1.4 | `git mv lib/council/plan/{models,compiler,loader,reader,writer,validators,paths,start,cli_bindings}.py` → `platform/missionos/plan/` |
| 1.5 | **保留** `lib/council/plan/runtime.py` 在 App（或移至 `lib/council/adapters/plan_runtime.py`） |
| 1.6 | `git mv schemas/meeting_plan.schema.json platform/missionos/schemas/`（随包发布） |
| 1.7 | **移动**（非复制）`claim_lifecycle` 中 `load_events`/`append_event`/锁 → `platform/missionos/ledger/store.py` |
| 1.8 | **移动** `state_store` 中 JSON 读写原语 → `platform/missionos/session/store.py` |
| 1.9 | **移动** `formatting` 中 `round_tag`/`render_template`/`format_list` → `platform/missionos/formatting.py` |
| 1.10 | 新建 `platform/missionos/executor/invoke.py`（从 `cli_runner` 提取纯 subprocess，**不**移 mock） |
| 1.11 | 改 `platform/missionos/plan/*` import；`validators` 用 `importlib.resources` |
| 1.12 | **根 `lib/` 只留 thin wrapper**（禁止复制实现）： |
| | `lib/utils.py` → `from missionos.utils import *` |
| | `lib/claim_lifecycle.py` → re-export `missionos.ledger` + 保留 App 函数直至 Phase 2 |
| | `lib/council/plan/__init__.py` → re-export `missionos.plan` + 保留 `runtime` 在 App |
| 1.13 | `tests/platform/` 迁移 `test_utils.py`、`test_plan_*.py`；启用 boundary + single-impl 测试 |
| 1.14 | `make ci` 全绿 |

**完成标准：**

- `./council.sh` 不变；`python3 -c "import missionos"` 成功
- 全仓库仅 **一个** `append_event` 真实实现
- `platform/` 内无 `council` / `runtime_ext` import
- 12 模块 / ~86 cases 全过

---

### Phase 2 — App Adapter Layer（应用适配层，仍在根 `lib/`，不搬目录）

**目标：** 领域逻辑全部经 Adapter 调用 Platform；Claim/Plan/Executor 边界清晰。

| 步骤 | 具体操作 |
|------|----------|
| 2.1 | 创建 `lib/council/adapters/{claim_ledger,plan_runtime,executor_policy,session_adapter}.py` |
| 2.2 | 移动 `plan/runtime.py` → `adapters/plan_runtime.py` |
| 2.3 | 拆分 `claim_lifecycle.py` → `council/claims/{policy,injection,respond,index}.py` + `adapters/claim_ledger.py` |
| 2.4 | 实现 `ClaimLedgerAdapter`：`fold_claims`、`rebuild_claim_index`、`append_promote_event` |
| 2.5 | 实现 `CouncilExecutorPolicy`：包装 `CommandInvoker` + mock/strict |
| 2.6 | `mock.py` 留 App；`cli_runner.py` 改为调用 `executor_policy` |
| 2.7 | `artifact_paths_research` 移入 `session_adapter.py` |
| 2.8 | 全局 import 切换（**禁止**重跑 `split_engine.py`） |
| 2.9 | **前置**：`GUEST_ALIASES` 外置 `config/guest_aliases.yaml`，打破 `config ↔ runtime_ext` 环 |
| 2.10 | 删除 `lib/claim_lifecycle.py` shim（逻辑已在 adapters/claims） |
| 2.11 | `make ci` + README mock 流程 + `claim verify` |

**完成标准：** `claim verify` 通过；`COUNCIL_MOCK=1 run-parallel` 通过；无双实现残留。

---

### Phase 3 — Layout Move（目录布局搬迁，物理搬迁 App）

**目标：** `apps/research_council/` 归拢；运行时数据兼容。

| 步骤 | 具体操作 |
|------|----------|
| 3.1 | `git mv lib/council apps/research_council/lib/council`（及 engine/runtime_ext 等） |
| 3.2 | `git mv config prompts scenarios scripts apps/research_council/` |
| 3.3 | `git mv council.sh apps/research_council/council.sh` |
| 3.4 | 根 `council.sh` 转发：`exec "$(dirname "$0")/apps/research_council/council.sh" "$@"` |
| 3.5 | **`claims/`、`meetings/`、`.current_meeting` 留仓库根**（或 `COUNCIL_DATA_ROOT`  env） |
| 3.6 | `council.config.ROOT` 指向 `apps/research_council`；`MEETINGS_DIR`/`CLAIMS_DIR` 可用 `DATA_ROOT` 覆盖 |
| 3.7 | `apps/research_council/pyproject.toml`：`dependencies = ["missionos"]` |
| 3.8 | 更新 `scripts/ci.sh`、`Makefile`、`tests/` 路径 |
| 3.9 | 验证历史 `evidence_refs`（`meet-xxx/raw/...`）仍可解析 |

**完成标准：** README 快速开始不变；旧 `claims.jsonl` / `meetings/` 无需迁移即可读写。

---

### Phase 4 — Compatibility Burn-down（兼容层销毁）

**目标：** 删除 shim、配置化、可选跨 App 验证。

| 步骤 | 具体操作 |
|------|----------|
| 4.1 | 删除所有 deprecation 已过期的 shim |
| 4.2 | `FOCUS_RULES` 外置 `config/focus_rules.yaml` |
| 4.3 | `EXECUTOR_TO_GUEST` 移入 `config/bindings/` |
| 4.4 | 更新 `docs/STRUCTURE.md`、根 `README.md` 架构图 |
| 4.5 | 删除/归档 `scripts/split_engine.py`、`scripts/split_core.py` |
| 4.6 | 可选：最小 dummy App fixture，验证 `missionos.plan` 编译 + `ledger.append_event` 非 Claim 事件 |
| 4.7 | 可选：`missionos` git tag / 私有 PyPI 发布 |

**完成标准：** 无 shim；alias/focus 配置化；shim 删除前所有外部入口已更新并经过一个发布周期。

---

## 7. import 迁移对照表

| 旧 import | 新 import |
|-----------|-----------|
| `from utils import atomic_write_json` | `from missionos.utils import atomic_write_json` |
| `from claim_lifecycle import load_events, append_event` | `from missionos.ledger.store import load_events, append_event` |
| `from claim_lifecycle import fold_claims, rebuild_index` | `from council.adapters.claim_ledger import fold_claims, rebuild_claim_index` |
| `from claim_lifecycle import validate_promotion_candidate` | `from council.claims.policy import validate_promotion_candidate` |
| `from council.plan import compile_meeting_plan` | `from missionos.plan import compile_meeting_plan` |
| `from council.plan.runtime import build_plan_actor_queue` | `from council.adapters.plan_runtime import build_plan_actor_queue` |
| `from council.state_store import load_state, save_state` | `from missionos.session.store import ...`（经 `session_adapter`） |
| `from council.cli_runner import invoke_cli` | `from council.adapters.executor_policy import invoke_cli` |
| `from council.formatting import round_tag` | `from missionos.formatting import round_tag` |
| `from runtime_ext import select_guests_for_focus` | 不变（App 内） |

---

## 8. 架构边界测试（每个 Phase 门禁）

```bash
# import boundary
python3 -c "import missionos"   # 不得 import council / runtime_ext

# platform 包内无 App 依赖
./scripts/check_platform_boundary.sh

# single source of truth（Phase 1 后启用）
python3 tests/platform/test_single_impl.py

# shim 只 re-export（Phase 1 期间）
python3 tests/platform/test_shim_purity.py
```

---

## 9. 潜在风险与缓解措施

| 风险 | 影响 | 缓解 |
|------|------|------|
| **双实现 / 双写路径** | 违反 Claim 单一事实源 | 禁止复制；single-impl 测试；只 git mv + wrapper |
| **plan/runtime 迁入 Platform** | Platform 反向依赖 App | Phase 0 明确排除；放 `adapters/plan_runtime.py` |
| **fold_claims 固化进 Platform** | 未来 Task ledger 被迫继承 Claim 状态机 | 投影逻辑全在 App；Platform 只提供 `replay(projector)` |
| **PYTHONPATH 断裂** | CLI 无法启动 | Phase 1–2 根 `lib/` 不变；Phase 3 根 `council.sh` 转发 |
| **ROOT / 数据路径错位** | 找不到 config、旧 meeting | Phase 3 前 `claims/meetings` 不搬；`COUNCIL_DATA_ROOT` 可选 |
| **schema 路径层级变化** | plan validate 失败 | `importlib.resources`；`test_plan_schema.py` |
| **config ↔ runtime_ext 环** | 隐蔽跨层耦合 | Phase 2 前置外置 `guest_aliases.yaml` |
| **历史 evidence_refs 断裂** | claim verify 失败 | 保持 `meetings/<id>/` 相对路径约定 |
| **fcntl 非 Linux** | 锁失效 | V0.1 仅保证 Linux；跨平台另开 issue（非阻塞） |
| **重复 split 脚本** | 覆盖手维护模块 | 禁止重跑 `split_engine.py` / `split_core.py` |

---

## 10. 迁移后验证（测试命令）

### 10.1 安装与静态检查

```bash
cd Claimfold

# Phase 1 后
pip install -e platform/
python3 -c "from missionos.ledger.store import append_event; from missionos.plan import compile_meeting_plan; print('platform ok')"
./scripts/check_platform_boundary.sh

# Phase 3 后
pip install -e platform/ -e apps/research_council/
python3 -c "import sys; sys.path.insert(0,'apps/research_council/lib'); import engine; print('app ok')"
```

### 10.2 单元 / 回归测试

```bash
make ci

python3 tests/platform/run_tests.py
python3 tests/app/run_tests.py
# 基线：12 模块，~86 test_* 函数，0 failed
```

### 10.3 端到端 CLI（离线 mock）

```bash
./council.sh init
./council.sh start "测试议题：未来一周黄金走势" --mode research
./council.sh context "黄金、美元、美债"
./council.sh select claude grok nemotron
COUNCIL_MOCK=1 ./council.sh run-parallel
./council.sh metrics
./council.sh audit-summary 1 qwen
./council.sh claim list
./council.sh stop
```

### 10.4 Claim 生命周期三场会议链

```bash
./council.sh claim promote --from-state conflicts[0] \
  --domain finance --subjects gold,USD --regime-tags risk-off \
  --valid-from 2026-07-10 --valid-until 2026-08-01 \
  --evidence raw/round-001-qwen.md

./council.sh start "黄金一周走势" --mode research
COUNCIL_MOCK=1 ./council.sh run-parallel
./council.sh claim retire clm-000001
./council.sh claim verify
```

---

## 11. PR 切分建议

| Phase | 核心产出 | 建议 PR |
|-------|----------|---------|
| **Phase 0** | 契约文档 + boundary 测试骨架 | PR-0: `docs(platform): contract freeze` |
| **Phase 1** | `missionos` 纯核 + thin wrapper | PR-A: `feat(platform): extract pure core` |
| **Phase 2** | App adapters + claims 拆分 | PR-B: `feat(app): adapter layer` |
| **Phase 3** | `apps/research_council` 物理搬迁 | PR-C: `feat(app): layout move` |
| **Phase 4** | shim 销毁 + 配置外置 | PR-D: `chore: compatibility burn-down` |

每个 PR 合入前：`make ci` + README mock 流程；Phase 2 起加 `claim verify`。

---

## 12. 与现有路线图的对齐

| 现有文档/产物 | 与本方案关系 |
|---------------|-------------|
| Codex 架构评审（2026-07-11） | 采纳 CONDITIONAL GO；本稿为 v2 修订 |
| `docs/STRUCTURE.md` | Phase 4 更新为双产物结构 |
| `docs/SCENARIO_ROLE_EXECUTOR_DECOUPLING_REVIEW.md` | `missionos.plan` 承载 compile 层；runtime 留 App |
| `PR1_FOLLOWUPS.md` Runner dual-path | Phase 2 `plan_runtime` adapter；LegacyAdapter Phase 4 |
| `docs/CLAIM_LIFECYCLE.md` | JSONL 唯一写入源不变；fold/index 明确为 App 投影 |
| `scripts/split_engine.py` / `split_core.py` | 已废弃，Phase 4 归档 |

---

## 13. 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1 | 2026-07-11 | 初稿：Phase 1–3 直接 git mv |
| v2 | 2026-07-11 | Codex 评审修订：新增 Phase 0/4；ledger/plan/executor 边界收紧；禁止双实现；数据目录不搬；契约前置 |
| v2.1 | 2026-07-11 | Phase 0 落地：`platform/README.md`、boundary 脚本、`tests/platform/` |
| v2.2 | 2026-07-11 | 文档规范：正文中文 + 术语 `English（中文）`；`STRUCTURE.md` 增基础要求；`platform/README.md` 中文化 |
| v3.0 | 2026-07-11 | Phase 1 落地：`missionos` 纯核抽取、`council.sh` PYTHONPATH、`append_event` 单实现 |
| v4.0 | 2026-07-11 | Phase 2 落地：`adapters/`、`council/claims/`、`guest_aliases.yaml`、lazy `council.__init__` |
| v4.1 | 2026-07-11 | Phase 3 落地：`apps/research_council/` 搬迁；`APP_ROOT`/`DATA_ROOT` 拆分；根 `council.sh` 转发；CI 88 项 + mock e2e 通过 |
| v5.0 | 2026-07-11 | Phase 4 落地：删除 compat shim；`focus_rules.yaml`、`executor-guest.yaml`；归档 `split_engine`/`split_core`；更新 STRUCTURE/README |