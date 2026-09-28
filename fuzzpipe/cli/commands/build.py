from __future__ import annotations
from typing import Optional
import typer

from fuzzpipe.harness.scaffold import _project_type, _compile_harness

app = typer.Typer(name="build", help="compile harness")


@app.callback(invoke_without_command=True)
def build(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
):
    target_path = Path(target).resolve()
    pt = _project_type(target_path, project_type)
    code = _compile_harness(target_path, pt)
    if code == 0:
        print("[ok] Harness compiled.")
    else:
        print("[error] compile failed - fix harness before running a campaign.")
    raise typer.Exit(code)