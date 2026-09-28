"""Coverage helpers: lcov parsing + hard gate evaluation.

Ports the original cli/fuzzpipe coverage section. Only in-scope Solidity
counts (not lib/test/recon/repro). New code should import from here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fuzzpipe.core.state import state_dir


def _cov_in_scope(sf: str) -> bool:
    """A source path that counts toward protocol coverage (not lib/test/recon/repro)."""
    if not sf.endswith(".sol"):
        return False
    norm = sf if sf.startswith("/") else "/" + sf
    return not any(s in norm for s in ("/lib/", "/test/", "/contracts/recon/", "/foundry-repro/"))


def _coverage_scan(target: Path, engine: str):
    """Parse the engine's lcov into in-scope per-file coverage.

    Returns (scope, err_message): scope is {file: {funcs, la, lh}} or
    (None, message) when there is no lcov or nothing in scope.
    """
    lcov = state_dir(target) / "corpus" / engine / "coverage" / "lcov.info"
    if not lcov.exists():
        return None, ("no coverage at %s. Run `fuzzpipe run --engine %s` first (coverage must be "
                      "enabled)." % (lcov, engine))
    files, cur = {}, None
    for line in lcov.read_text().splitlines():
        if line.startswith("SF:"):
            cur = line[3:]
            files[cur] = {"funcs": {}, "la": 0, "lh": 0}
        elif line.startswith("FNDA:") and cur:
            hits, name = line[5:].split(",", 1)
            files[cur]["funcs"][name] = int(hits)
        elif line.startswith("DA:") and cur:
            _, cnt = line[3:].split(",")
            files[cur]["la"] += 1
            if int(cnt) > 0:
                files[cur]["lh"] += 1
    scope = {sf: d for sf, d in files.items() if _cov_in_scope(sf)}
    if not scope:
        return None, "no in-scope source files found in coverage (only lib/test)."
    return scope, None


def _uncovered_functions(scope) -> list:
    """List of 'file::fn' for every in-scope function with zero hits."""
    out = []
    for sf in sorted(scope):
        name = sf.split("/")[-1]
        for fn, hits in sorted(scope[sf]["funcs"].items()):
            if hits == 0:
                out.append("%s::%s" % (name, fn))
    return out


def _overall_pct(scope) -> int:
    la = sum(d["la"] for d in scope.values())
    lh = sum(d["lh"] for d in scope.values())
    return (100 * lh // la) if la else 0


def _cov_waived(entry: str, waivers: dict) -> bool:
    """True if a 'file::fn' uncovered entry is waived — by exact key or bare fn name."""
    return entry in waivers or entry.split("::")[-1] in waivers


def _load_waivers(target: Path, override=None) -> dict:
    f = Path(override) if override else (state_dir(target) / "coverage-waivers.json")
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text())
        return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
    except Exception:
        return {}


def _min_pct_config(target: Path) -> int:
    """Configured minimum in-scope line-% for the run-time gate (default 0)."""
    f = state_dir(target) / "config.json"
    if f.exists():
        try:
            cov = (json.loads(f.read_text()).get("coverage") or {})
            return int(cov.get("min_pct") or 0)
        except Exception:
            return 0
    return 0


def _coverage_gate(target: Path, engine: str, min_pct: int, waivers: dict):
    """Evaluate the hard coverage gate. Returns (available, passed, reasons)."""
    scope, msg = _coverage_scan(target, engine)
    if scope is None:
        return False, False, [msg]
    reasons = []
    unwaived = [u for u in _uncovered_functions(scope) if not _cov_waived(u, waivers)]
    if unwaived:
        reasons.append("%d uncovered entry point(s): %s"
                       % (len(unwaived), ", ".join(unwaived[:8]) + (" ..." if len(unwaived) > 8 else "")))
    pct = _overall_pct(scope)
    if min_pct and pct < min_pct:
        reasons.append("in-scope line coverage %d%% < required %d%%" % (pct, min_pct))
    return True, (not reasons), reasons
