from __future__ import annotations
from typing import Optional
import shutil
import typer

from fuzzpipe.proc.runner import run_probe

app = typer.Typer(name="doctor", help="check installed tools (never crashes on a missing tool)")


TOOLS = {
    "forge": ("forge", "curl -L https://foundry.paradigm.xyz | bash && foundryup"),
    "medusa": ("medusa", "go install github.com/crytic/medusa@latest"),
    "echidna": ("echidna", "see https://github.com/crytic/echidna/releases (download binary)"),
    "crytic-compile": ("crytic-compile", "pip install 'crytic-compile>=0.4'"),
    "halmos": ("halmos", "pip install halmos"),
    "slither": ("slither", "pip install slither-analyzer"),
    "node": ("node", "https://nodejs.org"),
    "npx": ("npx", "bundled with Node.js"),
}

SUPPORT_MATRIX = [
    ("python3 (stdlib)", "the CLI itself", "no install - zero CLI deps"),
    ("forge (Foundry)", "scaffold, build, Tier-0, the verdict gate", "REQUIRED"),
    ("medusa + crytic-compile", "Tier-1 stateful campaign", "optional"),
    ("echidna", "Tier-1 cross-check", "optional"),
    ("halmos", "Tier-2 symbolic (eval-gated)", "optional; FUZZPIPE_SYMBOLIC=1"),
    ("slither", "seeds the fuzzing dictionary", "optional; absence is a warning"),
    ("node/npx", "Hardhat targets only", "Hardhat v2 AND v3 (crytic-compile >= 0.4)"),
]


@app.callback(invoke_without_command=True)
def doctor(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
):
    """Check fuzzing toolchain (every probe guarded - this never crashes on a missing tool)."""
    print("[fuzzpipe] Checking fuzzing toolchain (every probe guarded - this never crashes on a missing tool)...")
    missing = []
    for name, (binary, install) in TOOLS.items():
        if shutil.which(binary):
            print(f"[ok] {name:<16} found ({shutil.which(binary)})")
        else:
            print(f"[warn] {name:<16} MISSING")
            missing.append((name, install))
    print()
    print("[fuzzpipe] Runtime support matrix (the single source of truth):")
    for rt, need, note in SUPPORT_MATRIX:
        print(f"  {rt:<26} {need:<42} {note}")

    # Hardhat 3 needs crytic-compile >= 0.4 - GUARDED version check
    cc = _crytic_compile_version()
    if cc:
        try:
            ok_hh3 = tuple(int(x) for x in cc.split(".")[:2]) >= (0, 4)
        except Exception:
            ok_hh3 = False
        if ok_hh3:
            print(f"  Hardhat v2 AND v3 supported (crytic-compile {cc} >= 0.4).")
        else:
            print(f"  Hardhat v2 supported. For v3 upgrade crytic-compile (have {cc}, need >= 0.4): "
                  "pip install --upgrade 'crytic-compile>=0.4'")
    else:
        print("  crytic-compile absent - install it (>= 0.4) for Medusa/Echidna and Hardhat v3.")
    print()
    if missing:
        print("[warn] Missing tools - install commands:")
        for name, install in missing:
            print(f"  {name}: {install}")
        print()
        print("[fuzzpipe] Skills-only setup is fine for design work. Install tools before Stage 1+.")
    else:
        print("[ok] All tools present. Ready for the full pipeline (Foundry + Hardhat v2/v3).")
    # doctor is a diagnosis, not a gate: exit 0 always
    raise typer.Exit(0)


def _crytic_compile_version() -> Optional[str]:
    code, out = run_probe(["crytic-compile", "--version"])
    if code == 0 and out.strip():
        return out.strip().split()[-1]
    return None