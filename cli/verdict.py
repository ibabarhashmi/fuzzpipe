"""Legacy verdict API shim over fuzzpipe.verdict.gate.

Preserves the original cli/verdict.py contract: sync lower_and_verify
returning a (verdict, reason, output) triple. New code should use
fuzzpipe.verdict.gate directly (async).
"""
from __future__ import annotations

import asyncio

from fuzzpipe.verdict.gate import (
    Verdict,
    VerdictResult,
    reproduces_specific_break,
    lower_and_verify as _lower_and_verify,
)
from fuzzpipe.verdict.reproducer import render_reproducer_contract
from fuzzpipe.verdict.harm import asserts_harm
from fuzzpipe.proc.runner import run_bounded as _run_bounded

__all__ = [
    "Verdict", "VerdictResult", "reproduces_specific_break", "lower_and_verify",
    "render_reproducer_contract", "asserts_harm",
    "invariant_marker", "sanitize", "forge_build", "forge_test",
]


def invariant_marker(inv_id):
    """Hyphenated id embedded in the PoC's harm assertion revert reason."""
    return inv_id


def sanitize(inv_id):
    """Valid Solidity identifier fragment (underscores) for test fn names."""
    import re
    return re.sub(r"[^A-Za-z0-9]", "_", inv_id)


def forge_build(target, timeout_s=180):
    r = asyncio.run(_run_bounded(["forge", "build"], timeout_s, cwd=str(target)))
    return r.rc, r.stdout + r.stderr


def forge_test(target, test_name, timeout_s=180):
    r = asyncio.run(
        _run_bounded(["forge", "test", "--match-test", test_name, "-vv"], timeout_s, cwd=str(target)))
    return r.rc, r.stdout + r.stderr


def lower_and_verify(target, poc_source, test_name, marker, timeout_s=180):
    """Run the three-gate verdict. Returns (verdict, reason, raw_output)."""
    res = asyncio.run(_lower_and_verify(target, poc_source, test_name, marker, timeout_s))
    return res.verdict.value, res.reason, res.output
