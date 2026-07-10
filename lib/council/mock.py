"""Mock output generators for offline / degraded paths."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from council.formatting import round_tag


def generate_mock_guest_json(*, guest: str, role_id: str, round_num: int, focus: str, label: str) -> str:
    payload = {
        "speaker": guest,
        "role": role_id,
        "round": round_num,
        "focus": focus[:80] if focus else "unknown",
        "position": f"[MOCK/{label}] 第{round_num}轮模拟立场，待接入真实CLI",
        "confidence": 50,
        "evidence": [
            f"模拟证据A round {round_tag(round_num)}",
            "模拟证据B",
        ],
        "risks": ["CLI不可用", "数据待复核"],
        "challenge_to": "",
        "challenge_question": "",
        "need_verification": ["接入真实模型后重跑"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_mock_research_output(
    *,
    guest: str,
    round_num: int,
    label: str,
    state: dict[str, Any],
    injected_claims: list[dict[str, Any]] | None = None,
) -> str:
    """Mock guest output that satisfies semantic loop obligations when prior state exists."""
    conflicts = state.get("conflicts", [])
    confirmed = state.get("confirmed_points", [])
    open_q = state.get("open_questions", [])

    response_lines: list[str] = []
    if conflicts:
        target = conflicts[0]
        response_lines.append(
            f"反方视角：\n- [回应 conflict] {guest} 针对分歧「{target}」：部分同意前提，但认为证据不足，建议用 market_context 复核。"
        )
    if open_q:
        target = open_q[0]
        response_lines.append(
            f"判断：\n- [细化 open_question] 关于「{target}」：{guest} 认为需补充数据源后方可关闭，暂列验证清单。"
        )
    if confirmed and not conflicts:
        target = confirmed[0]
        response_lines.append(
            f"判断：\n- [修正 confirmed_point] 对「{target}」：{guest} 补充时间维度，立场不变但置信度下调。"
        )

    if not response_lines:
        response_lines.append(
            f"判断：\n[MOCK/{label}] Round {round_tag(round_num)} — {guest} 首轮发言，建立基线观点。"
        )

    body = "\n\n".join(response_lines)
    claim_block = ""
    if injected_claims:
        target = injected_claims[0]
        cid = target.get("claim_id", "clm-000001")
        claim_block = f"""
claim_responses:
- claim_id: {cid} | response: CHALLENGE | statement: [MOCK/{label}] {guest} 指出美元走强阶段该命题适用边界过宽
"""
    return f"""{body}

证据：
- 模拟证据 A（可审计测试数据）
- 模拟证据 B
{claim_block}
风险：
- 模拟风险：命令不可用，当前为 mock 模式

建议：
- 接入真实 CLI 后重新运行该轮

是否需要下一轮：
是
"""


def generate_mock_output(*, kind: str, guest: str, round_num: int, label: str, role_id: str = "", focus: str = "") -> str:
    if kind == "guest":
        if role_id:
            return generate_mock_guest_json(
                guest=guest, role_id=role_id, round_num=round_num, focus=focus, label=label
            )
        return f"""判断：
[MOCK/{label}] Round {round_tag(round_num)} — {guest} 的模拟发言。

证据：
- 模拟证据 A（可审计测试数据）
- 模拟证据 B

反方视角：
- 模拟反方：需验证假设是否成立

风险：
- 模拟风险：命令不可用，当前为 mock 模式

建议：
- 接入真实 CLI 后重新运行该轮

是否需要下一轮：
是
"""
    return f"""## confirmed_points
- [MOCK/{label}] {guest} 在 round {round_tag(round_num)} 提出可测试观点

## conflicts
- [MOCK] 与既有方案存在待验证分歧

## open_questions
- 真实 CLI 接入后是否复现相同结构？

## guest_position_summary
{guest}（round {round_tag(round_num)}）倾向先验证最小可行路径。

## suggested_next_question
下一步应优先验证哪条假设？
"""


def generate_mock_market_context(*, scope: str, topic: str, label: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sections = [
        "当前日期",
        "议题",
        "过去两周市场背景",
        "主要指数表现",
        "美股",
        "A股",
        "港股",
        "黄金",
        "原油",
        "美债",
        "美元",
        "人民币",
        "重要宏观事件",
        "重要政策事件",
        "重要财报事件",
        "需要人工复核的数据点",
        "Source Notes",
    ]
    lines = [f"# Market Context\n", f"[MOCK/{label}]\n"]
    for sec in sections:
        lines.append(f"## {sec}")
        if sec == "当前日期":
            lines.append(today)
        elif sec == "议题":
            lines.append(topic)
        else:
            lines.append(f"数据缺失：{scope} — CLI 不可用，需 Owner 人工补充")
        lines.append("")
    return "\n".join(lines)
