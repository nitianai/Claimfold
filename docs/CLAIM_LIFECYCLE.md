# 主张生命周期（Claim Lifecycle）— 研究运行时（Research Runtime）V0.2 规范（冻结草案）

> **运行时座右铭（Runtime Motto）**
>
> - 语义闭环（Semantic Loop）→ **不要忘记（Don't Forget）。**
> - 主张生命周期（Claim Lifecycle）→ **不要过早相信（Don't Believe Too Early）。**
> - 注入契约（Injection Contract）→ **不要比证据听起来更确定（Don't Sound More Certain Than the Evidence）。**
> - 账本折叠（Ledger Fold）→ **不要让投影（Projection）变成可写对象（Writable）。**

---

## 0. 范围（Scope）

V0.2 增加**跨会话可复用主张（cross-session reusable claims）**，且不制造第二真相源（second source of truth）。

- **不是** 知识库（Knowledge Base）
- **不是** 可变更的主张对象（mutable Claim objects）
- **是** 只追加的主张事件历史（append-only Claim Event History）+ 可重建的只读索引（rebuildable read-only index）

---

## 1. 绝不能晋升（Promote）的内容（禁止晋升清单 Non-Promotion List）

硬性拒绝（hard reject）。除非标注 `promoted_by: owner_override`（所有者覆盖晋升）并附审计说明（audit note），否则 Owner（所有者）不得绕过。

| 类别 | 示例 |
|------|------|
| 模拟 / 缺失数据（Mock / missing data） | `[MOCK]`、`数据缺失`、`待复核`、`forced-mock` |
| 活跃会话分歧（active session conflict） | 仍在 `meeting_state.conflicts`（会议状态·分歧）中且未解决的条目 |
| 开放任务（open tasks） | `open_questions`（未决问题）条目（问题 ≠ 主张） |
| 仅投影（projection-only） | 压缩器（Summarizer）输出无法在 raw（原始输出）中找到 `evidence_refs`（证据引用） |
| 报告叙事（report narrative） | 情景（Scenario）概率、配置比例、投资报告（investment_report）正文 |
| 单行摘要（one-liner summaries） | 仅有 `guest_position_summary`（嘉宾立场摘要），无 raw 锚点 |
| 重复噪声（duplicate noise） | `merge_unique`（去重合并）后仅 Guest 名称不同的字符串 |
| 无适用范围（unscoped assertions） | 无 `scope`（适用范围）边界（见 §5） |
| 单轮_singleton（single-round singleton） | 单 Guest、单轮、无 RESPOND（回应）链（默认拒绝） |

---

## 2. 账本事件（Ledger Events）— 谁可以产生什么

**唯一写入源：** `claims.jsonl`（只追加、不可变事件 immutable events）

| 事件（Event） | 执行者（Actor） | 用途（Purpose） |
|---------------|-----------------|-----------------|
| `PROMOTE`（晋升） | 仅 Owner（所有者） | 将会话命题登记为试探性主张（Tentative claim） |
| `RESPOND`（回应） | Guest（嘉宾，经引擎解析）或 Operator（操作员） | SUPPORT（支持）/ CHALLENGE（挑战）/ RETIRE（废弃）/ DEFER（暂缓）+ `evidence_refs` |
| `RETIRE`（退休） | Owner 或规则（如 scope 过期） | 从默认注入集合中移除 |

**V0.2 明确不做：**

- 自动晋升（Auto-PROMOTE）
- 自动语义争议检测（auto semantic CONTEST detection）
- 将 `SUPPORTED`（已支持）作为认识论状态（epistemic state）（支持次数 ≠ 真理投票）
- 所有者认证（Owner Attested）（推迟至 V0.3）
- 主张图（Claim Graph）/ 自动合并（auto-merge）/ 校准算子（Calibration Operator）

### 2.1 PROMOTE（晋升）最小字段

```json
{
  "event": "PROMOTE",
  "claim_id": "clm-000017",
  "fingerprint": "sha256:normalized(statement+scope)",
  "statement": "当地缘风险上升且美元走弱时，黄金倾向上涨",
  "scope": {
    "domain": "finance",
    "subjects": ["gold"],
    "regime_tags": ["risk-off"],
    "valid_from": "2026-07-10",
    "valid_until": "2026-08-01",
    "conditions": [],
    "exclusions": []
  },
  "epistemic_status": "TENTATIVE",
  "evidence_refs": ["meet-xxx/raw/round-002-hy3.md"],
  "derived_from_meeting": "meet-xxx",
  "derived_from_state_ref": "conflicts[0]|confirmed_points[2]",
  "promoted_by": "owner",
  "ts": "2026-07-10T00:00:00Z"
}
```

字段说明：

- `claim_id`（主张标识）：稳定指涉（stable reference），顺序编号 `clm-NNNNNN`
- `fingerprint`（指纹）：`sha256(normalize(statement)+scope)`，仅用于去重提示（deduplication hint）
- `statement`（陈述）：主张正文
- `scope`（适用范围）：见 §5
- `epistemic_status`（认识论状态）：V0.2 仅 `TENTATIVE`（试探性）
- `evidence_refs`（证据引用）：指向 raw 等审计文件
- `derived_from_meeting`（来源会议）
- `derived_from_state_ref`（来源状态引用）
- `promoted_by`（晋升者）
- `ts`（时间戳）

### 2.2 RESPOND（回应）— Guest 不直接修改状态

```json
{
  "event": "RESPOND",
  "claim_id": "clm-000017",
  "response": "CHALLENGE",
  "evidence_refs": ["meet-yyy/raw/round-001-nemo.md"],
  "meeting_id": "meet-yyy",
  "actor": "guest:north",
  "statement": "美元走强阶段该命题不适用",
  "ts": "2026-07-11T00:00:00Z"
}
```

- `response`（回应类型）：`SUPPORT` | `CHALLENGE` | `RETIRE` | `DEFER`
- `actor`（行为主体）：如 `guest:north`

### 2.3 RETIRE（退休）

```json
{
  "event": "RETIRE",
  "claim_id": "clm-000017",
  "reason": "scope expired | owner decision | superseded",
  "actor": "owner|rule:scope_expired",
  "ts": "2026-07-12T00:00:00Z"
}
```

- `reason`（原因）：适用范围过期 / 所有者决定 / 已被新主张取代（superseded）

---

## 3. 折叠规则（Fold Rules）— 事件历史 → 只读视图（Read-only View）

**投影文件（projection file）：** `claims_index.json`（主张索引）  
**性质：** 物化视图（Materialized View）— 可删除、可重建、**无独立写路径（no independent write path）**

重建命令（未来）：`./council.sh claim rebuild-index`（重建索引）

### 3.1 投影状态（V0.2 仅此三种）

| 状态（Status） | 含义 |
|----------------|------|
| `TENTATIVE`（试探性） | 存在 PROMOTE，无有效 CHALLENGE，未 RETIRE |
| `CONTESTED`（受争议） | 自上次 RETIRE（或 PROMOTE）起，存在 ≥1 条有效 `RESPOND:CHALLENGE` |
| `RETIRED`（已退休） | 最新生命周期事件为 RETIRE |

**V0.2 不作为状态：** `SUPPORTED`（已支持）— SUPPORT 只是事件，不是认识论等级升级。

### 3.2 折叠算法（Fold algorithm，确定性 deterministic）

```
对每个 claim_id（来自 PROMOTE 事件）：
  status = TENTATIVE
  若最后一次 PROMOTE 之后存在 RETIRE：status = RETIRED
  否则若存在 RESPOND:CHALLENGE 且无 RETIRE：status = CONTESTED
  附加：challenge_history[]、support_count、last_respond_ts
  附加：来自 PROMOTE 的 fingerprint、scope、statement、evidence_refs
```

**V0.2 中 Engine（引擎）不得通过语义冲突检测自动 CONTEST。**  
`CONTESTED` = 显式 CHALLENGE 回应经折叠（fold）得出。

### 3.3 身份 vs 去重（Identity vs deduplication）

| 字段 | 角色 |
|------|------|
| `claim_id`（主张标识） | 稳定指涉，顺序编号，**永不**从文本派生 |
| `fingerprint`（指纹） | 仅用于去重提示；算法版本升级不得改变 `claim_id` |

---

## 4. 注入契约（Injection Contract）— 主张如何进入研究

主张**仅**通过 `ANCHOR`（锚定）阶段（`context` / Guest 提示词 prompt）进入，**永不**通过 Report（报告）进入。

### 4.1 必需章节标题

```markdown
## 历史试探性主张

以下内容 **不是事实**，也 **不是当前结论**。
它们来自历史研究、仍可被挑战或废弃的命题。

你必须对 **至少一条** 主张选择一种回应：
- **SUPPORT（支持）** — 提供新增且独立的证据
- **CHALLENGE（挑战）** — 提供反证或指出适用边界
- **RETIRE（废弃）** — 说明已过期、失效或不再适用
- **DEFER（暂缓）** — 当前证据不足，暂不判断
```

### 4.2 单条主张格式

```markdown
- [{STATUS}] {claim_id}: {statement}
  scope: {domain} | subjects: {subjects} | valid: {valid_from}..{valid_until}
  evidence: {evidence_refs[0]}, ...
```

`CONTESTED` 主张注入时加前缀：`[CONTESTED — 优先处理]`

### 4.3 禁用注入词汇（权威渗漏 Authority Leakage）

禁止使用：

`已验证` `确定` `结论` `已知` `事实` `共识` `权威判断` `系统认为` `已经证明`

### 4.4 选取策略（Top-K，取前 K 条）

仅注入满足以下条件的主张：

- `scope` 与当前会议 `current_focus`（当前焦点）/ `topic`（议题）有交集
- `status` ∈ {`TENTATIVE`, `CONTESTED`}
- 未过 `valid_until`（若已设置）；若已 `CONTESTED` 可仍展示并标 `STALE`（过期）
- 默认 K = 5（可配置）

完整账本（ledger）保留；提示词（prompt）只取范围内子集。

---

## 5. 适用范围边界（Scope Boundary）— 不限于 valid_until

`scope` 必须定义**适用性（applicability）**，不能只有日历时间。

```json
{
  "domain": "finance|protocol|architecture|...",
  "subjects": ["gold", "USD"],
  "regime_tags": ["risk-off"],
  "valid_from": "2026-07-10",
  "valid_until": "2026-08-01",
  "conditions": ["Sony E-mount", "firmware >= 2.1"],
  "exclusions": ["intraday noise"]
}
```

字段说明：

- `domain`（领域）：金融 / 协议 / 架构等
- `subjects`（主题标的）
- `regime_tags`（体制标签）：如 risk-off（避险）
- `valid_from` / `valid_until`（有效起止日期）
- `conditions`（适用条件）
- `exclusions`（排除条件）

**规则：** 若无 `domain` + `subjects` + 至少一种边界机制（`valid_until` 或 `conditions` 或 `regime_tags`），则拒绝 promote。

---

## 6. V0.2 最小实现清单（Minimal Implementation Checklist）

> **封板 ≠ §6 勾选完毕。** V0.2 正式封板须同时满足：§6 全部交付、§7 在真实 CLI 下复验通过、**实验平台 Phase 2（E1–E5）完成**（见 `docs/EXPERIMENTS.md` §8）。当前：**实现已完成，封板待 Phase 2。**

### 必须交付（Must ship）— 代码已实现，封板待 Phase 2

- [x] `claims.jsonl` 只追加 — `lib/claim_lifecycle.py` + `claims/claims.jsonl`
- [x] `claims_index.json` 从账本重建 — `claim rebuild-index`
- [x] `claim promote`（Owner 手动晋升）— `--from-state conflicts[N]` + scope + `--evidence`
- [x] `claim retire`（Owner 手动退休）
- [x] `claim rebuild-index`（重建索引）
- [x] `claim list`（只读列表）
- [x] 按 scope 的 Top-K 注入研究 Guest prompt — `{{prior_claims}}`
- [x] Guest 输出解析为 `RESPOND` 事件（SUPPORT|CHALLENGE|RETIRE|DEFER）
- [x] `claim verify`（三场会议验收 §7）— 黄金链路已跑通一次；TSLA 跨会 CHALLENGE 待 E5
- [x] promote 时的禁止晋升校验器（non-promotion validator）
- [x] 注入禁用词检查（authority leakage）

### 明确推迟至 V0.3+

- 自动晋升、自动语义争议、SUPPORTED 状态、Owner Attested、Claim Graph、Calibration Operator、按 fingerprint 自动合并

---

## 7. 三场会议验收场景（Three-Meeting Acceptance Scenario）

### 会议 A（Meeting A）

1. 研究运行产生带 `evidence_refs` 的命题（raw / summary.json）
2. Owner：`./council.sh claim promote --from-state ...`
3. `claims.jsonl` ← `PROMOTE`
4. 重建 `claims_index.json` → `TENTATIVE`

### 会议 B（Meeting B）

1. `./council.sh start` + `context` → 按 §4 注入主张
2. Prompt 通过禁用词检查
3. Guest raw 含对 `claim_id` 的 CHALLENGE + 新证据
4. Engine 写入 `RESPOND:CHALLENGE`
5. 重建索引 → `CONTESTED`

### 会议 C（Meeting C）

1. Owner：`./council.sh claim retire clm-000017`
2. 重建索引 → `RETIRED`
3. 新会议 Top-K 注入排除已退休主张

**通过标准：** 各步可在 jsonl 中审计；索引可从零重建；禁止手改索引。

### §7 验收记录（进行中）

| 步骤 | 会议 / 命令 | 状态 |
|------|-------------|------|
| A promote | `meet-20260710-015200` → `clm-000001` | ✅ 真实 CLI |
| B 注入 + CHALLENGE | `meet-20260710-015733`（R1 含 mock） | ⚠️ 部分真实；封板前须无 mock 复验 |
| C retire + verify | `claim retire` + `claim verify` | ✅ 通过 |
| E5 TSLA 跨会 CHALLENGE | `clm-000004` → `meet-20260710-033604`，mimo 真实 raw | ✅ CONTESTED |

复现：`docs/EXPERIMENTS.md` §3。

---

## 8. 指标（Metrics）— 实验报告扩展（推迟 V0.3）

> V0.2 封板**不依赖**本节；E4 `model_tier` 属 Phase 2 必填项。

不追踪 `claim_count`（主张数量）。应追踪：

- `inject_to_respond_ratio`（注入回应比）— 被注入且收到实质 RESPOND 的主张占比
- `contested_unresolved_days`（争议未解决天数）— CONTESTED 后无后续跟进
- `promote_reject_rate`（晋升拒绝率）— 命中禁止晋升清单次数
- `stale_injected_count`（过期仍注入数）— 已过 valid_until 仍被展示

---

## 9. 架构边界（Architecture Boundary）（Grok × GPT 合成）

```
证据（Evidence，raw）
  → 会话投影（Session Projection，summary.json）
    → 会话折叠（Session Fold，meeting_state.json）
      → 主张事件（Claim Event，claims.jsonl）     ← 唯一新增写路径
        → 主张视图（Claim View，claims_index.json） ← 可重建、非权威
          → 注入（Injection，prompt 附录）          ← 语气受控、带义务
            → Guest RESPOND（回应）
              → 主张事件 ...
```

**可写（Writable）：** raw、summary.json（每轮）、meeting_state（仅来自 summary.json）、claims.jsonl（仅事件）  
**永不可写（Never writable）：** claims_index.json、investment_report.md、final.md  
**永不允许晋升路径（Never promotes）：** Report → Claim、State → Claim（未经 Owner PROMOTE）

---

## 10. 状态（Status）

| 项目 | 状态 |
|------|------|
| 语义闭环（Semantic Loop） | ✅ 已交付（Research `run-parallel`） |
| 主张生命周期 V0.2 — §6 实现 | ✅ 代码已交付（`lib/claim_lifecycle.py` + `claim` CLI） |
| §7 三场会议验收 | ⚠️ 黄金链路已跑通；封板前须真实 CLI 全链复验 + E5 |
| 实验平台 Phase 2（E1–E5） | ✅ 已完成（见 `docs/EXPERIMENTS.md` §8） |
| Claim 指标 §8 | ⏳ 推迟至 V0.3 |
| **V0.2 封板** | **待 Owner 确认** — Phase 2 达标；黄金 §7 B 轮建议去 mock 复验 |

---

## 附录：术语对照速查

| 英文 | 中文 |
|------|------|
| Claim | 主张（可跨会挑战的命题，非真理） |
| Claim Lifecycle | 主张生命周期 |
| Ledger | 账本（事件流） |
| Fold | 折叠（从事件推导视图） |
| Materialized View | 物化视图 |
| Projection | 投影 |
| PROMOTE | 晋升（登记为试探性主张） |
| RESPOND | 回应 |
| RETIRE | 退休（停止默认注入） |
| TENTATIVE | 试探性 |
| CONTESTED | 受争议 |
| Injection Contract | 注入契约 |
| Authority Leakage | 权威渗漏 |
| evidence_refs | 证据引用 |
| scope | 适用范围 |
| fingerprint | 指纹（去重用） |
| Non-Promotion List | 禁止晋升清单 |
| Research Runtime | 研究运行时 |