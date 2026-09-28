# tests/contract/test_engine_adapter.py
from pathlib import Path
from fuzzpipe.engines.protocols import EngineAdapter
from fuzzpipe.engines.registry import load_adapters
def test_builtin_adapters_load():
    adapters = load_adapters()
    assert "forge" in adapters
    assert isinstance(adapters["forge"], EngineAdapter)
def test_protocol_attrs():
    for name, ad in load_adapters().items():
        assert isinstance(ad.name, str)
        assert isinstance(ad.required_binaries, tuple)
        assert hasattr(ad, "run") and hasattr(ad, "prepare")