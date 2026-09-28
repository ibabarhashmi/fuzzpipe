from __future__ import annotations
from typing import Optional
from importlib import metadata
from fuzzpipe.engines.protocols import EngineAdapter


def load_adapters() -> dict[str, EngineAdapter]:
    found: dict[str, EngineAdapter] = {}
    try:
        eps = metadata.entry_points(group="fuzzpipe.engines")
    except Exception:
        eps = []
    for ep in list(eps or []):
        try:
            cls = ep.load()
            inst = cls() if isinstance(cls, type) else cls
            found[inst.name] = inst
        except Exception:
            continue
    if not found:
        from fuzzpipe.engines.adapters.forge import ForgeAdapter
        from fuzzpipe.engines.adapters.medusa import MedusaAdapter
        from fuzzpipe.engines.adapters.echidna import EchidnaAdapter
        from fuzzpipe.engines.adapters.halmos import HalmosAdapter
        for c in (ForgeAdapter, MedusaAdapter, EchidnaAdapter, HalmosAdapter):
            try:
                inst = c()
                found[inst.name] = inst
            except Exception:
                continue
    return found


def get_adapter(name: str) -> EngineAdapter:
    ads = load_adapters()
    if name not in ads:
        raise KeyError(f"unknown engine adapter: {name}")
    return ads[name]