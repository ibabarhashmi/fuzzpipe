from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.core.state import state_dir
from fuzzpipe.ir import load as load_ir
from fuzzpipe.engines.adapters.base import classify_rc
from fuzzpipe.engines.config import (
    _tester_rel_path, _disable_slither_for_hh3, _hardhat_major,
    _medusa_workers, _medusa_config_dict, stage_shard_config,
    _shard_has_breaks, _approved_or_candidate_ids, _recon_dir,
    _write_echidna_config,
)


def _tester_rel_path(target: Path) -> str:
    from fuzzpipe.engines.config import _tester_rel_path as _impl
    return _impl(target)


def _disable_slither_for_hh3(target: Path, pt: str) -> bool:
    from fuzzpipe.engines.config import _disable_slither_for_hh3 as _impl
    return _impl(target, pt)


def _hardhat_major(target: Path) -> int | None:
    from fuzzpipe.engines.config import _hardhat_major as _impl
    return _impl(target)


def _medusa_workers(target: Path, override: int | None = None) -> int:
    from fuzzpipe.engines.config import _medusa_workers as _impl
    return _impl(target, override)


def _medusa_config_dict(target: Path, depth: int, limit: int, pt: str, corpus: str, targets: list[str] | None = None, workers: int | None = None) -> dict[str, Any]:
    from fuzzpipe.engines.config import _medusa_config_dict as _impl
    return _impl(target, depth, limit, pt, corpus, targets, workers)


def stage_shard_config(target: Path, inv_id: str, depth: int, limit: int, pt: str, workers: int | None = None) -> Path:
    from fuzzpipe.engines.config import stage_shard_config as _impl
    return _impl(target, inv_id, depth, limit, pt, workers)


def _shard_has_breaks(target: Path, shard: str | None) -> bool:
    from fuzzpipe.engines.config import _shard_has_breaks as _impl
    return _impl(target, shard)


def _approved_or_candidate_ids(target: Path) -> list[str]:
    from fuzzpipe.engines.config import _approved_or_candidate_ids as _impl
    return _impl(target)


def _recon_dir(target: Path, pt: str) -> Path:
    from fuzzpipe.engines.config import _recon_dir as _impl
    return _impl(target, pt)


def _write_echidna_config(target: Path, depth: int, limit: int, force: bool = False, pt: str | None = None) -> Path:
    from fuzzpipe.engines.config import _write_echidna_config as _impl
    return _impl(target, depth, limit, force, pt)