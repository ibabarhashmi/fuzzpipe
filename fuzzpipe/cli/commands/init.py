from __future__ import annotations
from typing import Optional
import json
from pathlib import Path
import typer

from fuzzpipe.harness.scaffold import _project_type, _hardhat_major, _hardhat_config_path, _crytic_compile_version, state_dir

app = typer.Typer(name="init", help="create run state for a target")


@app.callback(invoke_without_command=True)
def init(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
):
    target_path = Path(target).resolve()
    if not target_path.exists():
        print(f"[error] target path does not exist: {target_path}")
        raise typer.Exit(1)
    sd = state_dir(target_path)
    sd.mkdir(parents=True, exist_ok=True)
    for sub in ("runs", "corpus", "findings", "poc", "medusa"):
        (sd / sub).mkdir(exist_ok=True)
    from fuzzpipe.harness.scaffold import load_state, save_state, set_stage
    tmpl = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "fuzzpipe.config.json"
    cfg_path = sd / "config.json"
    if tmpl.exists() and not cfg_path.exists():
        try:
            cfg = json.loads(tmpl.read_text())
            cfg["target"] = str(target_path)
            cfg_path.write_text(json.dumps(cfg, indent=2))
        except Exception:
            pass
    inv = sd / "invariants.md"
    if not inv.exists():
        inv.write_text(
            "# Invariants for this run\n\n"
            "## Seed (auditor, HIGH priority)\n"
            "<!-- Stage 0: paste auditor-provided invariants here. Leave empty for Auto mode. -->\n\n"
            "## Discovered + Library (Stage 2 fills this; AWAIT AUDITOR APPROVAL)\n\n"
            "| ID | Statement | Category | Priority | Source | Constrains | Tolerance |\n"
            "|----|-----------|----------|----------|--------|------------|-----------|\n")
    from fuzzpipe.ir.persistence import dump
    if not (sd / "invariants.json").exists():
        dump(sd / "invariants.json", [])
    pt = _project_type(target_path, project_type)
    set_stage(target_path, "0-init", mode="unset", project_type=pt)
    print(f"[ok] Initialized run state at {sd}")
    if pt == "foundry":
        print("[fuzzpipe] Detected project type: Foundry.")
    elif pt == "hardhat":
        hv = _hardhat_major(target_path)
        print(f"[fuzzpipe] Detected project type: Hardhat{(' v' + str(hv)) if hv else ''}. A Foundry compile layer will be added at scaffold.")
        if hv and hv >= 3:
            cc = _crytic_compile_version()
            if cc and tuple(int(x) for x in cc.split(".")[:2]) < (0, 4):
                print(f"[warn] Hardhat 3 needs crytic-compile >= 0.4 (you have {cc}). Upgrade: "
                      "pip install --upgrade 'crytic-compile>=0.4'")
    else:
        print("[warn] Could not detect project type (no foundry.toml or hardhat.config.*). "
             "Pass --project-type foundry|hardhat.")
    print("[fuzzpipe] Next: seed invariants in .fuzzpipe/invariants.md (optional), then `scaffold`.")
    raise typer.Exit(0)