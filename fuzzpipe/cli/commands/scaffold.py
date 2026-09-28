from __future__ import annotations
from typing import Optional
import typer

from fuzzpipe.harness.scaffold import scaffold

app = typer.Typer(name="scaffold", help="generate Chimera harness")


@app.callback(invoke_without_command=True)
def scaffold_cmd(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
    force: bool = typer.Option(False, "--force", help="regenerate even if recon/ exists"),
    offline: bool = typer.Option(False, "--offline", help="skip network fetches; vendoring failures are non-fatal"),
):
    code = scaffold(Path(target), project_type, force, offline)
    raise typer.Exit(code)