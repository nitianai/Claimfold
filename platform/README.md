# Mission OS（任务操作系统）— Platform（平台层）契约 v0.1

> **状态：** Phase 4 已交付（2026-07-11）；Phase 5 硬化见 [`docs/V2_BACKLOG.md`](../docs/V2_BACKLOG.md)
> **包名：** `missionos`  
> **消费方：** `apps/research_council`（Claimfold Research Council（研究委员会）会议应用）  
> **硬约束：** Platform（平台层）**不得** import `council`、`runtime_ext`、`claim_lifecycle`

Mission OS（任务操作系统）是可复现、可审计的多会话工作流最小基础设施层。  
App（应用层）拥有领域语义；Platform（平台层）拥有存储原语、安全 I/O、子进程调用与 Scenario Plan（场景计划）编译。

设计依据：[`docs/PLATFORM_APP_SPLIT.md`](../docs/PLATFORM_APP_SPLIT.md)

**文档规范：** 本项目文档以中文为主；专用术语首次出现须标注英文及中文，例如 Event Sourcing（事件溯源）、Projection（投影）。

---

## 1. 事实源矩阵（Single Source of Truth，单一事实源）

| 对象 | 唯一事实源（Canonical Store） | 投影（Projection） | 写入权 | 备注 |
|------|------------------------------|-------------------|--------|------|
| Claim（主张）事件 | `claims/claims.jsonl` | `claims/claims_index.json` | 仅 App（应用层）经 `missionos.ledger.append_event` 写 JSONL | 索引（Index）可删除重建，**无独立索引写 API** |
| Meeting Plan（会议计划） | `meetings/<id>/meeting_plan.json` | — | App 在 Session（会话）启动时冻结写入 | 已启动 Session 不受全局 Config（配置）变更影响 |
| Meeting State（会议状态） | `meetings/<id>/meeting_state.json` | 由 `summary.json` + `history` 派生 | App merge/rebuild（合并/重建） | Owner（所有者）命令可编辑部分字段 |
| 全局 Config（配置） | `config/roles.yaml`、`executors.yaml`、`scenarios/`、`bindings/` | — | 仅启动前输入 | 不得追溯性（retroactively）改变已冻结 Plan |
| Session 指针（Pointer） | `.current_meeting` | — | App start/stop | Platform 只提供指针读写原语 |
| Artifact（制品） | `prompts/`、`raw/`、`summaries/`、`errors/` | — | App Runner（运行器）写入 | Council（委员会）专用目录布局，非 Platform 通用契约 |

---

## 2. 依赖规则（Dependency Rule）

```
apps/research_council  →  missionos
missionos              ↗  不得依赖 App（应用层）包
```

**`platform/missionos/` 内禁止 import：**

- `council`、`council.*`
- `runtime_ext`、`claim_lifecycle`、`engine`
- 将 Council ROOT 硬编码为 App Config 路径

强制执行：`./scripts/check_platform_boundary.sh`

---

## 3. 模块边界（Module Boundaries）

### 3.1 `missionos.utils` — 通用工具

无领域词汇的通用辅助函数。

| 符号 | 职责 |
|------|------|
| `utc_now()` | UTC 时间戳字符串 |
| `atomic_write_json(path, data)` | Atomic Write（原子写）JSON 文件 |
| `validate_meeting_id(id)` | 格式校验（`meet-YYYYMMDD-HHMMSS`） |
| `resolve_meeting_path(meetings_dir, id)` | Path Traversal Safe（路径穿越安全）解析 |
| `strict_cli_enabled()` | Fail-Closed（失败即关闭）CLI 门禁 |
| `clamp_int(...)` | 有界整数转换 |

**不属于 Platform：** `INVESTMENT_AGENDA`（投资议程）、Guest Alias（嘉宾别名）、Focus Rules（焦点规则）。

---

### 3.2 `missionos.ledger` — Event Store（事件存储）

Append-Only（只追加）事件账本。**不含 Claim（主张）专用 Projection（投影）。**

| 符号 | 职责 |
|------|------|
| `append_event(ledger_path, event)` | 带锁追加 JSONL |
| `load_events(ledger_path)` | 读取全部事件（坏行策略：静默跳过） |
| `with_ledger_lock(ledger_path)` | 排他 flock 上下文（Linux V0.1） |
| `validate_envelope(event)` | 最小 `{event, ts}` + JSON 可序列化校验 |

| 符号 | 职责 |
|------|------|
| `replay(events, projector)` | 将 App 提供的 Projector（投影器）应用于事件列表 |

**App 拥有（经 `ClaimLedgerAdapter`（主张账本适配器））：**

- `fold_claims`、`rebuild_claim_index`、`next_claim_id`、`append_promote_event`
- `PROMOTE` / `RESPOND` / `RETIRE` 事件语义
- `TENTATIVE` / `CONTESTED` / `RETIRED` 状态机

---

### 3.3 `missionos.session` — Session Store（会话存储）

参数化 Session I/O。**不含 `meeting_state` 字段语义。**

```python
SessionStore(
    root: Path,
    pointer_name: str = ".current_meeting",
    sessions_dir_name: str = "meetings",
    state_filename: str = "meeting_state.json",
)
```

| 方法 | 职责 |
|------|------|
| `load_state(session_dir)` | 读取 JSON 状态文件 |
| `save_state(session_dir, data)` | Atomic Write（原子写）状态文件 |
| `read_pointer()` / `write_pointer(session_id)` | 活跃 Session 指针 |
| `resolve_session_dir(session_id)` | `sessions_dir` 下安全路径 |

`missionos.session.paths`：

| 符号 | 职责 |
|------|------|
| `safe_artifact_path(session_dir, kind, participant_id, round_id)` | 安全路径拼接 |

**App 拥有：**

- `get_current_meeting_dir`、`rebuild_state_from_summaries`
- `artifact_paths_research`（Guest 命名的 Council 目录布局）
- `confirmed_points` / `conflicts` / `open_questions` 语义合并

---

### 3.4 `missionos.executor` — Command Invoker（命令调用器）

纯 Subprocess（子进程）原语。**不含 mock / strict / guest 策略。**

```python
@dataclass
class InvokeResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool

def invoke_command(
    command: str,
    *,
    stdin: str = "",
    cwd: Path | None = None,
    timeout_seconds: int = 600,
) -> InvokeResult: ...
```

**App 拥有（`CouncilExecutorPolicy`（委员会执行策略））：**

- `COUNCIL_MOCK`、Strict Fail-Closed（严格失败即关闭）、Mock Fallback（模拟降级）
- `guest`、`kind`、`round_num` 参数
- `fetch_equity_context_block`

---

### 3.5 `missionos.plan` — Plan Compiler（计划编译器）

仅 compile / read / write / validate（编译/读/写/校验）。**不含运行时 Guest 映射。**

**属于 Platform：**

- `models`、`compiler`、`loader`、`reader`、`writer`、`validators`
- `paths.resolve_plan_inputs(root, scenario_id, bindings_path)`
- `start.build_meeting_plan`、`cli_bindings.parse_cli_bindings`
- Schema（模式）：`missionos/schemas/meeting_plan.schema.json`，经 `importlib.resources` 读取

**明确不属于 Platform：**

- `plan/runtime.py`（`build_plan_actor_queue`、`resolve_executor_to_guest`）
- 任何对 `council.guests` 的 import

---

### 3.6 `missionos.formatting` — 最小格式化

仅领域中立的格式化函数。

| Platform | App |
|----------|-----|
| `round_tag`、`render_template`、`format_list` | `format_guest_summaries`、`artifact_paths`（guest/json_mode） |

---

## 4. 明确仅属 App（永不迁入 Platform）

| 当前位置 | 原因 |
|----------|------|
| `lib/council/plan/runtime.py` | import `council.guests.resolve_executor_to_guest` |
| `lib/claim_lifecycle.py` → `fold_claims` | Claim Projection（主张投影）状态机 |
| `lib/council/mock.py` | Council JSON / Research 输出结构 |
| `lib/council/cli_runner.py` → `invoke_cli` | Guest / Mock / Strict 策略 |
| `lib/runtime_ext.py` | Metrics（指标）、报告、`FOCUS_RULES`、`GUEST_ALIASES` |
| `lib/council/prompts.py` | Prompt（提示词）路由、`prior_claims` 注入 |
| `lib/council/commands/*` | CLI 领域命令处理器 |

### 4.1 允许的 App 层 Shim（Allowlist，Phase 4 后保留）

> **原则：** Platform 不得 import App；App **可以** 薄封装 Platform 并注入本 App 的 `DATA_ROOT` / 配置路径。下列文件**不是**双实现，禁止删除或迁入 Platform。

| 路径 | 类型 | 职责 |
|------|------|------|
| `apps/research_council/lib/council/plan/paths.py` | Path Inject（路径注入） | 将 `council.config` 的 `ROOT` / `scenarios/` / `bindings/` 注入 `missionos.plan.paths.PlanLayout` |
| `apps/research_council/lib/council/plan/__init__.py` | Re-export + Wrapper（重导出 + 封装） | 重导出 `missionos.plan.*`；`build_meeting_plan` 默认 `default_plan_layout()` |
| `apps/research_council/lib/council/adapters/*` | Adapter（适配器） | Claim / Plan runtime / Executor / Session 领域语义 |
| `apps/research_council/lib/council/__init__.py` | Lazy Re-export | 避免 import 环；不复制 Platform 逻辑 |

**门禁：** `./scripts/check_platform_boundary.sh` 扫描 `platform/missionos` 与 `apps/platform_smoke`；`tests/platform/test_shim_purity.py` 确保已删除的 compat 文件不复现。

---

## 5. 实施阶段摘要（Implementation Phases）

| 阶段 | 交付物 |
|------|--------|
| **0** | 本契约 + Boundary Test（边界测试）（不移动业务代码） |
| **1** | 抽取纯核（`utils`、`ledger.store`、`session`、`executor`、`plan` 不含 runtime）+ Thin Shim（薄兼容层） |
| **2** | App Adapter（适配器）（`claim_ledger`、`plan_runtime`、`executor_policy`、`session_adapter`） |
| **3** | 物理搬迁至 `apps/research_council/`；运行时数据留仓库根 |
| **4** | Shim Burn-down（兼容层销毁）、Config Externalization（配置外置） |
| **5** | Dummy App fixture（`apps/platform_smoke`）、契约收口、可选 `missionos-v0.1` tag |

**第二消费方验证：** `apps/platform_smoke` — 仅依赖 `missionos`，不得 import `council`。

---

## 6. 门禁清单（Gate Checklist）

Phase 1–4 已满足；合并 Phase 5 变更前须满足：

- [x] `import missionos` 不得 import `council` 或 `runtime_ext`
- [x] `./scripts/check_platform_boundary.sh` 通过
- [x] 全仓库仅有 **一个** 真实 `append_event` 实现
- [x] `plan/runtime.py` 在 App `adapters/plan_runtime.py`，不在 Platform
- [x] `./council.sh` 不变；`scripts/ci.sh` 全绿
- [x] `apps/platform_smoke` 通过 `tests/platform/test_platform_smoke_app.py`

---

## 7. 版本说明（Versioning）

| 版本 | 含义 |
|------|------|
| `missionos 0.1.0`（`platform/pyproject.toml`） | Platform 初次抽取（Phase 1） |
| Git tag `missionos-v0.1` | Phase 5 封板快照（monorepo 提交，包版本 0.1.0） |
| Plan Schema `1.0` | `meeting_plan.schema.json`（PR1） |

Platform V0.1 仅保证 **Linux `fcntl` flock**。跨平台锁不在范围内。

---

## 8. 安装（Installation）

推荐从仓库根执行 editable install（与 `scripts/ci.sh` 第 0 步一致）：

```bash
./scripts/install_editable.sh
# 安装 missionos（platform/）+ research-council（apps/research_council/）
```

无 `pip` 时脚本与 CI 回退 `PYTHONPATH=platform:apps/research_council/lib`；生产/开发环境建议配置 `pip` 以锁定依赖解析。