from __future__ import annotations
from typing import Optional
import asyncio
import shutil
import typer
from pathlib import Path

from fuzzpipe.verdict.gate import lower_and_verify

app = typer.Typer(name="verify", help="verdict gate on one PoC: compile+reproduce+harm -> CONFIRMED/SUSPECTED")


@app.callback(invoke_without_command=True)
def verify(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    ce: Optional[str] = typer.Option(None, "--ce", help="counterexample id (used as the invariant marker if --marker omitted)"),
    poc: Optional[str] = typer.Option(None, "--poc", help="path to the reproducer .t.sol (for the harm-assertion check)"),
    test: Optional[str] = typer.Option(None, "--test", help="forge --match-test name (default: test_repro)"),
    marker: Optional[str] = typer.Option(None, "--marker", help="invariant-specific revert marker to require in the failure"),
):
    target_path = Path(target).resolve()
    poc_path = Path(poc) if poc else None
    if poc_path and not poc_path.is_absolute():
        poc_path = target_path / poc_path
    src = poc_path.read_text() if (poc_path and poc_path.exists()) else ""
    marker_val = marker or ce or ""
    test_name = test or "test_repro"
    if not shutil.which("forge"):
        print("[error] forge is required for the verdict gate (it re-executes the PoC). Install: curl -L https://foundry.paradigm.xyz | bash && foundryup")
        raise typer.Exit(2)

    import asyncio
    res = asyncio.run(lower_and_verify(target_path, src, test_name, marker_val))
    v, reason, out = res.verdict.value, res.reason, res.output
    (target_path / ".fuzzpipe" / "poc").mkdir(parents=True, exist_ok=True)
    (target_path / ".fuzzpipe" / "poc" / "last_verdict.log").write_text((out or "")[-8000:])
    if v == "CONFIRMED":
        print(f"[ok] VERDICT: CONFIRMED - {reason}")
        raise typer.Exit(0)
    print(f"[warn] VERDICT: SUSPECTED - {reason} (never reported as a bug without a re-executing, harm-asserting PoC).")
    raise typer.Exit(1)