from __future__ import annotations
from typing import Optional
import json
from pathlib import Path
from fuzzpipe.ir.model import Invariant
def load(path: Path) -> list[Invariant]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("invariants", [])
    return [Invariant.from_dict(d) for d in data]
def dump(path: Path, invs: list[Invariant]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"invariants": [i.model_dump() for i in invs]}, indent=2))