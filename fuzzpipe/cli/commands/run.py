from __future__ import annotations
from typing import Optional
import asyncio
import typer
from pathlib import Path

from fuzzpipe.harness.scaffold import _project_type, _compile_harness
from fuzzpipe.core.pipeline import run_ladder
from fuzzpipe.engines.adapters.base import classify_rc
from fuzzpipe.proc.runner import run_bounded

app = typer.Typer(name="run", help="run the tiered ladder (or one --engine)")


@app.callback(invoke_without_command=True)
def run(
    ctx: typer.Context,
    target: str = typer.Option(".", "--target", "-t", help="path to the Solidity project"),
    project_type: Optional[str] = typer.Option(None, "--project-type", help="override project-type autodetection"),
    engine: Optional[str] = typer.Option(None, "--engine", "-e", help="run a single engine (backward-compatible). Omit to run the tiered ladder."),
    max_tier: int = typer.Option(1, "--max-tier", help="highest ladder tier to run (0..2)"),
    depth: int = typer.Option(64, "--depth", help="sequence length / depth"),
    limit: int = typer.Option(100000, "--limit", help="test limit / runs"),
    budget: int = typer.Option(600, "--budget", help="tier-1 wall-clock budget (seconds)"),
    property: Optional[str] = typer.Option(None, "--property", help="focus a single property_* (foundry/halmos)"),
    regen_config: bool = typer.Option(False, "--regen-config", help="overwrite existing engine config"),
    workers: Optional[int] = typer.Option(None, "--workers", help="Medusa internal worker (goroutine) count"),
    jobs: Optional[int] = typer.Option(None, "--jobs", "-j", help="max CONCURRENT campaigns in Tier-1"),
    no_parallel: bool = typer.Option(False, "--no-parallel", help="disable per-invariant fan-out; run one shared medusa campaign"),
):
    target_path = Path(target).resolve()
    pt = _project_type(target_path, project_type)
    _compile_harness(target_path, pt)

    workers_val = workers
    jobs_val = jobs
    parallel = not no_parallel

    # backward-compatible single-engine mode
    if engine:
        if pt == "hardhat" and engine == "foundry":
            print("[error] the `foundry` engine needs Foundry test wiring; on Hardhat use medusa/echidna.")
            raise typer.Exit(1)
        status, rc = asyncio.run(_run_engine(target_path, engine, pt, depth, limit, budget, regen_config, property, workers_val))
        if status == "clean":
            print(f"[ok] {engine} finished with no property break (record coverage - NOT proof of safety).")
        elif status == "untested":
            print(f"[warn] {engine} did not run (engine unavailable).")
        else:
            print(f"[warn] {engine} reported a break or error. Run `fuzzpipe triage` next.")
        raise typer.Exit(0 if status != "break_or_error" else rc)

    # tiered ladder (counterexample-first)
    from fuzzpipe.harness.scaffold import _ladder_budgets
    budgets = _ladder_budgets(target_path, budget)
    max_tier_val = max_tier

    async def _run():
        return await run_ladder(target_path, depth, limit, budgets, max_tier_val, jobs_val, parallel)

    results = asyncio.run(_run())
    print("\n[fuzzpipe] Ladder result:")
    for k, v in results.items():
        print(f"  {k:<18} {v}")
    if any(v == "break_or_error" for v in results.values()):
        raise typer.Exit(1)
    raise typer.Exit(0)


async def _run_engine(target: Path, engine: str, pt: str, depth: int, limit: int, budget_s: int,
                      regen: bool, prop: Optional[str], workers: Optional[int]) -> tuple[str, int]:
    from fuzzpipe.engines import registry
    from fuzzpipe.engines.adapters.base import classify_rc

    missing = _engine_missing(engine, pt)
    if missing:
        print(f"[warn] Tier engine `{engine}` unavailable (missing: {', '.join(missing)}) -> UNTESTED for this tier.")
        return "untested", 127

    adapters = registry.load_adapters()
    adapter = adapters[engine]

    config = {
        "target": target,
        "depth": depth,
        "limit": limit,
        "budget_s": budget_s,
        "corpus_dir": target / ".fuzzpipe" / "corpus" / engine,
        "config_overrides": {"project_type": pt, "property": prop, "workers": workers},
    }
    result = await adapter.run(config)
    return result["status"], result["rc"]


def _engine_missing(engine: str, pt: str) -> list[str]:
    from fuzzpipe.engines import registry
    adapters = registry.load_adapters()
    if engine not in adapters:
        return [engine]
    adapter = adapters[engine]
    import shutil
    return [b for b in adapter.required_binaries if not shutil.which(b)]