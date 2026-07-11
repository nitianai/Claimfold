# Claimfold 进化方案（可执行规格）

> **状态：** Ready for implementation（Grok Build 可直接开工）  
> **日期：** 2026-07-11  
> **读者：** 实现 Agent / 工程师  
> **原则：** 以 Claimfold 产品语义为主；Mission OS 研究原型（`~/code/research/technology-graph-grok`）仅作**模式参考**，禁止整仓拷贝。  
> **硬约束：**  
> 1. `platform/missionos` **不得** import `council` / `runtime_ext`  
> 2. Claim 账本仍是 `claims/claims.jsonl` 只追加；索引可删可重建  
> 3. **禁止** 自动 PROMOTE LLM 输出进主张账本  
> 4. 每 PR 保持 `make ci` 全绿  

**文档规范：** 正文中文；专用术语首次标注 `English（中文）`。

---

## 0. 一页摘要（给执行者）

| 项 | 内容 |
|----|------|
| **产品是什么** | 多模型研究运行时：可复现会议 + 跨会话试探性主张（Claim），Owner 有控制权 |
| **现在痛点** | Round/Guest 状态难调和；晋升门靠人记；session 事件与 claim 账本边界靠约定；失败/HITL 策略散落；executor 工具策略弱 |
| **进化目标** | 在不重写引擎的前提下，引入控制面级不变量：Round Spec/Status、写路径版本、晋升 CI 门禁、失败策略、HITL 事件化、可选能力/工具策略 |
| **原型参考路径** | `~/code/research/technology-graph-grok/prototypes/mission_os/` + `FREEZE.md` + `design/production-path.md` |
| **不做** | 替换为完整 K8s/Temporal；自动相信模型；把 summary 当 Claim 真理 |

**推荐开工顺序（2026-07-11 Grok + Codex + Claude 审议后）：** PR-A → PR-B → PR-C → **PR-F** → PR-D → PR-E（见 §5、§13）。先做 A+B+C 即可显著提升可审计性与可恢复性。

---

## 1. 背景：两套资产如何分工

### 1.1 Claimfold（本仓库）— 产品与实验场

```
Claimfold/
  platform/missionos/     # Platform：ledger / session / executor / plan
  apps/research_council/  # App：会议、Guest、claim 领域、CLI/Web
  claims/                 # 跨会话主张账本（DATA_ROOT）
  meetings/               # 会议会话与制品
```

已具备：

- Platform / App 拆分 + `check_platform_boundary.sh`
- Claim Lifecycle V0.2：`PROMOTE` / `RESPOND` / `RETIRE` + Non-Promotion List
- Meeting Plan 启动冻结；prompt/raw/summary 审计链
- Owner 闸门（`owner_required` / continue / stop）
- 并行/交互式会议路径

### 1.2 technology-graph-grok 原型 — 模式库（只读参考）

路径：`~/code/research/technology-graph-grok/`

| 原型能力 | 关键文件（参考，勿复制粘贴成第二实现） |
|----------|----------------------------------------|
| Spec/Status Reconcile | `prototypes/mission_os/daemon.py`, `assignment.py` |
| ExpectedVersion 追加存储 | `prototypes/mission_os/event_store.py` |
| Fact Scope / Promotion | `experiments/exp3_fact_promotion/`, `facts.py` |
| FailurePolicy + 补偿 | `mission.py` FailurePolicy |
| HITL interrupt | `mission.py` HitlInterrupt, `HumanInterrupt*` |
| ToolInspection | `tool_policy.py`, `policy_runtime.py` |
| 父子能力派生 | `session.py` |
| 部门配额 | `quota.py` |
| 冻结门禁 | `prototypes/FREEZE.md`, `validate_freeze.py` |
| Outbox worker | `outbox_worker.py`, `filelock.py` |

### 1.3 概念映射（实现时统一话术）

| Mission OS 原型 | Claimfold | 说明 |
|-----------------|-----------|------|
| Mission | Meeting `meet-*` | 一场研究会话 |
| Assignment | Round × GuestSlot | 某轮某嘉宾的一次执行单元 |
| Department Runtime | Guest Executor（CLI） | 推理执行器 |
| Department Result | `raw/` + `summary.json` | 必须可审计 |
| Fact (scoped) | Claim event（TENTATIVE…） | 仅 Owner PROMOTE 进账本 |
| Core stream | `claims/claims.jsonl` | 跨会话权威 |
| Execution / session stream | `meetings/*/events.jsonl` | 不得混入 claims |
| Projection | `claims_index.json`, `meeting_state.json` | 可重建/派生 |
| HITL | `owner_required` + continue | 事件化加强 |
| ToolInspection | executor 调用前策略 | mock/strict 升格 |

---

## 2. 要解决的问题清单

### P1 — 主张可信度（Don't Believe Too Early）

| 问题 | 现象 | 目标 |
|------|------|------|
| P1.1 晋升门难强制 | Non-Promotion List 在文档，CI 覆盖不全 | 每次 `claim promote` 与 CI 用例必拦 mock/无 evidence |
| P1.2 投影被误当可写 | 风险：直接改 `claims_index.json` | 删除 index 后 `rebuild-index` 必须一致；无 index 写 API |
| P1.3 并发写 claim_id | flock 有，缺「版本/期望」语义 | 可选 ledger envelope revision 或 CAS 式 id 分配测试 |

### P2 — 会议可恢复与可调和（Recoverable）

| 问题 | 现象 | 目标 |
|------|------|------|
| P2.1 Round 状态模糊 | 崩溃后难判断哪位 Guest 该重跑 | 每个 GuestSlot：`Pending/Running/Succeeded/Failed` + attempts |
| P2.2 失败策略隐含 | runner 内 fallback/mock 分散 | `meeting_plan` / state 显式 `failure_policy` |
| P2.3 HITL 仅字段 | `owner_required` bool，审计链弱 | session events 记录 raised/resolved |

### P3 — 流隔离与审计（Auditable）

| 问题 | 现象 | 目标 |
|------|------|------|
| P3.1 两账本边界靠约定 | claims vs meeting events | CI 断言事件类型前缀/schema 不交叉 |
| P3.2 Result 契约不统一 | Guest 输出形态多 | Research 路径强制 summary.json schema 校验 |

### P4 — 安全与配额（Safe by default）

| 问题 | 现象 | 目标 |
|------|------|------|
| P4.1 Executor 策略弱 | 子进程策略在 App 各处 | 统一 Inspection：DENY / ALLOW / REQUIRE_OWNER |
| P4.2 并行打满 CLI | run-parallel 无细粒度配额 | 每 executor 并发上限 |

### P5 — 运维（Optional）

| 问题 | 目标 |
|------|------|
| P5.1 账本备份/迁移 | claims.jsonl 导出校验包 |
| P5.2 后台任务与主会议解耦 | daemon 与 webhook 类任务可独立（参考 outbox worker） |

---

## 3. 原型是怎么做的（实现时对照，勿整文件搬运）

### 3.1 Spec/Status + Reconcile

- **Spec** = 期望（谁、做什么、max_retries）  
- **Status** = 观测（phase、generation、observed_generation、attempts、result）  
- **Reconcile**：`observed_generation < generation` 则启动/重试；终态且匹配则不再动  

Claimfold 落地：为每个 `round_id + guest_id` 维护 `GuestSlotStatus`，存在 `meeting_state.json` 的结构化字段或仅由 `events.jsonl` 投影。

### 3.2 ExpectedVersion Append

- 流上 `append(..., expected_revision=N)`，冲突抛 `WrongExpectedVersion`  
Claimfold 落地（轻量）：`claims.jsonl` 保持 JSONL；增加：
  - 事件必填 envelope：`event`, `ts`, `schema_version`
  - 测试：并发 promote 不产生重复 `claim_id`
  - 可选：旁路 `claims.meta.json` 存 `last_event_seq`（若引入 seq）

### 3.3 Fact Scope / Promotion

- Worker 断言不可直接 Owner 可见；需 validate→approve→promote  
Claimfold 已有 Owner-only PROMOTE + Non-Promotion List。补强：
  - 会议内「候选命题」保持在 `meeting_state` / 未晋升  
  - 账本 claim 默认注入 research prompt 仅 `TENTATIVE` 活跃集  
  - **绝不** Summarizer 自动写 claims.jsonl

### 3.4 FailurePolicy

```text
allow_partial     # 有成功则可继续 Owner 决策/收束
all_must_succeed  # 任一 Guest 失败 → 会议标记 failed 或阻止 promote
fail_fast         # 首个失败停止后续 invoke
```

写入 `meeting_plan.json` 或 start 参数，runner 读取。

### 3.5 HITL

- 进入 `AwaitingDecision` 时 `HumanInterruptRaised`  
- 未 resolve 禁止 `record_decision`  
Claimfold：`owner_required=true` 时：
  - append `OwnerInterruptRaised`
  - `claim promote` / 部分 `stop` 路径检查 interrupt 未开则允许；若配置 `hitl_required_for_promote` 则禁止 promote 直到 continue  
  - `continue` → `OwnerInterruptResolved`

### 3.6 ToolInspection

```text
tool → required capability → ALLOW | DENY | REQUIRE_APPROVAL
```

Claimfold：在 `executor` 适配层包装 `invoke_cli`：
  - mock 路径显式标记
  - strict 模式禁止 silent fallback
  - 日志写入 session events

### 3.7 流分离（核心不变量）

| 允许 | 禁止 |
|------|------|
| claims.jsonl ← PROMOTE/RESPOND/RETIRE | claims.jsonl ← raw guest 文本整段 |
| meetings/*/events.jsonl ← floor/message/owner | meeting events 类型名与 claim 事件混用 |
| meeting_state 派生 | 手改 claims_index 作为写入 API |

---

## 4. 目标架构（进化后）

```text
Owner / CLI / Web
        │
        ▼
┌───────────────────────────────────────────┐
│  App: research_council                    │
│  - commands / runners / interactive       │
│  - claim_lifecycle 领域（PROMOTE 策略）    │
│  - GuestSlot reconcile（新）              │
│  - FailurePolicy / HITL 事件（新）        │
└─────────────┬─────────────────────────────┘
              │ 单向依赖
              ▼
┌───────────────────────────────────────────┐
│  Platform: missionos                      │
│  - ledger.append/load/lock/replay         │
│  - session store + events.jsonl           │
│  - executor.invoke                        │
│  - plan compile/read/write                │
│  - （可选）envelope validate 增强         │
└───────────────────────────────────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
claims.jsonl      meetings/<id>/
claims_index.json   events.jsonl
                    meeting_state.json
                    prompts|raw|summaries
```

**Single Source of Truth（单一事实源）不变**（见 `platform/README.md`）。

---

## 5. 分 PR 实施计划（Grok Build 按序做）

每个 PR：**一个主题、可回滚、必须 `make ci` 通过**。  
测试命令默认：

```bash
cd ~/code/projects/Claimfold
make ci
# 或
./scripts/check_platform_boundary.sh
python3 tests/platform/run_tests.py
python3 tests/app/run_tests.py
```

---

### PR-A — 晋升门禁补洞 + 流隔离测试（P1.1 / P3.1）【已收窄】

**解决问题：** Non-Promotion List 的**回归测试**与 claims/meeting **流隔离 CI**；**不重写**现有 `claims/policy.py`。

**现状（审议确认）：** `validate_promotion_candidate` + `cmd_claim_promote` 已接入；`test_claim_lifecycle.py` 已覆盖部分场景。

**改什么：**

1. **不新建** `assert_promotable` 重复实现；必要时在 `policy.py` 增加薄别名或补 1–2 条规则（见下）
2. **收紧证据（可选小改）：** 默认晋升须含 `raw/` 锚点；仅 `summaries/` 或 `context/` 不能单独成立
3. **测试** `tests/app/test_claim_promotion_gates.py`（整合 CLI 路径）：
   - mock 文本必拒；无 evidence 必拒
   - 合法 raw 引用可通过（fixtures）
   - `owner_override` 时 `override_note` 非空（测现有路径，**不新增** override 通道）
4. **测试** `tests/app/test_stream_isolation.py`：
   - `claims.jsonl` 事件名仅 `PROMOTE|RESPOND|RETIRE`
   - `meetings/*/events.jsonl` 不得出现上述 claim 事件名（历史污染则只断言**新写入**或带 cutoff）

**验收：**

- [ ] 流隔离 CI 绿
- [ ] `claim promote` mock 路径 CLI 集成失败
- [ ] `make ci` 绿；Platform 无 claim 语义

**参考：** `CLAIM_LIFECYCLE.md` §1。

---

### PR-B — GuestSlot Spec/Status（P2.1）

**解决问题：** 并行/交互轮次崩溃后无法判断谁成功谁失败。

**单一事实源（三方共识）：** `meetings/<id>/events.jsonl` 追加 Slot 事件；`meeting_state.guest_slots` 为**可重建投影**（与 claims_index 同理）。**v1 不引入** `generation` / `observed_generation`（无 reconcile 循环前仅为冗余状态）。

**数据模型（投影字段 `meeting_state.json`）：**

```json
{
  "guest_slots": {
    "r002:qwen": {
      "round": 2,
      "guest_id": "qwen",
      "phase": "Succeeded",
      "generation": 1,
      "observed_generation": 1,
      "attempts": 1,
      "max_retries": 1,
      "message": "",
      "artifact": {
        "prompt": "prompts/...",
        "raw": "raw/...",
        "summary_json": "summaries/..."
      }
    }
  }
}
```

`phase` 枚举：`Pending` | `Running` | `Succeeded` | `Failed` | `Skipped`

**改什么：**

1. 新模块建议：`apps/research_council/lib/council/slots.py`（纯函数 + 状态更新）
2. `runners/parallel.py` **与** `runners/interactive.py` **共用** `slots.py`（禁止双实现）：
   - invoke 前：`phase=Running`, `attempts+=1`
   - 成功：`Succeeded` + artifact 路径
   - 失败：`Failed`；若 `attempts < max_retries` 可保留 Pending 语义供重跑
3. CLI：`./council.sh status` 打印 slots 摘要；可选 `repair-slots` 从 artifacts 回填
4. 测试：模拟一次成功一次失败的 merge

**验收：**

- [ ] `run-parallel` 后 `guest_slots` 与 raw/summary 文件一致
- [ ] 失败 Guest 不伪装 Succeeded
- [ ] `make ci` 绿

**参考：** 原型 `assignment.py` Phase + `daemon.py` reconcile 语义（Claimfold 可先不做完整 reconcile 循环，只做状态落盘）。

---

### PR-C — FailurePolicy + HITL 事件化（P2.2 / P2.3）

**解决问题：** 失败与 Owner 暂停策略隐含在 runner。

**v1 范围收窄：** 落地 `OwnerInterruptRaised` / `OwnerInterruptResolved` 与 FailurePolicy 三态；**不**在 v1 实现 `require_before_promote` 拦截 promote（延后小 PR）。

**Plan / start 配置：**

```yaml
# meeting_plan 或 start 默认
failure_policy: allow_partial   # allow_partial | all_must_succeed | fail_fast
hitl:
  every_n_rounds: 3             # 已有 -r
  require_before_promote: false # 可选增强
```

**行为：**

| policy | run-parallel 结束时 |
|--------|---------------------|
| `allow_partial` | 有成功即可继续；记录 partial warnings |
| `all_must_succeed` | 任一 Failed → `owner_required=true` 或 meeting 标记 `blocked` |
| `fail_fast` | 首个 Failed 后不再 invoke 同轮剩余 Guest |

**HITL 事件（`meetings/<id>/events.jsonl`）：**

```json
{"event": "OwnerInterruptRaised", "ts": "...", "round": 3, "reason": "every_n_rounds"}
{"event": "OwnerInterruptResolved", "ts": "...", "action": "continue"}
```

- `continue` 命令必须写 `OwnerInterruptResolved`
- 若 `require_before_promote`：`owner_required` 时 `claim promote` 拒绝

**验收：**

- [ ] 三种 policy 各有单测（mock runner）
- [ ] continue 产生 resolved 事件
- [ ] `make ci` 绿

**参考：** 原型 `FailurePolicy`、`HitlInterrupt`、`HumanInterruptRaised/Resolved`。

---

### PR-F — Web / 角色卡与控制面对齐（新增）

**解决问题：** Web UI 已具备角色卡与邀请流；B/C 落地后若不同步，会出现「后端有 slot/HITL，前端仍读旧字段」。

**改什么：**

1. `council_status` / `meeting_payload` 暴露 `guest_slots` 摘要、HITL 状态、partial/failed 提示
2. Web：speaker strip / 在线嘉宾展示 phase、attempt、错误；`owner_required` 与 continue 对齐事件
3. 虚拟嘉宾 `rc-*` 与 Slot 的 `guest_id` 映射规则写入测试
4. 冒烟：`COUNCIL_MOCK=1` + Web API `run-interactive` 后轮询状态

**验收：**

- [ ] parallel 与 interactive 在 Web 上状态一致
- [ ] `make ci` 绿（可加轻量 API 契约测试）

**顺序：** PR-C 之后、PR-D 之前。

---

### PR-D — Executor 策略门（ToolInspection-lite）（P4.1 / P4.2）

**解决问题：** mock/strict/fallback 分散；并行打满。

**改什么：**

1. `council/adapters/executor_policy.py`（或扩展现有）：
   ```python
   def inspect_invoke(ctx) -> Literal["allow", "deny", "require_owner"]:
       ...
   ```
   - `COUNCIL_MOCK=1` → allow 但 result 必须带 mock 标记（已有则对齐）
   - strict：禁止未配置 guest 的 silent 降级
2. 并发：`run-parallel` 使用有界线程池，`max_parallel_guests` 来自 config（默认 3）
3. 拒绝时写 `errors/` + session event `ExecutorDenied`

**验收：**

- [ ] strict 下非法 executor 不 silent success
- [ ] 并行上限可配置并有测试
- [ ] Platform `invoke.py` 保持无业务策略（策略在 App adapter）

**参考：** 原型 `tool_policy.py` + `PolicyAwareRuntime`（思想，不必同名）。

---

### PR-E — 账本 envelope 增强 + 索引不变量 CI（P1.2 / P1.3 / P5.1）

**解决问题：** 投影可写风险；迁移/备份无标准包。

**改什么：**

1. 新事件可选字段：`schema_version: 1`（新旧兼容：缺省视为 1）
2. `claim verify` 扩展：
   - rebuild index 后与磁盘 index 深度比较（或 hash）
   - 事件单调 ts / claim_id 不回退
3. 脚本 `scripts/export_claims_bundle.py`：打包 `claims.jsonl` + 重建后的 index + manifest
4. 测试：删 index → rebuild → verify

**验收：**

- [ ] `claim verify` 覆盖 rebuild 一致性
- [ ] export bundle 可再 import 或至少 verify
- [ ] `make ci` 绿

**参考：** 原型 `store_io.py` export 格式思想；**不要**强行上 SQLite 除非有明确需求。

---

## 6. 非目标（写进 PR 描述，防止 scope creep）

| 非目标 | 原因 |
|--------|------|
| 自动 PROMOTE | 违反 Claimfold 与研究拒绝清单 |
| 把 Temporal/K8s 引入默认路径 | 过重 |
| 重写 interactive 为自由聊天 | 见 `INTERACTIVE_SESSION.md` 已否决 |
| Platform 实现 `fold_claims` | 领域属 App |
| 从 research 原型复制 HTTP 全套 API | Claimfold 已有 CLI/Web/daemon |
| 修改 research 仓克隆 | 只读参考 |

---

## 7. 测试与门禁矩阵

| 门禁 | 命令 | PR |
|------|------|-----|
| Platform 边界 | `./scripts/check_platform_boundary.sh` | 所有 |
| 单测 | `make test` / `make ci` | 所有 |
| 晋升门 | `tests/app/test_claim_promotion_gates.py` | A |
| 流隔离 | `tests/app/test_stream_isolation.py` | A |
| Slots | `tests/app/test_guest_slots.py` | B |
| Policy/HITL | `tests/app/test_failure_policy.py` | C |
| Web 契约 | `tests/app/test_web_control_plane.py`（或扩展现有 web 测试） | F |
| Executor | `tests/app/test_executor_policy.py` | D |
| Ledger | `tests/app/test_claim_verify_rebuild.py` | E |

**手动冒烟（PR-B/C 后）：**

```bash
COUNCIL_MOCK=1 ./council.sh start "进化方案冒烟" --mode research
COUNCIL_MOCK=1 ./council.sh select qwen
COUNCIL_MOCK=1 ./council.sh run-parallel
./council.sh status   # 应见 guest_slots
./council.sh stop
```

---

## 8. 文件触点预估（按 PR）

### PR-A

- `apps/research_council/lib/council/claims/` 或 `adapters/claim_ledger.py`
- `apps/research_council/lib/council/commands/claims.py`
- `tests/app/test_claim_promotion_gates.py`
- `tests/app/test_stream_isolation.py`（可选）

### PR-B

- `apps/research_council/lib/council/slots.py`（新）
- `apps/research_council/lib/council/runners/parallel.py`
- `apps/research_council/lib/council/commands/meeting_*.py`（status 展示）
- `tests/app/test_guest_slots.py`

### PR-C

- `apps/research_council/lib/council/plan` 读取 / `meeting_start`
- `runners/parallel.py`, `commands/meeting_owner.py`
- session events 写入点
- `tests/app/test_failure_policy.py`

### PR-D

- `adapters/executor_policy.py`（扩展）
- `runners/parallel.py` 线程池
- `tests/app/test_executor_policy.py`

### PR-E

- `adapters/claim_ledger.py`, `commands/claims.py`
- `scripts/export_claims_bundle.py`（新）
- `tests/app/test_claim_verify_rebuild.py`

**Platform 尽量少动**；若动 `missionos.ledger`，仅 envelope 校验纯函数，无 claim 语义。

---

## 9. 成功标准（进化完成定义）

1. **可信：** mock/无证据无法默认 promote；Owner override 有审计字段  
2. **可恢复：** 任意中断后 `guest_slots` 能说明每位嘉宾终态  
3. **可审计：** claims 与 meeting events 流隔离有 CI  
4. **可控：** failure_policy 与 HITL 事件可解释、可测试  
5. **边界：** Platform 仍零依赖 App；`make ci` 稳定  
6. **文档：** 本方案 §1.3 映射表与 `CLAIM_LIFECYCLE.md` 不冲突（冲突时以 CLAIM 语义为准）

---

## 10. 给 Grok Build 的开工指令（复制即用）

```text
你在仓库 ~/code/projects/Claimfold 工作。

阅读并严格执行：
- docs/EVOLUTION_PLAN.md（本文件）
- docs/CLAIM_LIFECYCLE.md
- docs/PLATFORM_APP_SPLIT.md
- platform/README.md

只读参考（禁止复制为第二实现、禁止修改 research 仓）：
- ~/code/research/technology-graph-grok/prototypes/FREEZE.md
- ~/code/research/technology-graph-grok/prototypes/mission_os/{daemon,assignment,mission,facts,tool_policy}.py

当前任务：实现 PR-A（晋升门禁补洞 + 流隔离测试，不重写 policy.py）。
约束：
1. platform/missionos 不得 import council
2. 禁止自动 PROMOTE
3. make ci 必须通过
4. 提交信息说明改了什么、如何验证

做完 PR-A 后汇报；按 A → B → C → F → D → E 推进（见 §13）。
```

---

## 11. 与现有路线的关系

| 已有文档 | 关系 |
|----------|------|
| `CLAIM_LIFECYCLE.md` | 主张语义权威；本方案不改 V0.2 事件形状，只加强执法 |
| `PLATFORM_APP_SPLIT.md` | 拆分已完成；本方案在边界内增强 |
| `INTERACTIVE_SESSION.md` | 交互会话并存；GuestSlot 应对 interactive 路径同样适用（PR-B 可第二阶段补） |
| `PR1_FOLLOWUPS.md` | 正交；PromptComposer 等仍按其表 |
| `EXPERIMENTS.md` | 实验方法论不变；进化后应用同议题对比验证「门禁未伤研究质量」 |

---

## 12. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-07-11 | 初版：基于 Mission OS 研究原型对照 + Claimfold 现状，输出 PR-A…E 可执行方案 |
| 2026-07-11 | §13：Grok + Codex + Claude 三方审议，收窄 PR-A、统一 Slot 事实源、新增 PR-F、调整顺序 |

---

## 13. 三方审议结论（Grok + Codex + Claude，2026-07-11）

### 一致采纳

| 议题 | 决定 |
|------|------|
| **PR 顺序** | **A → B → C → F → D → E**（B/C 紧耦合连续做，不并行改 unrelated 文件） |
| **PR-A** | 补洞为主：流隔离 CI + promote 集成测试；**不重写** `policy.py` |
| **GuestSlot** | `events.jsonl` 为源，`meeting_state` 为投影；**v1 无 generation** |
| **双路径** | `parallel` 与 `interactive` **共用** `slots.py` |
| **PR-C v1** | 仅 HITL 事件 + FailurePolicy；**不**拦 promote |
| **PR-F** | Web/角色卡对齐 slot/HITL；在 C 之后、D 之前 |

### 分工与分歧处理

- **Codex** 主张 PR-A 额外收紧「仅 summaries 不能单独晋升」与 promote CLI 集成测试 → **采纳**（小改 policy + 新测试）
- **Claude** 主张 PR-A **不**扩 scope 做新 override 通道 → **采纳**（只测现有 `owner_override` + `override_note`）
- **Grok** 主张 B 与 interactive 同步、避免 Web 再次脱节 → **采纳为 PR-F**

### 开工清单（复制即用）

- [ ] **PR-A：** `test_stream_isolation.py` + `test_claim_promotion_gates.py`；可选收紧 raw 证据；`make ci` 绿
- [ ] **PR-B：** `slots.py` + events 写入 + parallel/interactive 共用 + `status`/`repair-slots`
- [ ] **PR-C：** FailurePolicy 三态 + `OwnerInterruptRaised/Resolved`；不拦 promote
- [ ] **PR-F：** Web 消费 slot/HITL；`rc-*` 映射测试
- [ ] **PR-D / E：** 按原文档；每步 `make ci` + `check_platform_boundary.sh`
