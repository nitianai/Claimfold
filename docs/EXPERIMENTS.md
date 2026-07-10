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

## 5. 模型分层实验（稳定性探测）

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
| `openrouter/nvidia/nemotron-3-nano-30b-a3b:free` | 20–40s | 利率外汇、summarizer |
| `openrouter/cohere/north-mini-code:free` | ~51s | 大宗 |
| `openrouter/tencent/hy3:free` | 30–76s | 地缘（已移出默认阵容） |
| `openrouter/poolside/laguna-m.1:free` | 可用 | 地缘/policy（grok 别名） |

### C 级（实验禁用 — 易超时 Mock）

| 模型 | 问题 |
|------|------|
| `qwen3-next-80b:free` | 11s 即 mock |
| `gemma-4-26b:free` | 193s 超时 |
| `llama-3.3-70b:free` | 190s 超时 |
| `nemotron-3-super-120b:free` | 260s 超时 |
| `nemotron-3-ultra-550b:free` | 极慢，已移除 |

---

## 6. 架构实验结论（模型无关）

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

## 7. 冻结的生产配置（2026-07-10）

```yaml
# config/guests.yaml — 实验平台默认阵容（最差基线）
max_parallel: 6

推荐 select:
  qwen        # 宏观锚（gpu-llama，allow_parallel: false）
  mimo        # 个股（deepseek-v4-flash）
  gptoss20    # 结构化推理
  nemo        # 利率/外汇
  laguna      # 地缘（按需，grok 别名）
  north       # 大宗（按需）
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

## 8. 下一阶段实验计划（Phase 2）

| 编号 | 实验 | 目的 | 方法 |
|------|------|------|------|
| E1 | 单点换贵模型 | 测上限 | 同议题同 context，只换 qwen→grok-4.3 或 claude |
| E2 | 金融脚本进 context | 测证据层 ROI | `scripts/fetch_equity.py` → `market_context` |
| E3 | `guest_type: script` | Data Guest 契约 | 跳过 summarizer，raw 直接作证据 |
| E4 | metrics 加 `model_tier` | A/B 可量化 | 对比 floor vs premium delta |
| E5 | Claim promote TSLA 命题 | 跨会复用 | promote 可证伪 conflict → 新会议 CHALLENGE |

**对比指标（每场必填）：**

- `mock_guest_rate` / `failure_rate`
- `total_duration_s` / `avg_duration_s`
- `confirmed_unique_ratio` / `conflicts_unique_ratio`
- `open_questions` 数量（发散度）
- 语义闭环 pass/fail
- Owner 主观：结论可证伪性（1–5）

---

## 9. 实验会议索引

| 会议 ID | 标签 | 关键文件 |
|---------|------|----------|
| `meet-20260710-015200` | 黄金-真实CLI-2轮-语义闭环 | `metrics.json`, `final.md` |
| `meet-20260710-021348` | 黄金-3人基准 | `meeting_state.json` |
| `meet-20260710-021510` | 黄金-8人扩展 | `quality_comparison.md`（若已生成） |
| `meet-20260710-023309` | TSLA-4轮 | `raw/round-001-qwen.md`, `raw/round-004-mimo.md` |

会议产物在 `meetings/`（`.gitignore`），本地保留；指标摘要在本文件。

---

## 10. 元结论（Meta）

1. **Claimfold 作为实验平台已验证可行** — 真实 CLI、并行、语义闭环、Claim 全链均可复现。
2. **Claim Lifecycle V0.2 可生产使用** — §6 全部交付，`claim verify` 通过（见 `docs/CLAIM_LIFECYCLE.md`）。
3. **当前免费实验 = 最差基线** — 以后 Claude/Codex/Grok 4.3 实验是抬天花板，不是推翻架构。
4. **模型质量关键，但在「少而稳、角色对、锚定强」前提下** — 不是越多越好。
5. **V0.3 优先级** — Claim 指标 §8、数据脚本进 context、`guest_type: script`。

---

*最后更新：2026-07-10 | Claim V0.2 封版 · Git: `e31598b`*