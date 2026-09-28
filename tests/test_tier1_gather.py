# tests/test_tier1_gather.py
import asyncio
from pathlib import Path
from fuzzpipe.core.pipeline import run_ladder
from fuzzpipe.engines import registry
class FakeClean:
    name="fake-clean"; version="0"; required_binaries=()
    async def prepare(self, c): pass
    async def run(self, c): return {"status":"clean","rc":0,"output":"","artifacts":{}}
    def parse_results(self, d): return []
    def generate_config(self, c): return Path("x")
def test_ladder_clean(monkeypatch):
    monkeypatch.setattr(registry, "load_adapters", lambda: {"forge": FakeClean(), "medusa": FakeClean(), "echidna": FakeClean()})
    res = asyncio.run(run_ladder(Path("."), 10, 100, {0:5,1:5,2:5}, max_tier=1, jobs=2, parallel=False))
    assert all(v in ("clean","untested") for v in res.values())