"""Guest voice extraction and position cards tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.web.chat import build_guest_positions
from council.web.voice import extract_guest_voice

MOCK_RAW = """反方视角：
- [回应 conflict] qwen 针对分歧「[MOCK] 与既有方案存在待验证分歧」：部分同意前提，但认为证据不足，建议用 market_context 复核。

判断：
- [细化 open_question] 关于「真实 CLI 接入后是否复现相同结构？」：qwen 认为需补充数据源后方可关闭，暂列验证清单。

证据：
- 模拟证据 A（可审计测试数据）
- 模拟证据 B

风险：
- 模拟风险：命令不可用，当前为 mock 模式

建议：
- 接入真实 CLI 后重新运行该轮

是否需要下一轮：
是
"""


def test_extract_guest_voice_returns_judgment_only():
    voice = extract_guest_voice(MOCK_RAW)
    assert "判断" not in voice or "关于「真实 CLI" in voice
    assert "模拟证据" not in voice
    assert "是否需要下一轮" not in voice
    assert "[回应 conflict]" not in voice
    assert "需补充数据源" in voice


def test_build_guest_positions_from_summary_json():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        (meeting_dir / "summaries").mkdir(parents=True)
        (meeting_dir / "summaries" / "round-001-qwen.summary.json").write_text(
            json.dumps(
                {
                    "guest": "qwen",
                    "guest_position_summary": "黄金短期偏强，目标 4120",
                    "confirmed_points": ["金价4100"],
                    "conflicts": ["美元走强"],
                    "open_questions": ["联储措辞"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {
            "history": [
                {
                    "round": 1,
                    "entries": [
                        {
                            "guest": "qwen",
                            "success": True,
                            "summary_json_path": "summaries/round-001-qwen.summary.json",
                            "used_mock_guest": False,
                            "duration_s": 30,
                        }
                    ],
                }
            ]
        }
        positions = build_guest_positions(meeting_dir, state, guests={})
        assert len(positions) == 1
        assert positions[0]["position"] == "黄金短期偏强，目标 4120"
        assert positions[0]["guest"] == "qwen"