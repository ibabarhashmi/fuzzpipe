from __future__ import annotations
import shutil
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.engines.adapters.base import classify_rc
from fuzzpipe.engines.protocols import EngineAdapter, CampaignConfig, RunResult
from fuzzpipe.engines.config import _tester_rel_path, _write_echidna_config


class EchidnaAdapter:
    name = "echidna"
    version = "0.1.0"
    required_binaries = ("echidna", "crytic-compile")

    async def prepare(self, config: CampaignConfig) -> None:
        pass

    async def run(self, config: CampaignConfig) -> RunResult:
        target = config["target"]
        budget_s = config["budget_s"]
        depth = config["depth"]
        limit = config["limit"]
        pt = config.get("config_overrides", {}).get("project_type", "foundry")

        if not shutil.which("echidna") or not shutil.which("crytic-compile"):
            return {"status": "untested", "rc": 127, "output": "echidna or crytic-compile not found", "artifacts": {}}

        _write_echidna_config(target, depth, limit, force=True, pt=pt)

        cmd = ["echidna", _tester_rel_path(target), "--contract", "CryticTester", "--config", "echidna.yaml"]
        rb = await run_bounded(cmd, budget_s, cwd=str(target))
        status = classify_rc("echidna", rb.rc, budget_s)

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