# tests/test_proc_async.py
import pytest
from fuzzpipe.proc.runner import run_bounded, run_many_bounded, RC_MISSING, RC_TIMEOUT

@pytest.mark.asyncio
async def test_missing_binary_returns_127():
    from pathlib import Path
    from fuzzpipe.proc.runner import BoundedResult
    r = await run_bounded(["__definitely_missing_binary_xyz__"], 5)
    assert r.rc == RC_MISSING
    assert r.timed_out is False

@pytest.mark.asyncio
async def test_timeout_kills_child():
    r = await run_bounded(["sleep", "30"], 0.3)
    assert r.rc == RC_TIMEOUT
    assert r.timed_out is True
    assert "TIMEOUT" in (r.stdout + r.stderr)

@pytest.mark.asyncio
async def test_run_many_preserves_order():
    jobs = [
        {"key": "a", "cmd": ["echo", "hi-a"], "timeout_s": 5, "cwd": None},
        {"key": "b", "cmd": ["echo", "hi-b"], "timeout_s": 5, "cwd": None},
    ]
    out = await run_many_bounded(jobs, max_workers=2)
    assert [k for k, _ in out] == ["a", "b"]
    assert "hi-a" in out[0][1].stdout