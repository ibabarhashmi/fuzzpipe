from __future__ import annotations
from typing import Optional
import json
import typer
from pathlib import Path

from fuzzpipe.ir.persistence import load, dump
from fuzzpipe.ir.model import Invariant, validate
from fuzzpipe.core.state import state_dir

app = typer.Typer(name="ir", help="typed Invariant IR: put/get/list/validate/candidates/coverage-audit")


def _target_path(target: str) -> Path:
    return Path(target).resolve()


@app.command("put")
def ir_put(
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    file: Optional[str] = typer.Option(None, "--file", help="ir.json for `put`"),
):
    target_path = _target_path(target)
    path = state_dir(target_path) / "invariants.json"
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


@app.command("get")
def ir_get(
    id: Optional[str] = typer.Option(None, "--id", help="invariant id for `get`"),
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
):
    target_path = _target_path(target)
    path = state_dir(target_path) / "invariants.json"
    invs = load(path)
    for i in invs:
        if i.id == id:
            print(json.dumps(i.model_dump(), indent=2))
            raise typer.Exit(0)
    print(f"[error] no invariant with id {id}")
    raise typer.Exit(1)


@app.command("list")
def ir_list(
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
):
    target_path = _target_path(target)
    path = state_dir(target_path) / "invariants.json"
    invs = load(path)
    for i in invs:
        print(f"  {i.id:<18} [{i.category}/{i.shape}/{i.scope}] tier{i.tier_hint} {i.status:<9} {i.statement[:60]}")
    raise typer.Exit(0)


@app.command("validate")
def ir_validate(
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
):
    target_path = _target_path(target)
    path = state_dir(target_path) / "invariants.json"
    invs = load(path)
    errs = validate(invs)
    if errs:
        print("[error] IR invalid:")
        for e in errs:
            print(f"  - {e}")
        raise typer.Exit(1)
    print(f"[ok] IR valid ({len(invs)} invariant(s)).")
    raise typer.Exit(0)


@app.command("candidates")
def ir_candidates(
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
):
    target_path = _target_path(target)
    path = state_dir(target_path) / "invariants.json"
    invs = load(path)
    for i in invs:
        if i.status == "candidate":
            print(f"  {i.id:<18} {i.statement[:70]}")
    raise typer.Exit(0)


@app.command("coverage-audit")
def ir_coverage_audit(
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
    src: Optional[str] = typer.Option(None, "--src", help="source dir for `coverage-audit` (default src/ or contracts/)"),
    waivers: Optional[str] = typer.Option(None, "--waivers", help="waivers json for `coverage-audit`"),
):
    target_path = _target_path(target)
    from fuzzpipe.ir.coverage_audit import coverage_audit
    code = coverage_audit(target_path, project_type, src, waivers)
    raise typer.Exit(code)