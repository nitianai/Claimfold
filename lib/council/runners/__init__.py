"""Round execution — serial and parallel."""
from council.runners.parallel import (
    process_parallel_guest,
    require_parallel_success,
    run_one_parallel_round,
)
from council.runners.serial import run_one_round

__all__ = [
    "process_parallel_guest",
    "require_parallel_success",
    "run_one_parallel_round",
    "run_one_round",
]