from __future__ import annotations
from typing import Optional
import json
import typer
from pathlib import Path

from fuzzpipe.ir.persistence import load, dump
from fuzzpipe.ir.model import Invariant, validate
from fuzzpipe.harness.scaffold import state_dir

app = typer.Typer(name="ir", help="typed Invariant IR: put/get/list/validate/candidates/coverage-audit")


@app.callback(invoke_without_command=True)
def ir(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="put|get|list|validate|candidates|coverage-audit"),
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
    file: Optional[str] = typer.Option(None, "--file", help="ir.json for `put`"),
    id: Optional[str] = typer.Option(None, "--id", help="invariant id for `get`"),
    src: Optional[str] = typer.Option(None, "--src", help="source dir for `coverage-audit` (default src/ or contracts/)"),
    waivers: Optional[str] = typer.Option(None, "--waivers", help="waivers json for `coverage-audit`"),
):
    target_path = Path(target).resolve()
    path = state_dir(target_path) / "invariants.json"
    if action == "coverage-audit":
        code = _ir_coverage_audit(target_path, project_type, src, waivers)
        raise typer.Exit(code)
    if action == "put":
        if not file:
            print("[error] `ir put` needs --file <ir.json>")
            raise typer.Exit(1)
        raw = json.loads(Path(file).read_text())
        raw = raw.get("invariants", raw) if isinstance(raw, dict) else raw
        invs = [Invariant.from_dict(d) for d in raw]
        errs = validate(invs)
        if errs:
            print("[error] IR validation failed - not saved:")
            for e in errs:
                print(f"  - {e}")
            raise typer.Exit(1)
        dump(path, invs)
        print(f"[ok] stored {len(invs)} invariant(s) to {path}")
        raise typer.Exit(0)
    invs = load(path)
    if action == "validate":
        errs = validate(invs)
        if errs:
            print("[error] IR invalid:")
            for e in errs:
                print(f"  - {e}")
            raise typer.Exit(1)
        print(f"[ok] IR valid ({len(invs)} invariant(s)).")
        raise typer.Exit(0)
    if action == "list":
        for i in invs:
            print(f"  {i.id:<18} [{i.category}/{i.shape}/{i.scope}] tier{i.tier_hint} {i.status:<9} {i.statement[:60]}")
        raise typer.Exit(0)
    if action == "get":
        for i in invs:
            if i.id == id:
                print(json.dumps(i.model_dump(), indent=2))
                raise typer.Exit(0)
        print(f"[error] no invariant with id {id}")
        raise typer.Exit(1)
    if action == "candidates":
        for i in invs:
            if i.status == "candidate":
                print(f"  {i.id:<18} {i.statement[:70]}")
        raise typer.Exit(0)
    print(f"[error] unknown ir action: {action}")
    raise typer.Exit(1)


def _ir_coverage_audit(target: Path, pt: Optional[str], src: Optional[str], waivers: Optional[str]) -> int:
    from fuzzpipe.ir.coverage_audit import coverage_audit
    return coverage_audit(target, pt, src, waivers)