from __future__ import annotations
import json
import re as _re
from pathlib import Path
from typing import Any

from fuzzpipe.ir.model import Invariant
from fuzzpipe.ir.persistence import load as load_ir
from fuzzpipe.core.state import state_dir


_SKIP_SRC_PARTS = ("/test/", "/tests/", "/recon/", "/lib/", "/mock", "/mocks/", "/script/",
                   "/node_modules/", "/foundry-repro/")
_PRIV_MODS = ("onlyOwner", "onlyRole", "onlyAdmin", "onlyGovernance", "onlyGovernor",
              "onlyKeeper", "onlyManager", "onlyGuardian", "restricted", "auth")
_FUNC_HEAD_RE = _re.compile(r"\bfunction\s+(\w+)\s*\(")
_VAR_RE = _re.compile(
    r"\b(?:uint\d*|int\d*|address|bool|bytes\d*|string|mapping\s*\([^)]*\))\s+public\s+"
    r"(?:constant\s+|immutable\s+)?(\w+)")


def _src_dirs(target: Path, pt: str, override: Optional[str] = None) -> list[Path]:
    if override:
        return [target / override]
    if pt == "hardhat":
        return [target / "contracts"]
    return [target / "src"]


def _scan_solidity_surface(target: Path, pt: str, override: Optional[str] = None) -> tuple[set, set, set]:
    entry_points, state_vars, privileged = set(), set(), set()
    for base in _src_dirs(target, pt, override):
        if not base.is_dir():
            continue
        for sol in base.rglob("*.sol"):
            p = "/" + str(sol).replace("\\", "/").lstrip("/")
            if any(s in p for s in _SKIP_SRC_PARTS):
                continue
            try:
                text = sol.read_text(errors="replace")
            except Exception:
                continue
            text = _re.sub(r"/\*.*?\*/", " ", text, flags=_re.S)
            text = "\n".join(ln[:ln.find("//")] if "//" in ln else ln for ln in text.splitlines())
            for m in _FUNC_HEAD_RE.finditer(text):
                name = m.group(1)
                if name == "constructor":
                    continue
                depth, j = 0, m.end() - 1
                while j < len(text):
                    if text[j] == "(":
                        depth += 1
                    elif text[j] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                k, tail = j + 1, []
                while k < len(text) and text[k] not in "{;":
                    tail.append(text[k]); k += 1
                tail = "".join(tail)
                if not _re.search(r"\b(external|public)\b", tail):
                    continue
                if _re.search(r"\b(view|pure)\b", tail):
                    continue
                entry_points.add(name)
                if any(mod in tail for mod in _PRIV_MODS):
                    privileged.add(name)
            for m in _VAR_RE.finditer(text):
                state_vars.add(m.group(1))
    return entry_points, state_vars, privileged


def _ir_referenced_tokens(invs: list[Invariant]) -> tuple[set, set]:
    toks, auth_toks = set(), set()
    for i in invs:
        local = set()
        for t in (i.targets or []):
            local.add(str(t).split(".")[-1])
            local.add(str(t))
        expr = (i.predicate or {}).get("expr", "") if isinstance(i.predicate, dict) else ""
        for blob in (expr, i.statement or ""):
            local.update(_re.findall(r"[A-Za-z_]\w*", blob))
        toks.update(local)
        if i.shape == "AUTHORIZATION" or i.category == "anti-property":
            auth_toks.update(local)
    return toks, auth_toks


def _load_waivers(target: Path, override: Optional[str] = None) -> dict:
    f = Path(override) if override else (state_dir(target) / "coverage-waivers.json")
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text())
        return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
    except Exception:
        return {}


def coverage_audit(target: Path, pt: Optional[str] = None, src: Optional[str] = None, waivers: Optional[str] = None) -> int:
    pt = pt or _detect_project_type(target)
    invs = load_ir(state_dir(target) / "invariants.json")
    if not invs:
        print("[error] no IR at %s. Author invariants and `fuzzpipe ir put` them first." % (state_dir(target) / "invariants.json"))
        return 1
    entry_points, state_vars, privileged = _scan_solidity_surface(target, pt, src)
    if not entry_points and not state_vars:
        print("[warn] no Solidity surface found under %s — pass --src <dir> if sources live elsewhere."
              % ", ".join(str(d) for d in _src_dirs(target, pt, src)))
        return 1
    toks, auth_toks = _ir_referenced_tokens(invs)
    waivers_dict = _load_waivers(target, waivers)

    gaps = []
    for fn in sorted(entry_points):
        if fn not in toks and fn not in waivers_dict:
            gaps.append(("entry-point", fn))
    for v in sorted(state_vars):
        if v not in toks and v not in waivers_dict:
            gaps.append(("state-var", v))
    for fn in sorted(privileged):
        if fn not in auth_toks and fn not in waivers_dict:
            gaps.append(("privileged-no-authz", fn))

    print(f"\n[fuzzpipe] IR coverage audit ({target.name})")
    print(f"  entry points: {len(entry_points)}   state vars: {len(state_vars)}   privileged: {len(privileged)}   invariants: {len(invs)}")
    if waivers_dict:
        print(f"  waived: {', '.join(sorted(waivers_dict))}")
    if not gaps:
        print("[ok] Completeness gate PASSED — every surface element is covered by an invariant or waived.")
        return 0
    print(f"[warn] {len(gaps)} coverage GAP(s) — a whole bug class may be invisible to the campaign:")
    for kind, name in gaps:
        print(f"    [{kind}] {name}")
    print(f"[warn] Fix Stage 2 (add invariants) or record a justified waiver in "
          f".fuzzpipe/coverage-waivers.json ({{\"{gaps[0][1]}\": \"why it is safe to skip\"}}).")
    return 2


def _detect_project_type(target: Path) -> Optional[str]:
    has_foundry = (target / "foundry.toml").exists()
    has_hardhat = any((target / ("hardhat.config." + ext)).exists() for ext in ("js", "ts", "cjs"))
    if has_hardhat and not has_foundry:
        return "hardhat"
    if has_hardhat and has_foundry:
        st = load_state(target)
        if st.get("project_type"):
            return st["project_type"]
        return "foundry"
    if has_foundry:
        return "foundry"
    return None


def load_state(target: Path) -> dict:
    f = state_dir(target) / "state.json"
    return json.loads(f.read_text()) if f.exists() else {}