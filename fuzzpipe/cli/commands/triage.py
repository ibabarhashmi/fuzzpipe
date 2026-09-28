from __future__ import annotations
from typing import Optional
import typer
from pathlib import Path

from fuzzpipe.harness.scaffold import _project_type, state_dir
from fuzzpipe.verdict import render_reproducer_contract
from fuzzpipe import medusa_parse
from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.verdict.gate import lower_and_verify

app = typer.Typer(name="triage", help="broken sequences -> type-aware reproducer + verdict gate")


@app.callback(invoke_without_command=True)
def triage(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
):
    target_path = Path(target).resolve()
    pt = _project_type(target_path, project_type)
    sequences, warnings = _collect_medusa_sequences(target_path)
    for w in warnings:
        print(f"[warn] {w}")
    if not sequences:
        base = state_dir(target_path) / "corpus" / "medusa"
        print(f"[warn] no Medusa failing-sequence artifacts under {base} (checked the flat dir and every shard).")
        print("  Run `fuzzpipe run --engine medusa` first; triage reads its broken sequences.")
        raise typer.Exit(1)

    if pt == "hardhat":
        import_line = 'import {CryticToFoundry} from "./CryticToFoundry.sol";'
        repro = render_reproducer_contract(sequences, import_line)
        out = target_path / "foundry-repro" / "MedusaReproducers.t.sol"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(repro)
        print(f"[ok] Wrote {len(sequences)} reproducer(s) to {out} (byte-exact Foundry replay for a Hardhat target).")
        print("[fuzzpipe] Add the HARM assertion, then run the verdict gate with `forge test` from the foundry-repro context.")
        raise typer.Exit(0)

    # Foundry path
    print("[fuzzpipe] Lowering broken sequences into a Foundry reproducer (type-aware rendering)...")
    import_line = 'import {CryticToFoundry} from "./recon/CryticToFoundry.sol";'
    repro = render_reproducer_contract(sequences, import_line)
    out = target_path / "test" / "MedusaReproducers.t.sol"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(repro)
    print(f"[ok] Wrote {len(sequences)} reproducer test(s) to {out}")

    # verdict gate
    if shutil.which("forge"):
        print("[fuzzpipe] Re-executing reproducers (verdict gate)...")
        rc, out = run_bounded(["forge", "build"], 180, cwd=str(target_path))
        if rc != 0:
            print("[warn] reproducer did not compile -> SUSPECTED (fix the harness/rendering, or the sequence is unrenderable).")
            raise typer.Exit(0)
        rc, out = run_bounded(["forge", "test", "--match-test", "test_repro", "-vv"], 300, cwd=str(target_path))
        broke = "[FAIL" in (out or "")
        if broke:
            print("[ok] Reproducer triggered a break. Now add the HARM assertion, then `fuzzpipe verify` "
                  "to promote it to CONFIRMED (a break without a harm assertion stays SUSPECTED).")
        else:
            print("[warn] Reproducers ran without a break - re-check the sequence/harness (SUSPECTED).")
    else:
        print("[warn] forge absent - wrote the reproducer but cannot re-execute it. Verdict: SUSPECTED until re-run.")
    print("[fuzzpipe] Classify each break: real bug / bad invariant (Stage 2) / bad harness (Stage 3). "
         "See guidance/04 + guidance/05.")
    raise typer.Exit(0)


def _collect_medusa_sequences(target: Path):
    from fuzzpipe.engines.sharding import _medusa_results_dirs
    sequences, warnings = [], []
    for d in _medusa_results_dirs(target):
        seqs, warns = medusa_parse.failing_sequences(d)
        shard = d.parent.name if d.parent.name != "medusa" else None
        for fname, seq in seqs:
            tag = f"{shard}::{fname}" if shard else fname
            sequences.append((tag, seq))
        warnings += warns
    return sequences, warnings


def _medusa_results_dirs(target):
    from fuzzpipe.engines.sharding import state_dir
    base = state_dir(target) / "corpus" / "medusa"
    dirs = []
    flat = base / "test_results"
    if flat.is_dir():
        dirs.append(flat)
    if base.is_dir():
        for shard in sorted(base.iterdir()):
            if shard.is_dir() and shard.name != "test_results":
                tr = shard / "test_results"
                if tr.is_dir():
                    dirs.append(tr)
    return dirs