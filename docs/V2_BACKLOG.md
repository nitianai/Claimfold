# Claimfold v2 Backlog（V0.2 封板后）

> **状态：** Phase 5 ✅ 完成（`missionos-v0.1`）— **Phase 6 产品化/日常化** 待开工  
> **前置：** Research Runtime V0.2 已封板（tag `v0.2`，2026-07-12）  
> **原则：** Platform（`missionos`）与 App（`research_council`）边界已落地（`PLATFORM_APP_SPLIT` Phase 0–4 ✅）；v2 不推翻拆分，只做硬化与日常可用性。

**文档规范：** 正文中文；术语 `English（中文）`。

---

## 0. 当前基线

| 项 | 状态 |
|----|------|
| Platform / App 物理拆分 | ✅ `platform/missionos` + `apps/research_council` |
| Shim 销毁 | ✅ `test_shim_purity.py` |
| 进化 v1 + V0.2 封板 | ✅ `evolution-v1` + `v0.2` |
| CI | ✅ 7 步 · 141 tests |
| Web 会中能力 | ✅ start / speak / runtime-policy / slot 契约 |
| 日常化文档 | ⏳ Phase 6 |

---

## 1. Phase 5 — 平台硬化（Platform Hardening）

> **目标：** 证明 `missionos` 可被第二消费方独立使用；安装与契约文档与代码一致；为产品化提供稳定 Platform 底座。

| ID | 项 | 交付 | 状态 |
|----|-----|------|------|
| P5-1 | 契约文档收口 | `platform/README.md` 状态 → Phase 4 完成；`PLATFORM_APP_SPLIT` §Phase 5 | ✅ |
| P5-2 | Dummy App（哑应用）fixture | `apps/platform_smoke` + `tests/platform/test_platform_smoke_app.py` | ✅ |
| P5-3 | 边界 CI 扩展 | smoke app 不得 import `council`；`check_platform_boundary.sh` 覆盖 `apps/platform_smoke` | ✅ |
| P5-4 | Editable install 文档化 | README / STRUCTURE 明确 `install_editable.sh` 为推荐路径 | ✅ |
| P5-5 | Platform 版本 tag | `missionos-v0.1`（`platform/` 包版本 0.1.0） | ✅ |
| P5-6 | 有意保留的 App 注入层文档化 | `council/plan/paths.py` 等 path-inject shim 记入契约「允许列表」 | ✅ |

**Phase 5 完成定义：** P5-1…P5-6 合入且 CI 绿 → **✅ 可进入 Phase 6**。

---

## 2. Phase 6 — 产品化 / 日常化（Productization）

> **目标：** 少碰 CLI 也能跑研究会议；daemon / 定时任务可文档化复现；输出可归档对比。

| ID | 项 | 交付 | 依赖 |
|----|-----|------|------|
| P6-1 | Web 日常流收口 | 启动向导（议题 → context scope → 嘉宾 → 首轮 parallel）UI 与 API 一条龙；错误态可见 | P5 |
| P6-2 | 日常运行手册 | `docs/DAILY_OPS.md`：`council-web.sh`、`council-daemon.sh watch`、`run-daily`、systemd 示例 | P5 |
| P6-3 | 实验归档脚本 | 一键 `metrics` + `compare_meetings` + `gold_revalidation_report` 汇总到 `meetings/<id>/` | P5 |
| P6-4 | `cmd_init` 卫生 | 默认嘉宾去掉已下线模型名（审计报告 §12） | — |
| P6-5 | 可选：release 门禁 | tag `v0.2.x` 前跑 `run_gold_revalidation_cli.sh`（Owner 择机，非 CI 强制） | P6-3 |

**说明：** Web 已有 `POST /api/meeting/start`（含 `run_context_after`）；P6-1 重点是**默认日常路径**与 UI 引导，而非从零造 API。

---

## 3. 推荐 PR 顺序

```
P5-1 + P5-2（本批）→ P5-3…P5-6 → P6-2 文档 → P6-1 Web → P6-3 归档 → P6-4 卫生
```

| PR | 范围 | 预估 |
|----|------|------|
| **PR-P5a** | V2 backlog + Phase 5 文档 + `platform_smoke` + 测试 | 小 |
| **PR-P5b** | boundary 扩展 + `missionos-v0.1` tag + README install | 小 |
| **PR-P6a** | `DAILY_OPS.md` + daemon/web 示例 | 中 |
| **PR-P6b** | Web 日常启动向导 | 中 |
| **PR-P6c** | 实验归档脚本 + init 卫生 | 小 |

---

## 4. 明确不做（v2 范围外）

- 第二个完整 App 产品（仅 `platform_smoke` fixture）
- `missionos` 公有 PyPI 发布（可 Phase 5 后 Owner 决策）
- Claim bundle import、§8 指标（另开主张层 backlog）
- Platform 内嵌 Claim 投影状态机

---

## 5. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-07-12 | 初版：Owner 确认「先平台硬化 → 再产品化」；P5-1/P5-2 开工 |
| 2026-07-12 | Phase 5 收尾：boundary 扩展、install 文档、`missionos-v0.1` tag、shim allowlist |