from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.engines.adapters.base import classify_rc
from fuzzpipe.engines.protocols import EngineAdapter, CampaignConfig, RunResult
from fuzzpipe.engines.config import (
    _medusa_config_dict, stage_shard_config, _shard_has_breaks,
    _approved_or_candidate_ids, state_dir, _write_echidna_config,
    _tester_rel_path,
)


class MedusaAdapter:
    name = "medusa"
    version = "0.1.0"
    required_binaries = ("medusa", "crytic-compile")

    async def prepare(self, config: CampaignConfig) -> None:
        pass

    async def run(self, config: CampaignConfig) -> RunResult:
        target = config["target"]
        budget_s = config["budget_s"]
        depth = config["depth"]
        limit = config["limit"]
        pt = config.get("config_overrides", {}).get("project_type", "foundry")
        workers = config.get("config_overrides", {}).get("workers")

        if not shutil.which("medusa") or not shutil.which("crytic-compile"):
            return {"status": "untested", "rc": 127, "output": "medusa or crytic-compile not found", "artifacts": {}}

        # Write single medusa.json for non-sharded run
        corpus = str(state_dir(target) / "corpus" / "medusa")
        cfg_dict = _medusa_config_dict(target, depth, limit, pt, corpus, workers=workers)
        cfg_path = target / "medusa.json"
        cfg_path.write_text(json.dumps(cfg_dict, indent=2))

        cmd = ["medusa", "fuzz"]
        rb = await run_bounded(cmd, budget_s, cwd=str(target))
        status = classify_rc("medusa", rb.rc, budget_s)

        # If break_or_error but no test_results, downgrade to untested
        if status == "break_or_error" and not _shard_has_breaks(target, None):
            import warnings
            warnings.warn("medusa exited non-zero but wrote no failing sequence -> ERROR, not a break")
            status = "untested"

        return {
            "status": status,
            "rc": rb.rc,
            "output": rb.stdout + rb.stderr,
            "artifacts": {"test_results": state_dir(target) / "corpus" / "medusa" / "test_results"},
        }

    def parse_results(self, corpus_dir: Path) -> list[tuple[str, list[Any]]]:
        from fuzzpipe.verdict.reproducer import parse_types
        # Import medusa_parse logic here to avoid circular imports
        from fuzzpipe import medusa_parse
        sequences, _ = medusa_parse.failing_sequences(corpus_dir)
        return sequences

    def generate_config(self, config: CampaignConfig) -> Path:
        return stage_shard_config(config["target"], "default", config["depth"], config["limit"],
                                   config.get("config_overrides", {}).get("project_type", "foundry"),
                                   config.get("config_overrides", {}).get("workers"))

    async def run_sharded(self, config: CampaignConfig) -> dict[str, RunResult]:
        """Run medusa with per-invariant shards."""
        target = config["target"]
        budget_s = config["budget_s"]
        depth = config["depth"]
        limit = config["limit"]
        pt = config.get("config_overrides", {}).get("project_type", "foundry")
        workers = config.get("config_overrides", {}).get("workers")

        if not shutil.which("medusa") or not shutil.which("crytic-compile"):
            return {"medusa": {"status": "untested", "rc": 127, "output": "medusa or crytic-compile not found", "artifacts": {}}}

        ids = _approved_or_candidate_ids(target)
        if not ids:
            # Fall back to single run
            return {"medusa": await self.run(config)}

        import json
        specs = []
        for inv_id in ids:
            cfg = stage_shard_config(target, inv_id, depth, limit, pt, workers)
            specs.append({"key": inv_id, "cmd": ["medusa", "fuzz", "--config", str(cfg)],
                          "timeout_s": budget_s, "cwd": str(target)})

        from fuzzpipe.proc.runner import run_many_bounded
        outcomes = await run_many_bounded(specs)

        results = {}
        for (eng, shard), rb in outcomes:
            status = classify_rc("medusa", rb.rc, budget_s)
            if status == "break_or_error" and not _shard_has_breaks(target, shard):
                import warnings
                warnings.warn(f"medusa shard {shard} exited non-zero but wrote no failing sequence -> ERROR, not a break")
                status = "untested"
            results[shard] = {"status": status, "rc": rb.rc, "output": rb.stdout + rb.stderr, "artifacts": {}}
        return results