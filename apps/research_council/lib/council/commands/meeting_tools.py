"""Council: meeting repair / audit / TUI commands."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess

from council.adapters.session_adapter import artifact_paths_research

from council.config import LEGACY_GUEST_MAP
from council.formatting import artifact_paths, round_tag
from council.guests import is_json_mode, is_research_mode
from council.slots import format_guest_slots_summary, repair_guest_slots_from_artifacts
from council.state_store import (
    get_current_meeting_dir,
    load_state,
    migrate_guest_names,
    rebuild_state_from_summaries,
    save_state,
)
from missionos.utils import validate_meeting_id


def cmd_repair_slots(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    slots = repair_guest_slots_from_artifacts(meeting_dir, state)
    save_state(meeting_dir, state)
    print(f"Repaired guest_slots for: {state['meeting_id']}")
    print(format_guest_slots_summary(slots))


def cmd_repair_state(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)

    renamed = migrate_guest_names(meeting_dir, state)
    rebuild_state_from_summaries(state, meeting_dir)
    save_state(meeting_dir, state)

    print(f"Repaired meeting: {state['meeting_id']}")
    if renamed:
        print("\nRenamed artifacts:")
        for item in renamed:
            print(f"  - {item}")
    print("\nState rebuilt from summaries:")
    print(f"  confirmed_points: {len(state['confirmed_points'])}")
    print(f"  conflicts: {len(state['conflicts'])}")
    print(f"  open_questions: {len(state['open_questions'])}")
    print(f"  guest_summaries: {', '.join(state['guest_summaries'].keys()) or '(none)'}")


def cmd_audit_summary(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    round_num = int(args.round)
    guest = LEGACY_GUEST_MAP.get(args.guest, args.guest)

    research_paths = artifact_paths_research(meeting_dir, round_num, guest, round_tag)
    json_paths = artifact_paths(meeting_dir, round_num, guest, json_mode=True)
    md_paths = artifact_paths(meeting_dir, round_num, guest, json_mode=False)

    use_research = research_paths["raw"].exists() or is_research_mode(state)
    if use_research:
        paths = research_paths
        audit_items = [
            ("Prompt", paths["prompt"]),
            ("Raw", paths["raw"]),
            ("Summary MD", paths["summary_md"]),
            ("Summary JSON", paths["summary_json"]),
            ("Error", paths["error"]),
        ]
    elif is_json_mode(state):
        paths = json_paths
        audit_items = [("Prompt", paths["prompt"]), ("JSON Raw", paths["raw"])]
    else:
        paths = md_paths
        audit_items = [("Prompt", paths["prompt"]), ("Raw", paths["raw"])]
        if "summary" in paths:
            audit_items.append(("Summary MD", paths["summary"]))

    print(f"Audit — round {round_tag(round_num)}, guest: {guest}\n")
    for label, path in audit_items:
        exists = path.exists()
        print(f"{label}: {path} {'✓' if exists else '✗ MISSING'}")
        if exists and label != "Prompt":
            content = path.read_text(encoding="utf-8")
            print("--- preview ---")
            print(content[:800])
            if len(content) > 800:
                print("... (truncated)")


def cmd_tui(_: argparse.Namespace) -> None:
    if not shutil.which("tmux"):
        raise SystemExit("tmux not found. Install tmux or use CLI commands directly.")

    meeting_dir = get_current_meeting_dir()
    session = f"council-{meeting_dir.name}"

    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode == 0:
        subprocess.run(["tmux", "attach", "-t", session])
        return

    state_file = meeting_dir / "meeting_state.json"
    log_file = meeting_dir / "owner_console.log"
    log_file.touch(exist_ok=True)

    latest_raw = "(no raw output yet)"
    history = load_state(meeting_dir).get("history", [])
    if history:
        latest_raw = str(meeting_dir / history[-1]["raw_output_path"])

    validate_meeting_id(meeting_dir.name)
    subprocess.run(["tmux", "new-session", "-d", "-s", session, "-n", "council"], check=True)
    subprocess.run(
        ["tmux", "send-keys", "-t", session, f"watch -n2 cat {state_file}", "C-m"],
        check=True,
    )
    subprocess.run(["tmux", "split-window", "-h", "-t", session], check=True)
    subprocess.run(
        ["tmux", "send-keys", "-t", session, f"watch -n2 cat {latest_raw}", "C-m"],
        check=True,
    )
    subprocess.run(["tmux", "split-window", "-v", "-t", session], check=True)
    subprocess.run(
        [
            "tmux",
            "send-keys",
            "-t",
            session,
            (
                f"echo Council Owner Console && "
                f"echo Commands: continue | stop | view | ask | run && tail -f {log_file}"
            ),
            "C-m",
        ],
        check=True,
    )
    subprocess.run(["tmux", "select-pane", "-t", f"{session}:0.0"], check=True)
    os.execvp("tmux", ["tmux", "attach", "-t", session])