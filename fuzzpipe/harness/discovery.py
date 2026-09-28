from __future__ import annotations
from typing import Optional
from pathlib import Path

from fuzzpipe.engines.sharding import _recon_dir


def discover_instances(target: Path, pt: str) -> dict[str, str]:
    """Map a deployed contract TYPE -> its Setup variable name, by scanning Setup.sol."""
    setup = _recon_dir(target, pt) / "Setup.sol"
    inst = {}
    if not setup.exists():
        return inst
    text = setup.read_text(errors="replace")
    import re as _re
    text = _re.sub(r"/\*.*?\*/", " ", text, flags=_re.S)
    text = "\n".join(ln[:ln.find("//")] if "//" in ln else ln for ln in text.splitlines())
    for m in _re.finditer(r"\b([A-Z]\w*)\s+(?:internal|public|private)?\s*(\w+)\s*;", text):
        inst.setdefault(m.group(1), m.group(2))
    for m in _re.finditer(r"(\w+)\s*=\s*new\s+([A-Z]\w*)\s*\(", text):
        inst.setdefault(m.group(2), m.group(1))
    return inst


def scope_contracts(target: Path) -> set[str]:
    """Contract names declared in-scope via scope.txt."""
    f = target / "scope.txt"
    names = set()
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line.endswith(".sol"):
                names.add(Path(line).stem)
    return names


def manual_handler_names(target: Path, pt: str) -> set[str]:
    """handler_* already defined in TargetFunctions.sol — these win (MANUAL-OVERRIDE)."""
    tf = _recon_dir(target, pt) / "TargetFunctions.sol"
    if not tf.exists():
        return set()
    import re as _re
    return set(_re.findall(r"function\s+(handler_\w+)\s*\(", tf.read_text(errors="replace")))