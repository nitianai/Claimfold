# Interactive Session（交互式会话）设计

> **状态：** Phase 1–4 已交付（CLI + 事件 + 话轮协议 + 标注投影 + Web API）  
> **日期：** 2026-07-11
> **方向：** 持续 Agent Runtime（方向一）+ 话轮协商协议（方向二）  
> **原则：** Engine 调度、Guest 推理、事件可重放、不大爆炸替换 `run-parallel`

---

## 1. 问题陈述

当前 `run-parallel` 对每个嘉宾执行 **一次性** `invoke_cli`：同一轮内嘉宾互不可见、无法承接彼此观点。会议像「并行问卷」，不像「回合制讨论」。

目标：在保持 Claimfold 可审计性的前提下，升级为 **确定性回合制交互会话**。

**不做：** 自由抢话 WebSocket 聊天室（失去 Determinism（确定性））。

---

## 2. 架构定位

```
Owner / CLI
    ↓
Engine（InteractiveSessionEngine）  ← 唯一调度者、单写入
    ↓ floor_granted → invoke_cli → message_committed
Guest Runtime Adapter（Phase 1：仍是一次性 CLI，由 Engine 管队列）
    ↓
events.jsonl（追加） + meeting_state.json（派生） + raw/summary（制品）
```

| 层 | 职责 |
|----|------|
| **Platform** `missionos.session.events` | JSONL 追加、加载 |
| **App** `council.interactive` | 话轮队列、事件发布、回合收束 |
| **App** `council.runners.interactive` | 串行调用 `process_interactive_guest` |
| **现有** `run-parallel` | 保留，feature 并存 |

---

## 3. 交互模式

### 3.1 `meeting_mode: interactive`

```bash
./council.sh start "黄金一周走势" --mode interactive
./council.sh context "黄金、美元、美债"
./council.sh select codex grok
./council.sh run-interactive
```

一轮（macro round）内按 `speaking_queue` **串行**发言；每位嘉宾看到本轮已提交的发言（`build_on` = `reply_to`）。

### 3.2 与 `research` / `run-parallel` 关系

| 命令 | 行为 |
|------|------|
| `run-parallel` | 不变；ThreadPool 并行、互不可见 |
| `run-interactive` | 新；串行、可见 prior turns |
| `session step` | 调试/重现；只推进一步 |
| `session inspect` | 查看 queue / speaker / messages |

---

## 4. 事件类型（`events.jsonl`）

Phase 1 新增（`schema_version: 1.0` 保持）：

| event | 说明 | 关键字段 |
|-------|------|----------|
| `session_started` | 交互轮开始 | `round`, `guests`, `interaction_mode` |
| `floor_granted` | Engine 授权发言 | `round`, `guest`, `turn`, `event_seq` |
| `message_committed` | 嘉宾发言落盘 | `round`, `guest`, `turn`, `reply_to`, `message_id`, `raw_output_path` |
| `floor_yielded` | 嘉宾让出话轮 | `round`, `guest`, `turn` |
| `session_paused` | 中途暂停（`session step` 后） | `round`, `remaining_queue` |
| `session_ended` | 交互轮收束 | `round`, `guest_count`, `duration_s` |

既有事件保留：`round_started`, `guest_completed`, `state_merged`, `claim_responded`。

---

## 5. `meeting_state.json` 增量字段

```json
{
  "meeting_mode": "interactive",
  "interaction_mode": "turn_based",
  "session_status": "idle",
  "event_seq": 0,
  "current_speaker": null,
  "speaking_queue": [],
  "floor_turn": 0,
  "interactive_round": null,
  "interactive_entries": [],
  "session_messages": [],
  "context_cursor": 0,
  "state_version": 1,
  "pending_interrupts": [],
  "active_threads": []
}
```

| 字段 | 含义 |
|------|------|
| `session_status` | `idle` / `active` / `paused` / `ended` |
| `interactive_round` | 进行中的 macro round 号（收束后写入 `round` 并清空） |
| `session_messages` | 本轮已提交发言 `[{message_id, guest, turn, reply_to, summary_excerpt}]` |
| `interactive_entries` | 收束前累积的 guest entry（同 parallel history entries） |

---

## 6. 话轮协议（Phase 1 子集）

```
Engine                          Guest
  |                               |
  |-- floor_granted(guest) ------>|
  |                               | invoke_cli(prompt + prior_turns)
  |<-- message_committed ---------|
  |-- floor_yielded(guest) ------>|
  |                               |
  | (next in speaking_queue)      |
```

**Phase 2 已实现：** `floor_requested` / `interrupt_requested` / `message_proposed`；`build_on` 通过 `--build-on` 与 `active_threads` 追踪。  
**CLI：** `./council.sh floor request|yield|interrupt`

约束：

- 每轮最大话轮数 = `len(selected_guests)`（可配置上限 `max_turns_per_round`）
- `owner_required` 时 Engine 拒绝推进
- 所有状态变更经 `save_state` 单写入

---

## 7. Prompt 增强

不修改 `prompts/guest/research.md` 模板。Engine 在渲染后追加：

```markdown
## 本轮已发言（请回应或承接，勿重复）

### Turn 1 · codex
…guest_position_summary…

### Turn 2 · grok（reply_to: msg-001）
…
```

由 `council.interactive.prompts.format_prior_turns()` 生成。

---

## 8. CLI 命令

```bash
# 启动
./council.sh start "议题" --mode interactive

# 完整交互轮（队列跑完才收束）
./council.sh run-interactive

# 单步（调试 / 重现）
./council.sh session step

# 查看会话状态
./council.sh session inspect

# 从 paused 继续（等同 run-interactive 续跑）
./council.sh session resume
./council.sh session replay --tail 20
./council.sh floor request qoder --urgency 2 --build-on msg-001-01-codex
./council.sh floor interrupt grok codex --message msg-001-01-codex
./council.sh session inspect --annotations
```

---

## 9. 渐进迁移路线

| Phase | 内容 |
|-------|------|
| **1** ✅ | 串行 `invoke_cli` + 事件 + CLI + `session step/resume` |
| **2** ✅ | `floor` 子命令 + `active_threads` + `message_proposed` |
| **3** ✅ | `context_cursor` 同步 + `context_observed` + `session replay` |
| **4** ✅ | `annotations.py` 投影 + `session inspect --annotations` + Web `interactive` 字段 |
| **5（未来）** | 进程复用 PersistentGuest / 真 interrupt 调度 |

回退：任何会议可继续用 `run-parallel`；`meeting_mode != interactive` 时零影响。

---

## 10. 风险与规避

| 风险 | 规避 |
|------|------|
| 并发不可重放 | Phase 1 禁止并行 turn；单写入 Engine |
| 成本失控 | `max_turns_per_round`、CLI timeout 沿用 `timeout_seconds` |
| 中途失败 | `session_status=paused` + `interactive_entries` 保留；`session resume` 续跑 |
| 双轨维护 | 共用 `process_*_guest` 制品路径与 `summary.json` 管线 |

---

## 11. 验收标准（Phase 1）

1. `./council.sh start ... --mode interactive` 写入交互字段默认值  
2. `run-interactive` 串行产生 `floor_granted` / `message_committed` / `floor_yielded` 事件  
3. 后发言嘉宾 prompt 含前序 `prior_turns`  
4. 收束后 `history` 块 `mode: interactive`，`round` 递增  
5. `session step` 可逐步重现；`session inspect` 可读 queue  
6. 现有 `run-parallel` 测试不退化