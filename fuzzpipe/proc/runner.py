from __future__ import annotations
from typing import Optional
import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

RC_MISSING = 127
RC_TIMEOUT = 124

@dataclass
class BoundedResult:
    rc: int
    stdout: str
    stderr: str
    timed_out: bool

def run_probe(cmd: list[str], timeout_s: float = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (FileNotFoundError, OSError):
        return RC_MISSING, ""
    except subprocess.TimeoutExpired:
        return RC_TIMEOUT, ""

async def run_bounded(
    cmd: list[str],
    timeout_s: float,
    cwd: Path | Optional[str] = None,
    env: dict[str, str] | None = None,
) -> BoundedResult:
    full_env = None
    if env is not None:
        full_env = dict(os.environ)
        full_env.update({k: str(v) for k, v in env.items()})
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=full_env,
        )
        try:
            so, se = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return BoundedResult(RC_TIMEOUT, "TIMEOUT", "", True)
        out = (so or b"").decode(errors="replace")
        err = (se or b"").decode(errors="replace")
        return BoundedResult(proc.returncode or 0, out, err, False)
    except (FileNotFoundError, OSError):
        return BoundedResult(RC_MISSING, "MISSING", "", False)

async def run_many_bounded(jobs: list[dict], max_workers: Optional[int] = None) -> list[tuple]:
    jobs = list(jobs)
    if not jobs:
        return []
    cores = os.cpu_count() or 2
    workers = max_workers or max(1, cores - 2)
    workers = max(1, min(int(workers), len(jobs)))
    sem = asyncio.Semaphore(workers)
    async def _one(job: dict):
        async with sem:
            try:
                r = await run_bounded(job["cmd"], job["timeout_s"], cwd=job.get("cwd"), env=job.get("env"))
                return (job.get("key"), r)
            except Exception as e:
                return (job.get("key"), BoundedResult(RC_MISSING, f"worker error: {e}", "", False))
    results = await asyncio.gather(*[_one(j) for j in jobs])
    by_key = {k: (k, r) for k, r in results}
    return [by_key[j.get("key")] for j in jobs]