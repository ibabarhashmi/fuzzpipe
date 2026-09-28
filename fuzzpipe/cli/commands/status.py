from __future__ import annotations
from typing import Optional
import typer
from pathlib import Path

from fuzzpipe.harness.scaffold import load_state, state_dir
from fuzzpipe.ir.persistence import load as load_ir

app = typer.Typer(name="status", help="show pipeline state")


@app.callback(invoke_without_command=True)
def status(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
):
    target_path = Path(target).resolve()
    st = load_state(target_path)
    if not st:
        print("[warn] no run state - run `fuzzpipe init --target <path>` first.")
        raise typer.Exit(1)
    print("[fuzzpipe] fuzzpipe v2.2 status")
    print(f"  target : {target_path}")
    print(f"  stage  : {st.get('stage', '?')}")
    print(f"  updated: {st.get('updated', '?')}")
    invs = load_ir(state_dir(target_path) / "invariants.json")
    if invs:
        print(f"  IR     : {len(invs)} invariant(s)")
    for h in st.get("history", [])[-8:]:
        print(f"    - {h.get('at', '')[:19]}  {h.get('stage', '')}")
    raise typer.Exit(0)