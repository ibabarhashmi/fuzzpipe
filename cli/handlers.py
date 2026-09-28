"""Legacy handlers API shim over fuzzpipe.harness.handlers.

Preserves the original cli/handlers.py contract. New code should use
fuzzpipe.harness.handlers directly.
"""
from __future__ import annotations

from fuzzpipe.harness.handlers import (
    CLAMP_CAP,
    MAX_ARR,
    ETH_CAP,
    load_abi,
    mutating_functions,
    handler_arg,
    render_handler,
    render_auto_file,
    generate_handlers,
)

__all__ = [
    "CLAMP_CAP", "MAX_ARR", "ETH_CAP",
    "load_abi", "mutating_functions", "handler_arg",
    "render_handler", "render_auto_file", "generate_handlers",
]
