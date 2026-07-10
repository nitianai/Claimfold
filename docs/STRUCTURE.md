# Claimfold 目录结构

```
Claimfold/
├── council.sh              # CLI 入口
├── README.md
├── config/
│   └── guests.yaml         # 嘉宾与模型配置
├── lib/                    # 运行时（Phase 2 再拆 engine）
│   ├── engine.py
│   ├── runtime_ext.py
│   ├── claim_lifecycle.py
│   └── meeting_quality.py
├── scripts/                # 实验与数据工具
│   ├── compare_meetings.py
│   └── fetch_equity.py
├── prompts/
│   ├── guest/              # Guest 发言模板
│   ├── system/             # summarizer、market_context
│   └── reports/            # 报告生成模板
├── docs/                   # 项目规范与实验记录
│   ├── EXPERIMENTS.md
│   ├── CLAIM_LIFECYCLE.md
│   ├── STRUCTURE.md
│   └── archive/
├── claims/                 # 跨会话主张账本（gitignore）
└── meetings/               # 会议产物（gitignore）
```

**原则：** 代码在 `lib/`，文档在 `docs/`，模板在 `prompts/`，工具在 `scripts/`，运行时数据在 `meetings/` 与 `claims/`。