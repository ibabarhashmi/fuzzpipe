"""Legacy sync API shim over fuzzpipe.proc.runner (async).

Preserves the original cli/proc.py contract: sync functions returning
(rc, output) tuples, ThreadPoolExecutor-free concurrent runner returning
(key, rc, output) triples. New code should use fuzzpipe.proc.runner directly.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from fuzzpipe.proc.runner import (
    BoundedResult,
    RC_MISSING,
    RC_TIMEOUT,
    run_bounded as _run_bounded,
    run_many_bounded as _run_many_bounded,
    run_probe as _run_probe,
)

__all__ = [
    "BoundedResult", "RC_MISSING", "RC_TIMEOUT",
    "run_probe", "run_bounded", "run_stream", "default_jobs", "run_many_bounded",
]


def run_probe(cmd, timeout_s=10):
    """Run a short tool probe. Returns (rc, combined_output). NEVER raises."""
    return _run_probe(cmd, timeout_s)


def run_bounded(cmd, timeout_s, cwd=None, env=None):
    """Run a command under a REAL wall-clock bound. Returns (rc, combined_output)."""
    r = asyncio.run(_run_bounded(cmd, timeout_s, cwd=cwd, env=env))
    return r.rc, r.stdout + r.stderr


def run_stream(cmd, cwd=None):
    """Run a command inheriting stdio. Returns rc. NEVER raises on missing binary."""
    try:
        return subprocess.run(cmd, cwd=cwd).returncode
    except (FileNotFoundError, OSError):
        return RC_MISSING


def default_jobs(n_items=None):
    """Sane default concurrency: leave 2 cores for OS, at least 1."""
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

    Returns ordered [(key, rc, output)] matching input order. NEVER raises.
    """
    results = asyncio.run(_run_many_bounded(list(jobs), max_workers))
    return [(k, r.rc, r.stdout + r.stderr) for k, r in results]
