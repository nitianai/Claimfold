"""Council: commands/init_cmd."""
from __future__ import annotations

import argparse

from council.claims import ensure_claims_dir

from council.config import (
    APP_ROOT,
    CONFIG_FILE,
    DATA_ROOT,
    GUEST_TEMPLATE,
    INIT_CONFIG_TEMPLATE,
    REPO_ROOT,
    SUMMARIZER_TEMPLATE,
)


def cmd_init(_: argparse.Namespace) -> None:
    dirs = [
        APP_ROOT / "config",
        APP_ROOT / "prompts",
        APP_ROOT / "prompts" / "guest",
        APP_ROOT / "prompts" / "system",
        APP_ROOT / "prompts" / "reports",
        APP_ROOT / "scripts",
        APP_ROOT / "lib",
        REPO_ROOT / "docs",
        REPO_ROOT / "docs" / "archive",
        DATA_ROOT / "meetings",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    ensure_claims_dir(DATA_ROOT)

    # Fresh installs copy config/guests.yaml.template (kept in sync with guests.yaml).
    init_config = ""
    if INIT_CONFIG_TEMPLATE.is_file():
        init_config = INIT_CONFIG_TEMPLATE.read_text(encoding="utf-8")
    elif CONFIG_FILE.is_file():
        init_config = CONFIG_FILE.read_text(encoding="utf-8")
    else:
        init_config = "max_parallel: 6\nguests: {}\n"

    defaults = {
        CONFIG_FILE: init_config,
        GUEST_TEMPLATE: """# Council Round Context

你正在参加一个多模型架构会议。

你不是主持人。
你只需要回答当前问题。
不要重复历史。
不要写长报告。
不要提出无关方案。

## 议题

{{topic}}

## Owner 原始问题

{{owner_question}}

## 当前已确认观点

{{confirmed_points}}

## 当前冲突

{{conflicts}}

## 当前未决问题

{{open_questions}}

## Owner 最新观点

{{owner_views}}

## 其他嘉宾观点摘要

{{guest_summaries}}

## 你的角色

{{guest_role}}

## 当前轮问题

{{next_question}}

## 输出格式

判断：
证据：
反方视角：
风险：
建议：
是否需要下一轮：
""",
        SUMMARIZER_TEMPLATE: """你是 Meeting Secretary。

你只负责压缩和结构化。
禁止新增观点。
禁止评价观点。
禁止替 Guest 补充理由。
禁止解决冲突。

请从以下 Guest 原始输出中提取：

1. confirmed_points
2. conflicts
3. open_questions
4. guest_position_summary
5. suggested_next_question

要求：
- 每项尽量短
- 总长度不超过 500 字
- 不允许加入原文没有的判断
- 不允许替 Owner 做决策

请输出稳定 Markdown。
""",
    }

    created = []
    for path, content in defaults.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(str(path.relative_to(APP_ROOT)))

    print("Council Engine initialized.")
    if created:
        print("Created:")
        for item in created:
            print(f"  - {item}")
    else:
        print("All default files already present.")

