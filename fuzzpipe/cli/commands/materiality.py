from __future__ import annotations
from typing import Optional
import typer
from pathlib import Path

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.verdict.harm import asserts_harm

app = typer.Typer(name="materiality", help="sweep a reproducer across input scales: dust-only break => bad invariant (FP)")


def _parse_amount(s: str) -> int:
    s = str(s).strip().replace("_", "").lower()
    if "e" in s:
        m, _, e = s.partition("e")
        return int(m or "1") * (10 ** int(e))
    return int(s)


def _log_grid(lo: int, hi: int) -> list[int]:
    lo, hi = max(1, int(lo)), int(hi)
    hi = max(lo, hi)
    grid, dec = [], 1
    while dec <= hi:
        for mant in (1, 2, 5):
            v = mant * dec
            if lo <= v <= hi:
                grid.append(v)
        dec *= 10
    grid.append(lo)
    grid.append(hi)
    return sorted(set(grid))


def _test_broke(out: str, test_name: str) -> Optional[bool]:
    for line in (out or "").splitlines():
        if test_name in line:
            if "[FAIL" in line:
                return True
            if "[PASS" in line:
                return False
    return None


def _materiality_verdict(results: list[tuple[int, Optional[bool]]], material: int) -> tuple[str, int, list[int]]:
    breaking = [m for m, b in results if b is True]
    if not breaking:
        return "HELD", 0, []
    if max(breaking) >= material:
        return "MATERIAL", 0, breaking
    return "DUST-ONLY", 2, breaking


@app.callback(invoke_without_command=True)
def materiality(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    test: str = typer.Option(..., "--test", help="forge test fn that reads the amount from --env and asserts the invariant"),
    min_amt: str = typer.Option("1", "--min", help="smallest sweep amount (int or 1e18 form; default 1)"),
    max_amt: str = typer.Option("1e24", "--max", help="largest sweep amount (default 1e24)"),
    material: str = typer.Option("1e9", "--material", help="materiality threshold in base units (default 1e9)"),
    env: str = typer.Option("FUZZPIPE_SWEEP_AMOUNT", "--env", help="env var the test reads the amount from"),
    budget: int = typer.Option(120, "--budget", help="per-scale forge wall-clock budget (seconds)"),
):
    target_path = Path(target).resolve()
    if not shutil.which("forge"):
        print("[error] forge is required for the materiality sweep. Install: curl -L https://foundry.paradigm.xyz | bash && foundryup")
        raise typer.Exit(2)
    lo, hi, material_val = _parse_amount(min_amt), _parse_amount(max_amt), _parse_amount(material)
    grid = _log_grid(lo, hi)
    print(f"[fuzzpipe] Materiality sweep of `{test}` over {len(grid)} scales [{grid[0]} .. {grid[-1]}]; material threshold = {material_val}")
    results = []
    for m in grid:
        rc, out = run_bounded(["forge", "test", "--match-test", test], budget, cwd=str(target_path), env={env: str(m)})
        broke = _test_broke(out, test)
        results.append((m, broke))
        mark = "\033[31mBROKE\033[0m" if broke else ("\033[32mheld \033[0m" if broke is False else "\033[33m?    \033[0m")
        print(f"  {m:<26} {mark}")
    print()
    verdict, code, breaking = _materiality_verdict(results, material_val)
    if verdict == "HELD":
        print("[ok] Invariant HELD at every scale in the sweep — not falsified here.")
    elif verdict == "MATERIAL":
        print(f"[warn] Invariant BREAKS at a MATERIAL scale (largest break {max(breaking)} >= {material_val}). GENUINE candidate — triage as a real bug.")
    else:
        print(f"[warn] Invariant breaks ONLY below the materiality threshold (largest break {max(breaking)} < {material_val}). This is "
             "the dust-rounding signature of a BAD INVARIANT (false positive): do NOT report it; add a "
             "materiality bound to the invariant.")
    raise typer.Exit(code)