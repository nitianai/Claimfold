# Claimfold

> **多模型研究实验平台** — 可复现、可度量、可审计、可挑战主张。  
> 跨会话试探性主张运行时（Research Runtime）— 不是知识库，不是 AutoGPT。  
> 仓库：<https://github.com/nitianai/Claimfold>

基于 Council Engine V0.3 — 确定性多模型会议工作流。  
**实验记录与结论：** 见 [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md)（项目初心文档，持续更新）。

Engine 负责流程控制；Guest 负责推理；Summarizer 负责压缩；Owner 永远有控制权。

## 核心原则

| 角色 | 职责 |
|------|------|
| **Engine** | 并行调度、validate、从 `summary.json` merge `meeting_state`、metrics、final 报告 |
| **Guest** | 推理（JSON 模式或 Research 模式 Markdown） |
| **Summarizer** | 压缩 raw → `summary.md` + `summary.json`（Research 模式） |
| **Owner** | 每 N 轮可接管；`continue` / `stop` / `view` / `ask` |

## 运行模式

| 模式 | 启动 | 执行 | 状态更新来源 |
|------|------|------|-------------|
| **JSON**（默认 `start`） | `./council.sh start "议题"` | `./council.sh run` | Guest JSON → merge |
| **Research**（并行） | `./council.sh start "议题" --mode research` | `./council.sh run-parallel` | `summary.json` only |
| **Investment** | `./council.sh start "议题" --mode investment` | `./council.sh run-auto` | Guest JSON |

Research 模式推荐工作流：

```
context（共享市场数据）→ select（点名嘉宾）→ run-parallel（并行发言）
```

## 快速开始（Research 并行测试）

```bash
git clone https://github.com/nitianai/Claimfold.git
cd Claimfold

./council.sh init
./council.sh start "测试议题：未来一周黄金走势" --mode research
./council.sh context "黄金、美元、美债、地缘政治"
./council.sh select claude grok nemotron    # 别名 → qwen, laguna, nemo
./council.sh run-parallel
./council.sh metrics
./council.sh audit-summary 1 qwen
./council.sh stop
```

离线测试（无需 CLI）：

```bash
COUNCIL_MOCK=1 ./council.sh run-parallel
```

## 命令参考

| 命令 | 说明 |
|------|------|
| `init` | 初始化目录、配置、模板 |
| `start "议题"` | 创建 meeting；`--mode research\|investment\|standard` |
| `context "范围"` | 生成共享 `context/market_context.md` + `.json` |
| `select <guest>...` | 设置下一轮 `selected_guests`（支持 claude/grok 等别名） |
| `run-parallel` | **P0** 并行调用 selected_guests，各自保存 prompt/raw/summary |
| `run` | 串行单 Guest 一轮（JSON 或 legacy MD 模式） |
| `run-auto` | Investment 模式自动跑至停止条件 |
| `metrics` | 输出并保存 `metrics.md` / `metrics.json` |
| `report` | 生成 `investment_report.md` + `council_experiment_report.md` |
| `next` | 预览下一轮 prompt，不调用模型 |
| `summary` / `status` | 会议摘要 / 完整 state |
| `continue` | 解除 `owner_required`，重置 `rounds_since_owner` |
| `stop` | 停止并生成增强版 `final.md` + metrics |
| `view` / `ask` | Owner 观点 / 更新问题 |
| `audit-summary <round> <guest>` | 审计 prompt / raw / summary.md / summary.json |
| `repair-state` | 迁移旧 guest 名并从 summary 重建 state |
| `tui` | （可选）tmux 三栏视图 |
| `claim promote` | Owner 将 state 条目晋升为主张（写入 `claims/claims.jsonl`） |
| `claim retire <id>` | Owner 退休主张 |
| `claim list` | 列出 `claims_index.json` 投影 |
| `claim rebuild-index` | 从账本重建索引 |
| `claim verify` | 三场会议主张生命周期验收 |

### start 参数

- `-r N` — 每 N **轮**暂停等待 Owner（默认 3）
- `--max-rounds N` — 最大轮次（standard/research 默认 12，investment 默认 100）
- `--mode research` — 启用并行 Research Runtime

## Claim Lifecycle V0.2（跨会话试探性主张）

> **状态：** §6 已交付，Phase 2（E1–E5）已完成；**封板待 Owner 确认**（建议复验黄金 §7 B 轮去 mock）。规范见 [`docs/CLAIM_LIFECYCLE.md`](docs/CLAIM_LIFECYCLE.md)。

```bash
# 会议 A：从分歧晋升
./council.sh claim promote --from-state conflicts[0] \
  --domain finance --subjects gold,USD --regime-tags risk-off \
  --valid-from 2026-07-10 --valid-until 2026-08-01 \
  --evidence raw/round-001-hy3.md

# 会议 B：研究 prompt 自动注入 prior_claims；Guest raw 解析为 RESPOND
./council.sh start "黄金一周走势" --mode research
./council.sh context "黄金、美元"
COUNCIL_MOCK=1 ./council.sh run-parallel

# 会议 C：退休
./council.sh claim retire clm-000001
./council.sh claim verify
```

账本：`claims/claims.jsonl`（只追加）→ `claims/claims_index.json`（可重建投影）。详见 [`docs/CLAIM_LIFECYCLE.md`](docs/CLAIM_LIFECYCLE.md)。

## 目录结构

详见 [`docs/STRUCTURE.md`](docs/STRUCTURE.md)。概要（Platform / App 拆分后）：

```
Claimfold/
  council.sh                          # 转发至 apps/research_council/
  platform/missionos/                 # Platform（平台层）纯核
  apps/research_council/
    config/guests.yaml                # 嘉宾配置
    config/focus_rules.yaml           # 焦点 → 嘉宾规则
    lib/                              # App 运行时
    prompts/ / scenarios/ / scripts/
  claims/                             # 跨会话主张账本（仓库根）
  meetings/<meeting_id>/              # 会议产物（仓库根）
    meeting_state.json
    context/market_context.md
    prompts/ raw/ summaries/ errors/
    metrics.md  final.md
```

实验工具：

```bash
python3 apps/research_council/scripts/compare_meetings.py meet-20260710-021348 meet-20260710-021510
python3 apps/research_council/scripts/fetch_equity.py TSLA --out meetings/<id>/context/tsla_data.md
```

## 配置（guests.yaml）

```yaml
max_parallel: 3

guests:
  qwen:
    role_id: macro_strategist
    command: "opencode run -m gpu-llama/qwen3.6-35b --auto"
    enabled: true
    timeout_seconds: 180
    allow_parallel: true
  summarizer:
    command: "opencode run -m opencode/deepseek-v4-flash-free --auto"
    timeout_seconds: 120
    allow_parallel: false
```

- `max_parallel` — 并行 Guest 上限（默认 3）
- `timeout_seconds` — 单 Guest 超时（默认 180s）
- `allow_parallel: false` — 该 Guest 降级为串行执行

Guest 别名：`claude→qwen`, `grok→laguna`, `codex→codex`（本地无头）, `nemotron→nemo`

## P1：按需点名 selected_guests

`meeting_state.json` 字段：

```json
{
  "selected_guests": [],
  "current_focus": "",
  "round_mode": "parallel",
  "max_rounds": 12,
  "rounds_since_owner": 0,
  "stop_recommendation": ""
}
```

若 `selected_guests` 为空，`run-parallel` 按 `current_focus` / 议题关键词自动选 2~3 位嘉宾（见 `lib/runtime_ext.py` 规则）。

## P2：共享 market_context

Guest prompt 注入 `{{market_context}}`。Guest 优先基于共享上下文推理；自行补充须标注「【新增信息】」。

无法联网时 context 明确写「数据缺失：...」，禁止编造。

## P3：summary.json

机器可读摘要驱动 `meeting_state`；`summary.md` 仅给人看。解析失败写 `errors/` 且不污染 state。

## P4：metrics

`./council.sh metrics` 输出：轮数、发言次数、字数、压缩比、新增点数、JSON 成功率、失败率、平均耗时、最慢 Guest。

## P5：Owner 控制（保留）

1. 每 3 轮（可配置 `-r`）→ `owner_required=true`
2. `continue` / `stop` / `view` / `ask` 仍可用
3. 连续 2 轮无新增 → `stop_recommendation` 提示
4. `max_rounds` 默认 ≤ 12

## 依赖

- `bash`, `python3`, `PyYAML`
- `jq`（可选）
- `tmux`（仅 `tui`）

## 设计定位

Claimfold 是**实验平台**：用免费/混合模型建立**最差基线（floor）**，架构冻结后单点升级 Claude / Codex / Grok 等抬**上限（ceiling）**——换模型不换流程。

Council Engine 提供确定性运行时：并行执行、共享上下文、按需点名、原文留痕、结构化摘要、可度量、可恢复、Owner 可接管。**不是 AutoGPT。**

| 文档 | 内容 |
|------|------|
| [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md) | 实验设计、实测数据、结论、Phase 2 计划 |
| [`docs/CLAIM_LIFECYCLE.md`](docs/CLAIM_LIFECYCLE.md) | 主张生命周期规范 V0.2 |
| [`docs/STRUCTURE.md`](docs/STRUCTURE.md) | 目录架构说明 |