from __future__ import annotations
from typing import Optional
import typer
from pathlib import Path

from fuzzpipe.harness.handlers import generate_handlers

app = typer.Typer(name="gen-handlers", help="auto-generate a COMPLETE ABI-driven handler surface (run after build)")


@app.callback(invoke_without_command=True)
def gen_handlers(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
    contract: Optional[str] = typer.Option(None, "--contract", help="restrict generation to one contract type"),
    src: Optional[str] = typer.Option(None, "--src", help="source dir for privileged-function detection (default src/ or contracts/)"),
    force: bool = typer.Option(False, "--force", help="overwrite TargetFunctionsAuto.sol"),
):
    code = generate_handlers(Path(target), project_type, contract, src, force)
    raise typer.Exit(code)