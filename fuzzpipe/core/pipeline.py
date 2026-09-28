from __future__ import annotations
from typing import Optional
import asyncio
import os
import warnings
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_many_bounded
from fuzzpipe.engines import registry
from fuzzpipe.engines.adapters.medusa import MedusaAdapter
from fuzzpipe.engines.config import _approved_or_candidate_ids, _shard_has_breaks, state_dir
from fuzzpipe.engines.adapters.base import classify_rc


def _engine_missing(engine: str, pt: str) -> list[str]:
    """Check if required binaries for engine are missing."""
    adapters = registry.load_adapters()
    if engine not in adapters:
        return [engine]
    adapter = adapters[engine]
    missing = [b for b in adapter.required_binaries if not shutil.which(b)]
    return missing


import shutil


async def run_ladder(
    target: Path,
    depth: int,
    limit: int,
    budgets: dict[int, int],
    max_tier: int,
    jobs: Optional[int],
    parallel: bool,
) -> dict[str, str]:
    """Run the tiered ladder (counterexample-first)."""
    results: dict[str, str] = {}
    tiers = [(0, ["forge"]), (1, ["medusa", "echidna"]), (2, ["halmos"])]

    for tier, engines in tiers:
        if tier > max_tier:
            break
        if tier == 2:
            # Check FUZZPIPE_SYMBOLIC env
            if os.environ.get("FUZZPIPE_SYMBOLIC") != "1":
                results["halmos(t2)"] = "skipped"
                continue

        if tier == 1:
            # Tier-1: medusa (sharded) + echidna concurrently
            tier_results, broke = await _run_tier1(target, "foundry", depth, limit, budgets[1], False, None, jobs, parallel)
            results.update(tier_results)
        else:
            broke = False
            for engine in engines:
                status, rc = await _run_engine(target, engine, "foundry", depth, limit, budgets[tier])
                results[f"{engine}(t{tier})"] = status
                if status == "break_or_error":
                    broke = True

        if broke:
            warnings.warn(f"Tier-{tier} surfaced a candidate break -> stop escalating; run `fuzzpipe triage` (the verdict gate).")
            break

    return results


async def _run_engine(
    target: Path,
    engine: str,
    pt: str,
    depth: int,
    limit: int,
    budget_s: int,
    regen: bool = False,
    prop: Optional[str] = None,
    workers: Optional[int] = None,
) -> tuple[str, int]:
    """Run one engine under a REAL wall-clock budget."""
    missing = _engine_missing(engine, pt)
    if missing:
        warnings.warn(f"Tier engine `{engine}` unavailable (missing: {', '.join(missing)}) -> UNTESTED for this tier.")
        return "untested", 127

    adapters = registry.load_adapters()
    adapter = adapters[engine]

    config: dict[str, Any] = {
        "target": target,
        "depth": depth,
        "limit": limit,
        "budget_s": budget_s,
        "corpus_dir": state_dir(target) / "corpus" / engine,
        "config_overrides": {"project_type": pt, "property": prop, "workers": workers, "regen": regen},
    }

    # Special handling for medusa sharding
    if engine == "medusa" and parallel:
        medusa_adapter = adapters["medusa"]
        if isinstance(medusa_adapter, MedusaAdapter):
            shard_results = await medusa_adapter.run_sharded(config)
            # Return first shard status for ladder purposes
            first_status = next(iter(shard_results.values()))["status"]
            return first_status, 0 if first_status == "clean" else 1

    # Run adapter
    result = await adapter.run(config)
    return result["status"], result["rc"]


async def _run_tier1(
    target: Path,
    pt: str,
    depth: int,
    limit: int,
    budget_s: int,
    regen: bool,
    workers: Optional[int],
    jobs: Optional[int],
    parallel: bool,
) -> tuple[dict[str, str], bool]:
    """Tier-1 (medusa + echidna) with concurrency - uses adapters directly."""
    adapters = registry.load_adapters()
    results: dict[str, str] = {}
    broke = False

    # Run medusa
    if "medusa" in adapters:
        medusa_adapter = adapters["medusa"]
        if isinstance(medusa_adapter, MedusaAdapter) and parallel:
            config: dict[str, Any] = {
                "target": target,
                "depth": depth,
                "limit": limit,
                "budget_s": budget_s,
                "corpus_dir": state_dir(target) / "corpus" / "medusa",
                "config_overrides": {"project_type": pt, "workers": workers},
            }
            shard_results = await medusa_adapter.run_sharded(config)
            for shard, result in shard_results.items():
                status = result["status"]
                if status == "break_or_error" and not _shard_has_breaks(target, shard):
                    warnings.warn(f"medusa shard {shard} exited non-zero but wrote no failing sequence -> ERROR, not a break")
                    status = "untested"
                results[f"medusa:{shard}(t1)"] = status
                if status == "break_or_error":
                    broke = True
        else:
            # Single medusa run
            config = {
                "target": target,
                "depth": depth,
                "limit": limit,
                "budget_s": budget_s,
                "corpus_dir": state_dir(target) / "corpus" / "medusa",
                "config_overrides": {"project_type": pt, "workers": workers},
            }
            result = await medusa_adapter.run(config)
            status = result["status"]
            if status == "break_or_error" and not _shard_has_breaks(target, None):
                warnings.warn("medusa exited non-zero but wrote no failing sequence -> ERROR, not a break")
                status = "untested"
            results["medusa(t1)"] = status
            if status == "break_or_error":
                broke = True
    else:
        results["medusa(t1)"] = "untested"

    # Run echidna
    if "echidna" in adapters:
        echidna_adapter = adapters["echidna"]
        config = {
            "target": target,
            "depth": depth,
            "limit": limit,
            "budget_s": budget_s,
            "corpus_dir": state_dir(target) / "corpus" / "echidna",
            "config_overrides": {"project_type": pt},
        }
        result = await echidna_adapter.run(config)
        status = result["status"]
        results["echidna(t1)"] = status
        if status == "break_or_error":
            broke = True
    else:
        results["echidna(t1)"] = "untested"

    return results, broke


# Need to import at module level for type hints
from typing import Any