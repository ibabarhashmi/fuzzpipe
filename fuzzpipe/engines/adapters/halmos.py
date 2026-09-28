from __future__ import annotations
import shutil
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.engines.adapters.base import classify_rc
from fuzzpipe.engines.protocols import EngineAdapter, CampaignConfig, RunResult


class HalmosAdapter:
    name = "halmos"
    version = "0.1.0"
    required_binaries = ("halmos",)

    async def prepare(self, config: CampaignConfig) -> None:
        pass

    async def run(self, config: CampaignConfig) -> RunResult:
        target = config["target"]
        budget_s = config["budget_s"]
        prop = config.get("config_overrides", {}).get("property")

        if not shutil.which("halmos"):
            return {"status": "untested", "rc": 127, "output": "halmos not found", "artifacts": {}}

        cmd = ["halmos"]
        if prop:
            cmd += ["--function", prop]

        rb = await run_bounded(cmd, budget_s, cwd=str(target))
        status = classify_rc("halmos", rb.rc, budget_s)

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