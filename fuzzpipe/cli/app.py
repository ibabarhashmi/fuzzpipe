from __future__ import annotations
from typing import Optional
import sys
import typer
from pathlib import Path

from fuzzpipe.cli.commands import (
    doctor, init, scaffold, build, gen_handlers, verify_harness,
    run, triage, verify, materiality, ir, coverage, status, selftest
)

app = typer.Typer(
    name="fuzzpipe",
    help="Deterministic orchestration CLI for AI-driven EVM/Solidity invariant fuzzing.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def _common_target_option(target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project")) -> str:
    return target


def _common_project_type_option(project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection")) -> Optional[str]:
    return project_type


@app.callback()
def main(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection (foundry|hardhat)"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
    log_level: str = typer.Option("INFO", "--log-level", help="DEBUG|INFO|WARN|ERROR"),
):
    ctx.ensure_object(dict)
    ctx.obj["target"] = target
    ctx.obj["project_type"] = project_type
    ctx.obj["json_output"] = json_output
    ctx.obj["log_level"] = log_level


# Register subcommands
app.add_typer(doctor.app, name="doctor")
app.add_typer(init.app, name="init")
app.add_typer(scaffold.app, name="scaffold")
app.add_typer(build.app, name="build")
app.add_typer(gen_handlers.app, name="gen-handlers")
app.add_typer(verify_harness.app, name="verify-harness")
app.add_typer(run.app, name="run")
app.add_typer(triage.app, name="triage")
app.add_typer(verify.app, name="verify")
app.add_typer(materiality.app, name="materiality")
app.add_typer(ir.app, name="ir")
app.add_typer(coverage.app, name="coverage")
app.add_typer(status.app, name="status")
app.add_typer(selftest.app, name="selftest")


if __name__ == "__main__":
    app()