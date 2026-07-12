# Claimfold 目录结构

## 文档书写规范（基础要求）

本项目 `docs/`、`platform/README.md` 及后续架构文档须遵守：

1. **正文使用中文。**
2. **专用术语**首次出现须标注英文及中文，格式：`English Term（中文名称）`。  
   示例：Event Sourcing（事件溯源）、Platform（平台层）、Projection（投影）、Single Source of Truth（单一事实源）。
3. **代码符号、路径、命令、环境变量**保持英文原样（如 `missionos.ledger.append_event`、`./council.sh`）。
4. **API 契约、事实源矩阵、Phase 门禁**须可审计、可执行，避免纯口号式描述。

---

```
Claimfold/
├── council.sh                      # CLI 转发 → apps/research_council/council.sh
├── README.md
├── platform/                       # Mission OS（任务操作系统）Platform（平台层）
│   ├── pyproject.toml              # name = "missionos"
│   └── missionos/                  # ledger / session / executor / plan 纯核
├── apps/
│   └── research_council/           # Research Council App（应用层）
│       ├── council.sh              # PYTHONPATH + engine 入口
│       ├── pyproject.toml          # dependencies = ["missionos"]
│       ├── config/
│       │   ├── guests.yaml         # 嘉宾与模型配置
│       │   ├── guest_aliases.yaml  # 嘉宾别名
│       │   ├── focus_rules.yaml    # 焦点 → 嘉宾选择规则
│       │   ├── roles.yaml / executors.yaml
│       │   └── bindings/           # scenario 绑定 + executor-guest.yaml
│       ├── lib/
│       │   ├── engine.py           # 薄入口
│       │   ├── runtime_ext.py      # metrics、报告、嘉宾选择
│       │   ├── meeting_quality.py
│       │   └── council/
│       │       ├── adapters/       # Claim/Plan/Executor/Session 适配器
│       │       ├── claims/         # 主张领域逻辑
│       │       ├── commands/       # CLI 子命令
│       │       └── runners/        # 串行 / 并行执行
│       ├── prompts/                # Guest / system / reports 模板
│       ├── scenarios/              # 会议场景定义
│       ├── web/                    # 会议室 Web UI（server.py + static/）
│       └── scripts/                # fetch_equity、compare_meetings 等
├── scripts/
│   ├── ci.sh                       # 本地 CI 门禁
│   ├── check_platform_boundary.sh
│   ├── council-web.sh              # Web UI 启动脚本
│   └── export_claims_bundle.py     # 主张账本导出（manifest + jsonl + index）
├── tests/                          # 回归测试（引用 App lib + platform）
├── docs/                           # 项目规范与实验记录
│   ├── PLATFORM_APP_SPLIT.md
│   ├── CLAIM_LIFECYCLE.md
│   ├── EVOLUTION_PLAN.md       # 进化方案（PR-A…E，对照 Mission OS 原型）
│   └── archive/
├── claims/                         # 跨会话主张账本（gitignore，DATA_ROOT）
├── meetings/                       # 会议产物（gitignore，DATA_ROOT）
└── .current_meeting              # 当前会议指针（DATA_ROOT）
```

**原则：**

- **Platform（平台层）** 在 `platform/missionos/`，不得 import App 模块。
- **App（应用层）** 在 `apps/research_council/`，单向依赖 `missionos`。
- **运行时数据**（`claims/`、`meetings/`、`.current_meeting`）默认在仓库根；可用 `COUNCIL_DATA_ROOT` 覆盖。
- **入口不变：** `./council.sh` 从仓库根调用，行为与搬迁前一致。