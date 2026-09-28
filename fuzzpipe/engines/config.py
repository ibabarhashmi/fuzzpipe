from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any

from fuzzpipe.core.state import state_dir
from fuzzpipe.ir import load as load_ir
from fuzzpipe.engines.adapters.base import classify_rc


DEFAULT_MEDUSA_WORKERS = 8

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


def _tester_rel_path(target: Path) -> str:
    for cand in ("test/recon/CryticTester.sol", "contracts/recon/CryticTester.sol",
                 "test/CryticTester.sol", "src/CryticTester.sol"):
        if (target / cand).exists():
            return cand
    for p in target.rglob("CryticTester.sol"):
        if "lib/" not in str(p):
            return str(p.relative_to(target))
    return "test/recon/CryticTester.sol"


def _disable_slither_for_hh3(target: Path, pt: str) -> bool:
    return pt == "hardhat" and (_hardhat_major(target) or 2) >= 3


def _hardhat_major(target: Path) -> int | None:
    pkg = target / "node_modules" / "hardhat" / "package.json"
    if pkg.exists():
        try:
            return int(json.loads(pkg.read_text()).get("version", "").split(".")[0])
        except Exception:
            return None
    proj = target / "package.json"
    if proj.exists():
        try:
            data = json.loads(proj.read_text())
            import re
            for sect in ("devDependencies", "dependencies"):
                spec = (data.get(sect) or {}).get("hardhat")
                if spec:
                    m = re.search(r"(\d+)", spec)
                    if m:
                        return int(m.group(1))
        except Exception:
            pass
    return None


def _medusa_workers(target: Path, override: int | None = None) -> int:
    if override:
        return override
    return 8


def _medusa_config_dict(target: Path, depth: int, limit: int, pt: str, corpus: str, targets: list[str] | None = None, workers: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "fuzzing": {
            "workers": _medusa_workers(target, workers),
            "testLimit": int(limit), "callSequenceLength": int(depth),
            "corpusDirectory": corpus,
            "deploymentOrder": targets or ["CryticTester"],
            "targetContracts": targets or ["CryticTester"],
            "testChainConfig": {"codeSizeCheckDisabled": True},
        },
        "compilation": {"platform": "crytic-compile",
                        "platformConfig": {"target": _tester_rel_path(target), "solcVersion": ""}},
        "testing": {"stopOnFailedTest": True, "testAllContracts": False,
                    "assertionTesting": {"enabled": True},
                    "propertyTesting": {"enabled": True, "testPrefix": "property_"},
                    "optimizationTesting": {"enabled": False}},
    }
    if _disable_slither_for_hh3(target, pt):
        d["slither"] = {"useSlither": False}
    return d


def _approved_or_candidate_ids(target: Path) -> list[str]:
    invs = load_ir(state_dir(target) / "invariants.json")
    approved = [i.id for i in invs if i.status == "approved"]
    if approved:
        return approved
    return [i.id for i in invs if i.status == "candidate"]


def stage_shard_config(target: Path, inv_id: str, depth: int, limit: int, pt: str = "foundry", workers: int | None = None) -> Path:
    out = state_dir(target) / "medusa" / (inv_id + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    corpus = str(state_dir(target) / "corpus" / "medusa" / inv_id)
    cfg = _medusa_config_dict(target, depth, limit, pt, corpus, workers=workers)
    cfg["compilation"]["platformConfig"]["target"] = str(target / _tester_rel_path(target))
    out.write_text(json.dumps(cfg, indent=2))
    return out


def _shard_has_breaks(target: Path, shard: str | None) -> bool:
    base = state_dir(target) / "corpus" / "medusa"
    tr = (base / "test_results") if shard is None else (base / shard / "test_results")
    return tr.is_dir() and any(tr.glob("*.json"))


def _write_echidna_config(target: Path, depth: int, limit: int, force: bool = False, pt: str | None = None) -> Path:
    cfg = target / "echidna.yaml"
    if cfg.exists() and not force:
        return cfg
    cfg.write_text("testMode: assertion\ntestLimit: %d\nseqLen: %d\n"
                   "corpusDir: .fuzzpipe/corpus/echidna\ncoverage: true\n" % (int(limit), int(depth)))
    return cfg


def _recon_dir(target, pt: str) -> Path:
    target = Path(target)
    if pt == "hardhat":
        return target / "contracts" / "recon"
    return target / "test" / "recon"