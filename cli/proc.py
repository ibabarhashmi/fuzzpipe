"""
proc.py — process helpers with NO crash surface and REAL wall-clock timeouts.

Two defects this module closes:
  * A tool-version probe must never raise FileNotFoundError when the tool is absent
    (that is precisely the fresh-machine state `doctor` exists to diagnose).
  * A "timeout" must actually terminate a hung child, not be a soft no-op.

It also provides `run_many_bounded` — a bounded concurrent runner that lets the
orchestrator supervise several child processes at once (per-invariant campaigns,
medusa + echidna, parallel reproducer replays), each under its OWN wall-clock bound.
This is the enabling primitive for the v2.2 parallel campaign fan-out; the blocking
`run_bounded` is kept intact and is what each pool worker calls, so a hung child still
cannot outlive its budget.

stdlib only.
"""
from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

# rc sentinels (kept distinct so callers can branch without string matching)
RC_MISSING = 127   # binary not found / OSError
RC_TIMEOUT = 124   # wall-clock budget exceeded, child terminated


def run_probe(cmd, timeout_s=10):
    """Run a short tool probe. Returns (rc, combined_output). NEVER raises.

    A missing binary → (127, "");  a hung probe → (124, "").  Everything a
    `doctor`-style caller needs, with no exception ever escaping.
    """
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (FileNotFoundError, OSError):
        return RC_MISSING, ""
    except subprocess.TimeoutExpired:
        return RC_TIMEOUT, ""


def run_bounded(cmd, timeout_s, cwd=None, env=None):
    """Run a command under a REAL wall-clock bound. Returns (rc, combined_output).

    On timeout the child is terminated by subprocess and we return (124, "TIMEOUT")
    — a hung engine cannot outlive its budget. A missing binary → (127, "MISSING").
    `env`, if given, is MERGED over the current environment (so PATH etc. survive).
    """
    full_env = None
    if env is not None:
        full_env = dict(os.environ)
        full_env.update({k: str(v) for k, v in env.items()})
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout_s, cwd=cwd, env=full_env)
        out = (p.stdout or b"").decode(errors="replace") + (p.stderr or b"").decode(errors="replace")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return RC_TIMEOUT, "TIMEOUT"
    except (FileNotFoundError, OSError):
        return RC_MISSING, "MISSING"


def run_stream(cmd, cwd=None):
    """Run a command inheriting stdio (for interactive/long campaigns). Returns rc.
    NEVER raises on a missing binary."""
    try:
        return subprocess.run(cmd, cwd=cwd).returncode
    except (FileNotFoundError, OSError):
        return RC_MISSING


def default_jobs(n_items=None):
    """A sane default concurrency: leave 2 cores for the OS/orchestrator, at least 1,
    never more workers than there are items to run."""
    try:
        cores = os.cpu_count() or 2
    except Exception:
        cores = 2
    jobs = max(1, cores - 2)
    if n_items is not None:
        jobs = max(1, min(jobs, int(n_items)))
    return jobs


def run_many_bounded(jobs, max_workers=None):
    """Run several commands CONCURRENTLY, each under its OWN wall-clock bound.

    `jobs` is an iterable of dicts, each: {"key": <hashable>, "cmd": [...], "timeout_s": N,
    "cwd": <path or None>}.  Returns an ordered list of (key, rc, output) — same order as the
    input — so callers can attribute each result (e.g. to an invariant id).

    Every child goes through the blocking `run_bounded`, so a hung child is still killed at its
    own bound; the pool only overlaps their wall-clocks. NEVER raises: a worker that somehow
    errors is reported as (key, RC_MISSING, "<error>"). Pool size defaults to `default_jobs`.
    """
    jobs = list(jobs)
    if not jobs:
        return []
    workers = max_workers if max_workers else default_jobs(len(jobs))
    workers = max(1, min(int(workers), len(jobs)))

    def _one(job):
        try:
            rc, out = run_bounded(job["cmd"], job["timeout_s"], cwd=job.get("cwd"))
            return job.get("key"), rc, out
        except Exception as e:                                  # defensive: never let a worker escape
            return job.get("key"), RC_MISSING, "run_many_bounded worker error: %s" % e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_one, jobs))


# --- v2.2 shim: re-export new async implementation for backward compatibility ---
try:
    import asyncio
    from fuzzpipe.proc.runner import (
        BoundedResult, RC_MISSING as _RC_MISSING, RC_TIMEOUT as _RC_TIMEOUT,
        run_bounded as _run_bounded, run_many_bounded as _run_many_bounded, run_probe as _run_probe,
    )
    # Keep original sync signatures available for legacy callers
    run_probe = _run_probe
    def run_bounded(cmd, timeout_s, cwd=None, env=None):
        r = asyncio.run(_run_bounded(cmd, timeout_s, cwd, env))
        return r.rc, r.stdout + r.stderr
    def run_many_bounded(jobs, max_workers=None):
        results = asyncio.run(_run_many_bounded(jobs, max_workers))
        return [(k, r.rc, r.stdout + r.stderr) for k, r in results]
except ImportError:
    pass  # fuzzpipe not available (legacy standalone mode)
