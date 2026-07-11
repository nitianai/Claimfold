from council.parsers.mock_filter import is_mock_semantic_item
from council.parsers.summary_json import apply_summary_json_to_state


def test_is_mock_semantic_item():
    assert is_mock_semantic_item("[MOCK/guest-cli-missing]")
    assert is_mock_semantic_item("数据缺失：无行情")
    assert not is_mock_semantic_item("TSLA 收 $406.55")


def test_apply_summary_skips_mock_items():
    state = {"confirmed_points": [], "conflicts": [], "open_questions": []}
    data = {
        "guest": "qwen",
        "confirmed_points": ["[MOCK/test]", "TSLA $406.55"],
        "conflicts": [],
        "open_questions": [],
    }
    counts = apply_summary_json_to_state(state, data)
    assert counts["confirmed_points_added"] == 1
    assert state["confirmed_points"] == ["TSLA $406.55"]