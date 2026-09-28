from __future__ import annotations
import shutil
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.engines.adapters.base import classify_rc
from fuzzpipe.engines.protocols import EngineAdapter, CampaignConfig, RunResult
from fuzzpipe.engines.sharding import _tester_rel_path


class ForgeAdapter:
    name = "forge"
    version = "0.1.0"
    required_binaries = ("forge",)

    async def prepare(self, config: CampaignConfig) -> None:
        pass

    async def run(self, config: CampaignConfig) -> RunResult:
        target = config["target"]
        budget_s = config["budget_s"]
        depth = config["depth"]
        limit = config["limit"]
        prop = config.get("config_overrides", {}).get("property")

        # Check required binaries
        for bin_name in self.required_binaries:
            if not shutil.which(bin_name):
                return {"status": "untested", "rc": 127, "output": f"{bin_name} not found", "artifacts": {}}

        cmd = ["forge", "test", "--match-contract", "CryticToFoundry"]
        if prop:
            cmd += ["--match-test", prop]

        rb = await run_bounded(cmd, budget_s, cwd=str(target))
        status = classify_rc("forge", rb.rc, budget_s)

        return {
            "status": status,
            "rc": rb.rc,
            "output": rb.stdout + rb.stderr,
            "artifacts": {},
        }

    def parse_results(self, corpus_dir: Path) -> list[tuple[str, list[Any]]]:
        return []

    def generate_config(self, config: CampaignConfig) -> Path:
        return Path("stub.json")