from __future__ import annotations
from typing import Optional
import shutil
import typer
from pathlib import Path

from fuzzpipe.harness.scaffold import _project_type, _tester_rel_path

app = typer.Typer(name="verify-harness", help="preflight: assert the engine discovers the harness")


@app.callback(invoke_without_command=True)
def verify_harness(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
):
    target_path = Path(target).resolve()
    pt = _project_type(target_path, project_type)
    tester = target_path / _tester_rel_path(target_path)
    problems = []
    if not tester.exists():
        problems.append(f"CryticTester.sol not found at the expected path ({_tester_rel_path(target_path)})")
    else:
        print(f"[ok] harness entrypoint present: {tester.relative_to(target_path)}")
    if shutil.which("forge"):
        code, out = run_bounded(["forge", "build"], 600, cwd=str(target_path))
        if code != 0:
            problems.append("forge build failed - the engine would not compile this harness")
        else:
            print("[ok] forge build succeeds - Foundry discovers the harness")
    else:
        print("[warn] forge absent - cannot run the compile preflight (install forge).")
    if problems:
        for p in problems:
            print(f"[error] {p}")
        print("[warn] Harness is NOT campaign-ready. Fix the above before `run` (a silently-undiscovered "
             "harness would report every invariant UNTESTED while looking like it ran).")
        raise typer.Exit(1)
    print("[ok] Harness discovery preflight passed.")
    raise typer.Exit(0)