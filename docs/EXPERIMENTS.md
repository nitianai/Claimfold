# Claimfold 实验记录（Experiments Log）

> **项目初心：** Claimfold 是**多模型研究实验平台**，不是单一结论生成器。  
> 价值在于：可复现流程、可度量对比、可审计留痕、可挑战主张——而非某次会议的涨跌判断。

本文档记录截至 **2026-07-10** 的真实 CLI 实验结果，作为后续升级模型（Claude / Codex / Grok 4.3 等）的**最差基线（floor）**。

---

## 0. 实验设计原则

| 原则 | 说明 |
|------|------|
| **架构优先** | 先冻结流程（context → parallel → semantic loop → claim），再换模型 |
| **最差基线** | 免费 / 混合 tier 实验定义下限；贵模型实验定义上限 |
| **同议题对比** | 对比实验共用 `market_context`，只改变嘉宾数或模型 |
| **可审计** | 每场会议留 `prompt/`、`raw/`、`summary.json`、`metrics.json` |
| **不堆人数** | 质量来自角色分工 + 议题聚焦，非 Guest 数量 |

复现质量对比：

```bash
python3 scripts/compare_meetings.py meet-20260710-021348 meet-20260710-021510
```

---

## 1. 实验 A — Research 语义闭环（黄金，真实 CLI）

**会议：** `meet-20260710-015200`  
**议题：** 未来一周黄金走势  
**流程：** `context` → Round1(hy3+nemo) → Round2(qwen+north+hy3)

| 指标 | 结果 |
|------|------|
| 总轮次 | 2 |
| Guest 发言 | 5 次 |
| 平均耗时 | 156s/轮 |
| JSON 解析成功率 | 100% |
| Guest 失败率 | 0% |
| Mock 率 | 20%（north summarizer 因 opencode 配置；Guest raw 真实） |
| 语义闭环 Round2 | **通过** |
| 最终 state | CP:19 / CF:8 / OQ:14 |

**结论：**

- 两轮 `run-parallel` 可形成可回溯的 `confirmed/conflicts/open_questions` 闭环。
- 议题过宽导致 OQ=14，引擎提示议题发散。
- qwen Round2 真实输出 36s，gpu-llama 锚定有效。

---

## 2. 实验 B — 嘉宾数量对比（黄金，同 context）

**对照：** 同一 `market_context`（来自 `meet-20260710-015200`），单轮并行。

| 组别 | 会议 ID | 嘉宾 | 耗时 | Mock率 | CP | CF | OQ |
|------|---------|------|------|--------|----|----|-----|
| **A 基准** | `meet-20260710-021348` | qwen+hy3+nemo (3) | 97s | **0%** | 7 | 2 | 4 |
| **B 扩展** | `meet-20260710-021510` | 8人含 north/gptoss20/gemma/llama/nemotron120 | 883s | **38%** | 13 | 8 | 13 |

**B 组逐 Guest：**

| Guest | 耗时 | Mock | 评价 |
|-------|------|------|------|
| qwen | 32s | 否 | 宏观锚定 |
| north | 51s | 否 | 大宗视角，有效增量 |
| gptoss20 | 39s | 否 | 2407 字，结构化推理最佳之一 |
| hy3 | 76s | 否 | 地缘/policy |
| nemo | 41s | 否 | 利率外汇 |
| gemma26 | 193s | **是** | 超时 |
| llama70 | 190s | **是** | 超时 |
| nemotron120 | 260s | **是** | 超时 |

**结论：**

1. **8 人并非 3 人的超集质量** — 耗时 ×9，Mock 污染 38%。
2. **有效增量来自角色互补**（north、gptoss20），非模型数量。
3. **70B+ 免费 tier 不适合并行生产** — 超时 → mock → state 污染。
4. **推荐生产阵容：4–5 人**，`max_parallel: 4–6`。

---

## 3. 实验 C — Claim Lifecycle 全链（真实 + mock 混合）

**流程：** Meeting A promote → Meeting B 注入 + CHALLENGE → Meeting C retire → `claim verify`

| 步骤 | 结果 |
|------|------|
| `claim promote` clm-000003 | 从 `conflicts[0]` 晋升，证据 `raw/round-002-qwen.md` |
| prior_claims 注入 | prompt 含 `[TENTATIVE] clm-000003` |
| qwen CHALLENGE | 真实 25s，实质性反证写入 `claims.jsonl` |
| `claim retire` | RETIRED |
| `claim verify` | **通过** |

**结论：**

- Semantic Loop（不忘）+ Claim Lifecycle（不信太早）可同时工作。
- 主张晋升应选**可证伪命题**，非整份会议结论。
- `claims.jsonl` 只追加；`claims_index.json` 可重建。

详见 [`CLAIM_LIFECYCLE.md`](CLAIM_LIFECYCLE.md)。

---

## 4. 实验 D — 窄议题 vs 宽议题（TSLA）

**会议：** `meet-20260710-023309`  
**议题：** TSLA 未来一周走势（2026-07-10 至 07-17）  
**阵容：** R1: mimo+qwen+gptoss20+nemo → R4: mimo(deepseek 修正)

| 轮次 | 嘉宾 | 模型 | 耗时 | Mock | 要点 |
|------|------|------|------|------|------|
| R1 | qwen | gpu-llama | 50s | 否 | $395–$420 三情景概率 |
| R1 | gptoss20 | gpt-oss-20b | 122s | 否 | 结构化逻辑 |
| R1 | nemo | nemotron-30b | 27s | 否 | 7/22 财报前波动 |
| R1 | mimo | qwen3-next-80b | 11s | **是** | 无效 |
| R4 | mimo | deepseek-v4-flash | 48s | 否 | 挑战 Bull 三大叙事 |

**TSLA 会议可收敛结论（非投资建议）：**

> 基准情景：宽幅震荡 **$395–$425**，财报（7/22）前观望；  
> 阻力 $415–$425，支撑 $380–$390；  
> Robotaxi / SpaceX 合并短期难证实；高 PE + 高利率为主要压制。

**结论：**

- 个股议题比「一周黄金全资产」更聚焦，但仍建议用 `ask` 再收窄到单因子。
- **equity 位必须用稳定小模型**（mimo: deepseek-v4-flash）；大模型免费 tier 不可靠。
- 锚定模型（qwen）决定会议基调；职能嘉宾（mimo）提供挑战增量。

---

## 5. 实验 F — 5 人风格分化（TSLA，真实 CLI）

**会议：** `meet-20260710-040135`  
**阵容：** `tsla_feed` + `qwen` + `grok`(laguna→4.3) + `mimo` + `nemo`  
**流程：** context（E2 脚本 ✅，LLM context mock）→ R1 五人 → R2 自动三人 → 语义闭环

| 轮次 | 嘉宾 | 耗时 | Mock | 风格贡献 |
|------|------|------|------|----------|
| R1 | tsla_feed | 0.3s | 否 | 证据层 $406.55 |
| R1 | qwen | 31.8s | 否 | 宏观区间 $393–$420，引用 clm-000004 |
| R1 | grok-4.3 | 28.2s | 否 | **DEFER** clm-000004（无地缘数据，守纪律） |
| R1 | mimo | 41.6s | 否 | 个股深挖 + **CHALLENGE** 废弃 SpaceX merge |
| R1 | nemo | 20.6s | 否 | 利率视角 **CHALLENGE** 高 PE vs 低 VIX |
| R2 | qwen+north+mimo | 89.4s | 否 | 语义闭环 **通过** |

| 指标 | R1（5人） | R1+R2 合计 | 对照 8人实验 B |
|------|-----------|------------|----------------|
| 耗时 | 73.4s | 162.8s | 883s |
| Mock率 | 0% | 0% | 38% |
| OQ | 11 | **15** | 13 |
| CP | 17 | 27（有重复） | 13 |
| 语义闭环 | — | **通过** | 未测 |

**结论：**

1. **5 人风格分化有效** — 证据/宏观/地缘/个股/利率五类输出，且 grok、mimo、nemo 对 `clm-000004` 给出 DEFER/CHALLENGE 三种不同回应。
2. **人多不必同场重复** — R2 引擎自动缩为 3 人（qwen+north+mimo）仍通过语义闭环；**第二轮不必再堆 5 人**。
3. **OQ=15 接近发散阈值** — 5 人已够；再加 gptoss20/north 同轮会放大 CP/OQ 重复。
4. **grok 依赖 context 质量** — LLM context mock 时 grok 正确 DEFER，不硬编地缘；下一场须真实 `context` 才能发挥。
5. **推荐生产阵容不变：4–5 职能位**，不是 6–8 同族模型。

```bash
# 推荐 select（TSLA / 个股）
./council.sh select tsla_feed qwen grok mimo nemo   # R1
./council.sh run-parallel
./council.sh select qwen mimo                       # R2 语义闭环即可，或 run-parallel 让引擎 auto-pick
./council.sh run-parallel
```

---

## 6. 模型分层实验（稳定性探测）

**探测方法：** `opencode run -m <model> --auto "回复ok"` + 会议实测

### S 级（生产锚定）

| 模型 | 延迟 | Mock率 | 角色 |
|------|------|--------|------|
| `gpu-llama/qwen3.6-35b` | 25–50s | 0% | 宏观锚定（**串行**，单槽位） |

### A 级（免费 tier 可用）

| 模型 | 延迟 | 角色 |
|------|------|------|
| `opencode/deepseek-v4-flash-free` | <50s | 个股/股票（mimo） |
| `openrouter/openai/gpt-oss-20b:free` | ~39s | 结构化推理 |
| `nvidia/nvidia/nemotron-3-nano-30b-a3b`（NIM） | **~5s** | 利率外汇、summarizer（推荐） |
| `openrouter/nvidia/nemotron-3-nano-30b-a3b:free` | 20–40s | 备用 |
| `openrouter/cohere/north-mini-code:free` | ~51s | 大宗 |
| `openrouter/tencent/hy3:free` | 30–76s | 地缘（已移出默认阵容） |
| `hermes-grok/grok-4.3` | ~17s | 地缘/policy（grok 别名 → laguna） |
| `openrouter/poolside/laguna-m.1:free` | ~16s | 备用（已被 grok-4.3 取代） |

### C 级（实验禁用 — 易超时 Mock）

| 模型 | 问题 |
|------|------|
| `qwen3-next-80b:free` | 11s 即 mock |
| `gemma-4-26b:free` | 193s 超时 |
| `llama-3.3-70b:free` | 190s 超时 |
| `nemotron-3-super-120b:free` | 260s 超时 |
| `nemotron-3-ultra-550b:free` | 极慢，已移除 |

---

## 7. 架构实验结论（模型无关）

```
会议产出质量 ≈
  议题聚焦度（~30%）
+ 证据/context 质量（~25%）
+ 锚定模型 + 角色分工（~30%）
+ 其他嘉宾增量（~10%）
+ 流程：语义闭环 + Claim（~5%）
```

| 发现 | 证据 | 行动 |
|------|------|------|
| 人数 ≠ 质量 | 实验 B | 默认 4–5 人 |
| Mock 是负贡献 | gemma/llama/mimo-old | 监控 `used_mock_guest` |
| 议题宽度驱动 OQ 发散 | 黄金 OQ=14 vs TSLA OQ=4 | 用 `ask` 收窄 |
| 角色 > 模型名 | north/gptoss20 增量 vs 大模型 mock | `role_id` 职能化 |
| 脚本应作证据层 | TSLA mimo 关闭「缺 CLI」OQ | 待做 `guest_type: script` |
| 贵模型抬上限，非重做架构 | 当前为 floor 基线 | Phase 2 单点 A/B |

---

## 8. 冻结的生产配置（2026-07-10）

```yaml
# config/guests.yaml — 实验平台默认阵容（最差基线）
max_parallel: 6

推荐 select（R1，4–5 职能位）:
  tsla_feed   # 证据脚本（个股议题）
  qwen        # 宏观锚（串行）
  grok        # 地缘政策（grok-4.3）
  mimo        # 个股挑战
  nemo        # 利率/外汇
按需（勿同轮全加）: gptoss20（结构化）, north（大宗）
```

**单场推荐流程：**

```bash
./council.sh start "<窄议题>" --mode research
./council.sh context "<窄 scope>"
./council.sh ask "<单因子/单时间盒问题>"
./council.sh select qwen mimo gptoss20 nemo
./council.sh run-parallel    # Round 1
./council.sh run-parallel    # Round 2 — 语义闭环
./council.sh metrics
./council.sh stop
```

---

## 9. Phase 2 实验（E1–E5）— ✅ 2026-07-10 完成

> Phase 2 已完成。封板待 Owner 确认（建议复验黄金 §7 B 轮去 mock）。

| 编号 | 实验 | 会议 / 证据 | 结果 | 状态 |
|------|------|-------------|------|------|
| E1 | 贵模型 A/B | `meet-20260710-033125` R2 | claude 28.7s vs qwen 42.2s | ✅ |
| E2 | 脚本进 context | `context` 自动 TSLA | `tsla_data.md` 合并 | ✅ |
| E3 | `guest_type: script` | `tsla_feed` | 0.3s，跳过 summarizer | ✅ |
| E4 | `model_tier` | `metrics.json` | 四层 tier 统计 | ✅ |
| E5 | TSLA 跨会 Claim | `clm-000004` | mimo CHALLENGE → CONTESTED | ✅ |

**对比指标（每场必填）：**

- `mock_guest_rate` / `failure_rate`
- `total_duration_s` / `avg_duration_s`
- `confirmed_unique_ratio` / `conflicts_unique_ratio`
- `open_questions` 数量（发散度）
- 语义闭环 pass/fail
- Owner 主观：结论可证伪性（1–5）

---

## 10. 实验会议索引

| 会议 ID | 标签 | 关键文件 |
|---------|------|----------|
| `meet-20260710-015200` | 黄金-真实CLI-2轮-语义闭环 | `metrics.json`, `final.md` |
| `meet-20260710-021348` | 黄金-3人基准 | `meeting_state.json` |
| `meet-20260710-021510` | 黄金-8人扩展 | `quality_comparison.md`（若已生成） |
| `meet-20260710-023309` | TSLA-4轮 | `raw/round-001-qwen.md`, `raw/round-004-mimo.md` |
| `meet-20260710-033125` | **Phase2-E1/E2/E3/E4** | `context/tsla_data.md`, `metrics.json` |
| `meet-20260710-033604` | **Phase2-E5-Claim-CHALLENGE** | `raw/round-001-mimo.md`, `clm-000004` |
| `meet-20260710-040135` | **5人风格分化-grok4.3** | `metrics.json`, `raw/round-001-mimo.md` |

会议产物在 `meetings/`（`.gitignore`），本地保留；指标摘要在本文件。

---

## 11. 元结论（Meta）

1. **Phase 2 已完成（E1–E5）** — 证据脚本、Data Guest、model_tier、TSLA 跨会 Claim 全链真实 CLI 验证。
2. **证据层 ROI 显著** — `tsla_feed` 0.3s 消灭「缺 CLI」OQ；market_context 含真实 $406.55 行情。
3. **贵模型抬上限但非必需** — claude-sonnet-4 比 qwen 更快（28.7s vs 42.2s），结构化输出更收敛。
4. **Claim 跨会复用可行** — `clm-000004` promote → 注入 → mimo CHALLENGE → CONTESTED。
5. **V0.2 封板待 Owner 确认** — Phase 2 达标；建议复验黄金 §7 B 轮（去 mock）后正式封板。

---

*最后更新：2026-07-10 | Phase 2 完成 · E1–E5 ✅*