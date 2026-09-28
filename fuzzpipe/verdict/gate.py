from __future__ import annotations
from typing import Optional
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.verdict.harm import asserts_harm


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    SUSPECTED = "SUSPECTED"


@dataclass
class VerdictResult:
    verdict: Verdict
    reason: str
    output: str


def reproduces_specific_break(output: Optional[str], marker: Optional[str]) -> bool:
    """True only if a test FAILED *and* the failure carries the invariant-specific marker."""
    out = output or ""
    failed = ("[FAIL" in out) or re.search(r"\bFAIL(ED|ing)\b", out) is not None
    return bool(failed and marker and (marker in out))


async def lower_and_verify(
    target: Path | str,
    poc_source: str,
    test_name: str,
    marker: str,
    timeout_s: float = 180,
) -> VerdictResult:
    """
    Run the three-gate verdict.
    1. forge build → must compile
    2. forge test --match-test <test_name> → must reproduce SPECIFIC break (marker in revert)
    3. asserts_harm(poc_source) → must assert consequence, not tautology
    """
    rb = await run_bounded(["forge", "build"], timeout_s, cwd=str(target))
    if rb.rc != 0:
        return VerdictResult(Verdict.SUSPECTED, "poc did not compile", rb.stdout + rb.stderr)
    rt = await run_bounded(["forge", "test", "--match-test", test_name, "-vv"], timeout_s, cwd=str(target))
    out = rt.stdout + rt.stderr
    if not reproduces_specific_break(out, marker):
        return VerdictResult(Verdict.SUSPECTED, "did not reproduce the specific property break", out)
    if not asserts_harm(poc_source):
        return VerdictResult(Verdict.SUSPECTED, "no harm assertion — mechanism only", out)
    return VerdictResult(Verdict.CONFIRMED, "poc compiled, re-executed the specific break, asserted harm", out)