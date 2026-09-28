# tests/test_adapters_forge_medusa.py
import pytest
from fuzzpipe.engines.adapters.forge import ForgeAdapter
from fuzzpipe.engines.adapters.medusa import MedusaAdapter
def test_forge_missing_is_untested():
    import asyncio
    from pathlib import Path
    ad = ForgeAdapter()
    ad.required_binaries = ("__missing__",)
    cfg = {"target": Path("."), "depth": 64, "limit": 10, "budget_s": 5, "corpus_dir": Path(".")}
    r = asyncio.run(ad.run(cfg))
    assert r["status"] == "untested"
def test_classify_timeout_is_clean():
    from fuzzpipe.engines.adapters.base import classify_rc
    from fuzzpipe.proc.runner import RC_TIMEOUT, RC_MISSING
    assert classify_rc("medusa", RC_TIMEOUT, 600) == "clean"
    assert classify_rc("medusa", RC_MISSING, 600) == "untested"
    assert classify_rc("medusa", 1, 600) == "break_or_error"