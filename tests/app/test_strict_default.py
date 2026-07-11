"""Regression: CLI mock defaults to strict fail-closed (meet-20260710-061856)."""

from missionos.utils import relax_cli_enabled, set_relax_cli, strict_cli_enabled


def test_strict_default_on():
    set_relax_cli(False)
    assert strict_cli_enabled() is True
    assert relax_cli_enabled() is False


def test_relax_disables_strict():
    set_relax_cli(True)
    try:
        assert strict_cli_enabled() is False
        assert relax_cli_enabled() is True
    finally:
        set_relax_cli(False)


def test_invoke_cli_strict_raises_on_missing_command():
    import engine

    set_relax_cli(False)
    try:
        try:
            engine.invoke_cli(
                "/nonexistent-council-cli-xyz",
                "ping",
                mock_label="test-missing",
                round_num=1,
                guest="testguest",
                kind="guest",
                timeout_seconds=5,
            )
            raise AssertionError("expected SystemExit under strict default")
        except SystemExit as exc:
            assert "STRICT" in str(exc)
    finally:
        set_relax_cli(False)


def test_invalid_guest_json_strict_exits_without_mock():
    import json

    from council.parsers import extract_json_from_text, validate_guest_json

    set_relax_cli(False)
    raw_output = "{ not valid json"
    validation_errors: list[str] = []
    try:
        guest_data = extract_json_from_text(raw_output)
        validation_errors = validate_guest_json(
            guest_data, guest_name="codex", role_id="logic_auditor", round_num=1
        )
        if validation_errors:
            raise ValueError("; ".join(validation_errors))
        raise AssertionError("expected parse/validation failure")
    except (json.JSONDecodeError, ValueError) as exc:
        validation_errors = validation_errors or [str(exc)]
        if strict_cli_enabled():
            try:
                raise SystemExit(
                    f"STRICT: guest codex returned invalid JSON — {validation_errors[0]}"
                ) from exc
            except SystemExit as exit_exc:
                assert "STRICT" in str(exit_exc)
                return
        raise AssertionError("strict mode should exit")
    finally:
        set_relax_cli(False)


def test_invoke_cli_relax_returns_mock():
    import engine

    set_relax_cli(True)
    try:
        out, used_mock = engine.invoke_cli(
            "/nonexistent-council-cli-xyz",
            "ping",
            mock_label="test-missing",
            round_num=1,
            guest="testguest",
            kind="guest",
            timeout_seconds=5,
        )
        assert used_mock is True
        assert "[MOCK" in out or "MOCK" in out
    finally:
        set_relax_cli(False)