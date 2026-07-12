"""Minimal second consumer of missionos (Platform split smoke fixture)."""

from platform_smoke.ledger_demo import run_ledger_demo
from platform_smoke.plan_demo import compile_smoke_plan_summary

__all__ = ["run_ledger_demo", "compile_smoke_plan_summary"]