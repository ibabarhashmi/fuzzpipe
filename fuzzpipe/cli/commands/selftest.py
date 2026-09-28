from __future__ import annotations
from pathlib import Path
from typing import Optional
import subprocess
import typer

app = typer.Typer(name="selftest", help="run the shipped regression suite (zero deps)")


@app.callback(invoke_without_command=True)
def selftest(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="verbose output"),
):
    tests_dir = Path(__file__).resolve().parent.parent.parent.parent / "tests"
    if not tests_dir.exists():
        print(f"[error] no tests/ directory found at {tests_dir}")
        raise typer.Exit(1)
    cmd = ["python3", "-m", "pytest", str(tests_dir), "-v" if verbose else "-q"]
    code = subprocess.run(cmd).returncode
    raise typer.Exit(code)