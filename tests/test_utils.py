from pathlib import Path

from utils import atomic_write_json, clamp_int, validate_meeting_id


def test_validate_meeting_id_ok():
    assert validate_meeting_id("meet-20260710-043201") == "meet-20260710-043201"


def test_validate_meeting_id_rejects_bad():
    try:
        validate_meeting_id("../etc/passwd")
        raise AssertionError("expected SystemExit")
    except SystemExit:
        pass


def test_clamp_int_bounds():
    assert clamp_int(99, default=3, min_val=1, max_val=8) == 8
    assert clamp_int("x", default=4, min_val=1, max_val=8) == 4


def test_atomic_write_json():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "state.json"
        atomic_write_json(target, {"ok": True})
        assert target.read_text(encoding="utf-8").strip().startswith("{")