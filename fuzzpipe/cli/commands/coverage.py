from __future__ import annotations
from typing import Optional
import typer
from pathlib import Path

from fuzzpipe.harness.scaffold import state_dir
from fuzzpipe.harness.config_gen import write_medusa_config, write_echidna_config

app = typer.Typer(name="coverage", help="per-function coverage + uncovered-entry-point flags")


@app.callback(invoke_without_command=True)
def coverage(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    engine: str = typer.Option("medusa", "--engine", "-e", help="engine to read coverage from (medusa|echidna)"),
    gate: bool = typer.Option(False, "--gate", help="blocking gate: fail (exit 2) on unwaived uncovered entry points"),
    min_pct: int = typer.Option(0, "--min-pct", help="minimum in-scope line % required by --gate"),
):
    target_path = Path(target).resolve()
    sd = state_dir(target_path)
    lcov = sd / "corpus" / engine / "coverage" / "lcov.info"
    if not lcov.exists():
        msg = f"no coverage at {lcov}. Run `fuzzpipe run --engine {engine}` first (coverage must be enabled)."
        if gate:
            print(f"[error] {msg}")
        else:
            print(f"[warn] {msg}")
        raise typer.Exit(1)

    waivers = {}
    if gate:
        waivers_path = sd / "coverage-waivers.json"
        if waivers_path.exists():
            import json
            try:
                waivers = {k: v for k, v in json.loads(waivers_path.read_text()).items() if isinstance(v, str) and v.strip()}
            except Exception:
                pass

    from fuzzpipe.harness.scaffold import _cov_in_scope, _coverage_scan, _uncovered_functions, _overall_pct, _cov_waived
    scope, msg = _coverage_scan(target_path, engine)
    if scope is None:
        if "in-scope" in msg:
            print(f"[warn] {msg}")
        else:
            print(f"[error] {msg}")
        raise typer.Exit(1)

    print(f"\n[fuzzpipe] Coverage report ({engine})")
    for sf in sorted(scope):
        d = scope[sf]
        la, lh = d["la"], d["lh"]
        pct = (100 * lh // la) if la else 0
        name = sf.split("/")[-1]
        color = "green" if pct >= 80 else ("yellow" if pct >= 40 else "red")
        print(f"\n  {name}  lines {lh}/{la} ({pct}%)")
        for fn, hits in sorted(d["funcs"].items()):
            waived = gate and _cov_waived(f"{name}::{fn}", waivers)
            mark = "ok " if hits > 0 else ("waiv" if waived else "MISS")
            print(f"    [{mark}] {fn:<30} hits={hits}")
    print()

    overall = _overall_pct(scope)
    if gate:
        uncovered = _uncovered_functions(scope)
        unwaived = [u for u in uncovered if not _cov_waived(u, waivers)]
        reasons = []
        if unwaived:
            reasons.append(f"{len(unwaived)} uncovered entry point(s): {', '.join(unwaived[:8])}{' ...' if len(unwaived) > 8 else ''}")
        if min_pct and overall < min_pct:
            reasons.append(f"in-scope line coverage {overall}% < required {min_pct}%")
        if reasons:
            print(f"[warn] COVERAGE GATE FAILED ({overall}% in-scope lines):")
            for r in reasons:
                print(f"    - {r}")
            print("[warn] Raise coverage (`fuzzpipe gen-handlers`, loosen clamps) or record a justified "
                 "waiver in .fuzzpipe/coverage-waivers.json, then re-run.")
            raise typer.Exit(2)
        print(f"[ok] COVERAGE GATE PASSED — {overall}% in-scope lines, every entry point hit or waived.")
        raise typer.Exit(0)

    uncovered = _uncovered_functions(scope)
    if uncovered:
        print(f"[warn] {len(uncovered)} function(s) NEVER exercised by the campaign:")
        for u in uncovered:
            print(f"    - {u}")
        print("[warn] LOOP-BACK SIGNAL: uncovered entry points mean the harness is incomplete. "
             "Add/loosen handlers (Stage 3) before trusting any 'passed' result.")
        raise typer.Exit(2)
    print(f"[ok] All in-scope functions were exercised. Coverage looks healthy.")
    raise typer.Exit(0)