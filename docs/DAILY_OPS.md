# Claimfold 日常运行手册（Daily Operations）

> **读者：** Owner / 日常使用者  
> **前置：** V0.2 已封板；Platform Phase 5 完成（`missionos-v0.1`）  
> **原则：** 研究会议以 **Web 或 CLI** 启动；定时日频走 **daemon + run-daily**；数据默认在仓库根 `meetings/`、`claims/`。

---

## 1. 环境与安装

```bash
cd /path/to/Claimfold
./scripts/install_editable.sh    # 推荐：pip install -e platform + research-council
./scripts/ci.sh --quick          # 可选：冒烟
```

| 变量 | 默认 | 说明 |
|------|------|------|
| `COUNCIL_DATA_ROOT` | 仓库根 | 会议 / 主张 / `.current_meeting` 数据目录 |
| `COUNCIL_WEB_HOST` | `127.0.0.1` | Web UI 监听地址 |
| `COUNCIL_WEB_PORT` | `8787` | Web UI 端口 |
| `COUNCIL_DAILY_SCOPE` | — | `council-daemon.sh daily` 的 scope（无参数时必填） |
| `COUNCIL_MOCK` | 未设置（真实 CLI） | `1` 时离线 mock；**生产日频勿开** |

**注意：** 勿残留 `/tmp` 下的 `COUNCIL_DATA_ROOT` 或 `COUNCIL_MOCK`（见 `scripts/run_gold_revalidation_cli.sh` 教训）。新开终端执行 `unset COUNCIL_DATA_ROOT COUNCIL_MOCK` 或显式 `export COUNCIL_DATA_ROOT=/path/to/Claimfold`。

---

## 2. 路径 A — Web 日常研究会议（推荐）

### 2.1 启动 Web

```bash
./scripts/council-web.sh
# 浏览器打开 http://127.0.0.1:8787
```

### 2.2 标准流程（推荐：日常启动向导）

左栏顶部的 **日常启动向导** 将研究会议收口为四步：

| 步骤 | UI | 等价 CLI |
|------|-----|----------|
| 1 | 填写**议题** | `start --topic …` |
| 2 | 填写**上下文范围** | `context --scope …` |
| 3 | 邀请嘉宾（默认推荐 3 位：利率策略师 / GPT-OSS / 大宗分析师） | `select` |
| 4 | 点击 **一键启动并跑首轮** | `start` + `context` + `run-parallel` |

向导会自动：会议类型 **并行研究会议**、勾选 **创建后自动生成共享上下文**、等待 context 完成后触发首轮 `run-parallel`。步骤状态与错误通过左栏步骤条 + toast 可见。

**手动路径（与向导等价）：**

| 步骤 | UI 操作 | 等价 CLI |
|------|---------|----------|
| 1 | 左栏填写议题、上下文范围 | `start` + `context` |
| 2 | 会议类型选并行研究会议 | `--mode research` |
| 3 | 勾选「创建后自动生成共享上下文」 | `context` |
| 4 | 邀请已有角色（至少 1 位） | `select` |
| 5 | 点击议题旁 **+** 发布，或用手动向导外的发布 | `POST /api/meeting/start` |
| 6 | 主区 **并行讨论**（可点 2 次做双轮语义闭环） | `run-parallel` ×2 |
| 7 | 右栏运行策略 / HITL；必要时 **继续** | `continue` |
| 8 | **结束** | `stop` |

**API 对照（调试 / 脚本）：**

```bash
# 启动（含 context）
curl -sX POST http://127.0.0.1:8787/api/meeting/start -H 'Content-Type: application/json' \
  -d '{"topic":"未来一周黄金走势","mode":"research","context_scope":"黄金、美元、美债","run_context_after":true,"invited_card_ids":["rates-strategist","quant-researcher","industry-analyst"]}'

# 并行一轮
curl -sX POST http://127.0.0.1:8787/api/run-parallel -H 'Content-Type: application/json' -d '{}'
```

### 2.3 Owner 接管

- 每 3 轮（可配置）引擎可置 `owner_required`；Web 显示 HITL 条，点 **继续** 或 CLI `./council.sh continue`。
- 右栏 **运行策略** 可改 `failure_policy` / `require_before_promote`（仅影响后续轮次）。

### 2.4 产物位置

```
meetings/<meeting_id>/
  meeting_state.json   context/   prompts/   raw/   summaries/
  metrics.json         final.md   events.jsonl
```

---

## 3. 路径 B — CLI 日常研究会议

```bash
./council.sh init
./council.sh start "未来一周黄金走势" --mode research
./council.sh context "黄金、美元、美债"
./council.sh select nemo gptoss20 north    # 3–4 职能位，见 EXPERIMENTS §2
./council.sh run-parallel
./council.sh run-parallel                  # 第二轮：语义闭环
./council.sh metrics
./council.sh stop
```

离线调试：`COUNCIL_MOCK=1 ./council.sh run-parallel`（不替代真实 floor，见 `docs/EXPERIMENTS.md`）。

---

## 4. Session Daemon（会话守护）

入口：`./scripts/council-daemon.sh` → `apps/research_council/scripts/council_daemon.py`（底层 `missionos.daemon`）。

### 4.1 健康检查（cron / 监控）

```bash
./scripts/council-daemon.sh check
# 退出码 0 = 有健康活跃会话；JSON 含 meeting_id / issues
```

### 4.2 状态监视（长期运行）

```bash
./scripts/council-daemon.sh watch --interval 30
# 轮询 .current_meeting 与 meeting_state.json mtime
```

### 4.3 日频触发（需先有活跃会议）

```bash
export COUNCIL_DAILY_SCOPE="TSLA、VIX、美债"
./scripts/council-daemon.sh daily
# 内部调用 ./council.sh run-daily（默认 --skip-context-llm）
```

无活跃会话时输出 `{"skipped": true, "reason": "no healthy session"}` 并退出 0。

---

## 5. run-daily（14:30 日频流水线）

**前提：** 当前指针指向**未 stop** 的研究会议（可先 Web/CLI `start` 保持一个长跑会话）。

```bash
./council.sh run-daily "TSLA、VIX、美债"
# 或显式嘉宾 / 前日 final：
./council.sh run-daily "TSLA、VIX、美债" --guests grok,codex,qoder --prior-meeting meet-20260710-015200
```

| 步骤 | 行为 |
|------|------|
| Context | `build_daily_context`（默认脚本 + 昨日 `final.md`，`--skip-context-llm` 默认开） |
| Guests | `DAILY_DEFAULT_GUESTS` 或 `--guests` |
| 执行 | 单轮 `run_one_parallel_round` |
| 产出 | `meetings/<id>/daily_decision.md` |

### Owner pause 策略

若 `owner_required=true`：

- **手动：** 先 `./council.sh continue`，再 `run-daily`
- **无人值守（cron/systemd）：** 必须加 `--force-owner-continue`，会在 `meeting_state.json` 写入 `daily_owner_override` 审计字段

```bash
./council.sh run-daily "TSLA、VIX、美债" --force-owner-continue
```

---

## 6. systemd 示例

模板在 `scripts/systemd/`（`tests/app/test_daemon_daily.py` 校验文件存在）。

### 6.1 安装步骤

```bash
sudo cp scripts/systemd/council-daemon.service.example /etc/systemd/system/council-daemon.service
sudo cp scripts/systemd/council-daily.service.example /etc/systemd/system/council-daily.service
sudo cp scripts/systemd/council-daily.timer.example /etc/systemd/system/council-daily.timer
```

编辑三处：

1. `User=` — 运行用户  
2. `WorkingDirectory=` / `ExecStart=` — 改为本机 Claimfold 路径  
3. `Environment=COUNCIL_DATA_ROOT=` — 数据根（通常同仓库根）  
4. `Environment=COUNCIL_DAILY_SCOPE=` — 日频 scope  

### 6.2 启用

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now council-daemon.service   # 可选：watch
sudo systemctl enable --now council-daily.timer        # 定时日频
```

**Timer 说明：** 示例 `OnCalendar=*-*-* 06:30:00` 对应 **UTC 06:30 ≈ 北京时间 14:30**（夏令时需自行调整）。`council-daily.service` 为 `Type=oneshot`，由 timer 触发。

### 6.3 日频与 run-daily 衔接

1. 人工或 Web 启动一个长期 `research` 会议（不 `stop`）  
2. Timer 到点 → `council-daemon.sh daily` → `run-daily`  
3. 检查 `meetings/<id>/daily_decision.md`

---

## 7. 运维检查清单

| 检查 | 命令 |
|------|------|
| 当前会议 | `cat .current_meeting` |
| 会话健康 | `./scripts/council-daemon.sh check` |
| 本轮指标 | `./council.sh metrics` |
| 主张列表 | `./council.sh claim list` |
| 账本校验 | `./council.sh claim verify` |
| 实验对照 | `python3 apps/research_council/scripts/compare_meetings.py <id_a> <id_b>` |
| **实验归档** | `./scripts/archive_meeting_experiment.sh [meeting_id] [--baseline <id>]` |
| 黄金复验 | `./scripts/run_gold_revalidation_cli.sh`（真实 CLI，Owner 择机） |

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| Web 启动后数据不在 `meetings/` | 检查 `COUNCIL_DATA_ROOT` 是否指向 `/tmp` |
| `run-daily` 报 owner_required | `continue` 或 `--force-owner-continue` |
| `daemon daily` skipped | 无活跃会话或 state 损坏；`check` 看 `issues` |
| Guest mock 污染 | 确认未设 `COUNCIL_MOCK`；大模型并行数见 EXPERIMENTS §2（3–5 人） |
| 并行按钮无响应 | 看左栏「运行中」任务条；查 `meetings/<id>/errors/` |

---

## 8.1 实验归档（P6-3）

会议结束后一键汇总指标、分析与可选基线对比：

```bash
# 当前会议（.current_meeting）
./scripts/archive_meeting_experiment.sh

# 指定会议 + 基线对照
./scripts/archive_meeting_experiment.sh meet-20260712-145503 \
  --baseline meet-20260710-015200

# 仅打包已有 metrics（不重新计算）
./scripts/archive_meeting_experiment.sh meet-20260712-145503 --no-refresh-metrics
```

**写入 `meetings/<id>/`：**

| 文件 | 内容 |
|------|------|
| `experiment_archive.json` | 分析 + metrics + 语义闭环状态 + 产物索引 |
| `metrics.json` / `metrics.md` | 刷新或保留 |
| `quality_comparison.md` | 仅当指定 `--baseline` |

---

## 9. 相关文档

| 文档 | 内容 |
|------|------|
| [`README.md`](../README.md) | CLI 命令速查 |
| [`docs/EXPERIMENTS.md`](EXPERIMENTS.md) | 实验 floor / 嘉宾阵容 |
| [`docs/V2_BACKLOG.md`](V2_BACKLOG.md) | Phase 6 产品化进度 |
| [`docs/CLAIM_LIFECYCLE.md`](CLAIM_LIFECYCLE.md) | 主张 promote / verify |

---

*最后更新：2026-07-12 | Phase 6 P6-2 日常运行手册*