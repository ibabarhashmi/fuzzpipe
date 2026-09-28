from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from fuzzpipe.engines.sharding import _tester_rel_path, _disable_slither_for_hh3, _medusa_config_dict, _medusa_workers, state_dir


DEFAULT_MEDUSA_WORKERS = 8


def write_medusa_config(target: Path, depth: int, limit: int, force: bool = False, pt: Optional[str] = None, workers: Optional[int] = None) -> Path:
    cfg = target / "medusa.json"
    if cfg.exists() and not force:
        return cfg
    cfg.write_text(json.dumps(
        _medusa_config_dict(target, depth, limit, pt, ".fuzzpipe/corpus/medusa", workers=workers),
        indent=2))
    print(f"[fuzzpipe] wrote medusa.json (compile target: {_tester_rel_path(target)})")
    return cfg


def write_echidna_config(target: Path, depth: int, limit: int, force: bool = False, pt: Optional[str] = None) -> Path:
    cfg = target / "echidna.yaml"
    if cfg.exists() and not force:
        return cfg
    cfg.write_text("testMode: assertion\ntestLimit: %d\nseqLen: %d\n"
                   "corpusDir: .fuzzpipe/corpus/echidna\ncoverage: true\n" % (int(limit), int(depth)))
    print("[fuzzpipe] wrote echidna.yaml")
    return cfg


def stage_medusa_config_for_invariant(target: Path, inv_id: str, depth: int, limit: int, pt: Optional[str] = None, workers: Optional[int] = None) -> Path:
    out = state_dir(target) / "medusa" / (inv_id + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    corpus = str(state_dir(target) / "corpus" / "medusa" / inv_id)
    cfg = _medusa_config_dict(target, depth, limit, pt, corpus, workers=workers)
    cfg["compilation"]["platformConfig"]["target"] = str(target / _tester_rel_path(target))
    out.write_text(json.dumps(cfg, indent=2))
    return out