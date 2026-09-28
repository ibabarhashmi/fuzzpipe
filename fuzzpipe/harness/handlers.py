from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.verdict.reproducer import parse_types
from fuzzpipe.engines.sharding import _tester_rel_path, state_dir, load_ir


CLAMP_CAP = "type(uint128).max"
MAX_ARR = "4"
ETH_CAP = "1_000 ether"
_OWNER_FNS = ("transferOwnership", "renounceOwnership")


def _decode_abi(raw: Any) -> list:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


def load_abi(target: Path, contract: str) -> list:
    out = target / "out" / (contract + ".sol") / (contract + ".json")
    if out.exists():
        try:
            j = json.loads(out.read_text())
            abi = _decode_abi(j.get("abi"))
            if abi:
                return abi
        except Exception:
            pass
    combined = target / "crytic-export" / "combined_solc.json"
    if combined.exists():
        try:
            j = json.loads(combined.read_text())
            contracts = j.get("contracts", {})
            for key, val in contracts.items():
                if key.rsplit(":", 1)[-1] == contract:
                    abi = _decode_abi(val.get("abi"))
                    if abi:
                        return abi
        except Exception:
            pass
    return []


def mutating_functions(abi: list) -> list:
    seen = set()
    for e in abi or []:
        if e.get("type") != "function":
            continue
        if e.get("stateMutability") in ("view", "pure"):
            continue
        name = e.get("name")
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        yield e


def _is_auto_renderable(t: str) -> bool:
    t = (t or "").strip()
    if t.startswith("("):
        return False
    if t.endswith("[]"):
        base = t[:-2]
        return _is_leaf(base)
    return _is_leaf(t)


def _is_leaf(t: str) -> bool:
    t = (t or "").strip()
    if t in ("bool", "address", "string", "bytes"):
        return True
    if t.startswith(("uint", "int")):
        return True
    if t.startswith("bytes"):
        return True
    return False


def _int_bounds(t: str) -> tuple[str, str, Optional[str]]:
    t = t.strip()
    if t in ("uint", "uint256"):
        return ("0", CLAMP_CAP, None)
    if t in ("int", "int256"):
        return ("-int256(%s)" % CLAMP_CAP, "int256(%s)" % CLAMP_CAP, None)
    if t.startswith("uint"):
        return ("0", "uint256(type(%s).max)" % t, t)
    if t.startswith("int"):
        return ("-int256(uint256(type(%s).max) / 2)" % t.replace("int", "uint"),
                "int256(uint256(type(%s).max) / 2)" % t.replace("int", "uint"), t)
    return ("0", CLAMP_CAP, None)


def handler_arg(idx: int, abi_type: str) -> tuple[list[str], list[str], str] | None:
    t = (abi_type or "").strip()
    p = "arg%d" % idx
    if not _is_auto_renderable(t):
        return None
    if t == "bool":
        return (["bool %s" % p], [], p)
    if t == "address":
        return (["uint256 %sSeed" % p], ["address %s = _pickAddr(%sSeed);" % (p, p)], p)
    if t == "string":
        return (["string memory %s" % p], [], p)
    if t == "bytes":
        return (["bytes memory %s" % p], [], p)
    if t.startswith("bytes"):
        return (["%s %s" % (t, p)], [], p)
    if t.startswith(("uint", "int")):
        lo, hi, cast = _int_bounds(t)
        decl = "%s %s" % (t, p)
        if cast is None:
            return ([decl], ["%s = between(%s, %s, %s);" % (p, p, lo, hi)], p)
        base = "int256" if t.startswith("int") else "uint256"
        return ([decl], ["%s = %s(between(%s(%s), %s, %s));" % (p, cast, base, p, lo, hi)], p)
    if t.endswith("[]"):
        base = t[:-2]
        var = "%sArr" % p
        body = ["uint256 %sLen = between(%sN, 0, %s);" % (p, p, MAX_ARR),
                "%s[] memory %s = new %s[](%sLen);" % (base, var, base, p),
                "for (uint256 i; i < %sLen; ++i) {" % p,
                "    %s" % _array_elem_fill(base, var, p),
                "}"]
        return (["uint256 %sN" % p, "uint256 %sSeed" % p], body, var)
    return None


def _array_elem_fill(base: str, var: str, p: str) -> str:
    seed = "%sSeed + i" % p
    if base == "address":
        return "%s[i] = _pickAddr(%s);" % (var, seed)
    if base == "bool":
        return "%s[i] = ((%s) %% 2 == 0);" % (var, seed)
    if base in ("uint", "uint256"):
        return "%s[i] = uint256(keccak256(abi.encode(%s))) %% (%s);" % (var, seed, CLAMP_CAP)
    if base.startswith("uint"):
        return "%s[i] = %s(uint256(keccak256(abi.encode(%s))) %% (uint256(type(%s).max) + 1));" % (
            var, base, seed, base)
    if base.startswith("int"):
        return "%s[i] = %s(int256(uint256(keccak256(abi.encode(%s))) %% (%s)));" % (
            var, base, seed, CLAMP_CAP)
    return "%s[i] = abi.encodePacked(%s);" % (var, seed)


def _handler_name(instance: str, fn_name: str, multi: bool) -> str:
    return "handler_%s_%s" % (instance, fn_name) if multi else "handler_%s" % fn_name


def render_handler(instance: str, fn: dict, multi: bool = False, privileged: bool = False) -> tuple[str, str, str]:
    fn_name = fn["name"]
    inputs = fn.get("inputs", []) or []
    payable = fn.get("stateMutability") == "payable"
    hname = _handler_name(instance, fn_name, multi)
    is_priv = privileged or fn_name in _OWNER_FNS

    params, body, call_args, needs_stub = [], [], [], False
    for i, inp in enumerate(inputs):
        r = handler_arg(i, inp.get("type", ""))
        if r is None:
            needs_stub = True
            break
        p, b, ca = r
        params += p
        body += b
        call_args.append(ca)

    if needs_stub:
        return hname, _render_stub(hname, instance, fn_name), "STUB(tuple)"
    if is_priv:
        src = _render_privileged(hname, instance, fn_name, params, body, call_args, payable)
        return hname, src, "GEN(privileged)"
    return hname, _render_plain(hname, instance, fn_name, params, body, call_args, payable), "GEN"


def _call_line(instance: str, fn_name: str, call_args: list[str], payable: bool, value_expr: Optional[str] = None) -> str:
    val = "{value: %s}" % value_expr if (payable and value_expr) else ""
    return "try %s.%s%s(%s) {} catch {}" % (instance, fn_name, val, ", ".join(call_args))


def _render_plain(hname: str, instance: str, fn_name: str, params: list[str], body: list[str], call_args: list[str], payable: bool) -> str:
    sig = ["uint256 actorSeed"] + params + (["uint256 msgValue"] if payable else [])
    lines = ["    function %s(%s) public updateGhosts {" % (hname, ", ".join(sig)),
             "        _useActor(actorSeed);"]
    lines += ["        " + b for b in body]
    if payable:
        lines += ["        msgValue = between(msgValue, 0, %s);" % ETH_CAP,
                  "        vm.deal(currentActor, msgValue);"]
    lines += ["        vm.prank(currentActor);",
              "        " + _call_line(instance, fn_name, call_args, payable, "msgValue"),
              "    }"]
    return "\n".join(lines)


def _render_privileged(hname: str, instance: str, fn_name: str, params: list[str], body: list[str], call_args: list[str], payable: bool) -> str:
    sig = params + (["uint256 msgValue"] if payable else [])
    admin_sig = ", ".join(sig) if sig else ""
    admin = ["    function %s(%s) public updateGhosts {" % (hname, admin_sig)]
    admin += ["        " + b for b in body]
    if payable:
        admin += ["        msgValue = between(msgValue, 0, %s);" % ETH_CAP]
    admin += ["        " + _call_line(instance, fn_name, call_args, payable, "msgValue"),
              "    }"]
    atk_sig = ", ".join(["uint256 actorSeed"] + sig)
    atk = ["    function %s_attacker(%s) public updateGhosts {" % (hname, atk_sig),
           "        _useActor(actorSeed);"]
    atk += ["        " + b for b in body]
    if payable:
        atk += ["        msgValue = between(msgValue, 0, %s);" % ETH_CAP,
                "        vm.deal(currentActor, msgValue);"]
    atk += ["        vm.prank(currentActor);",
            "        " + _call_line(instance, fn_name, call_args, payable, "msgValue"),
            "    }"]
    return "\n".join(admin + [""] + atk)


def _render_stub(hname: str, instance: str, fn_name: str) -> str:
    hook = "_build_%s" % fn_name
    return ("    // STUB(tuple): %s.%s takes a struct/nested arg auto-gen cannot synthesize.\n"
            "    // Fill `%s(seed)` in TargetFunctions.sol to build the args and call the target.\n"
            "    function %s(uint256 seed) public updateGhosts {\n"
            "        _useActor(seed);\n"
            "        %s(seed);\n"
            "    }\n"
            "    function %s(uint256 seed) internal virtual {}"
            % (instance, fn_name, hook, hname, hook, hook))


def _preamble() -> str:
    return "\n".join([
        "    // --- auto surface knobs (tune CLAMP_CAP if reverts dominate the campaign) ---",
        "    uint256 internal constant CLAMP_CAP = %s;" % CLAMP_CAP,
        "    uint256 internal constant ETH_CAP = %s;" % ETH_CAP,
        "",
        "    // Multi-actor model (Pattern A): the fuzzer builds multi-user sequences across these.",
        "    address[3] internal _autoActors = [address(0xA11CE), address(0xB0B), address(0xCA201)];",
        "    address internal currentActor;",
        "    address[] internal _addressBook;   // Setup pushes deployed target/token addresses here",
        "",
        "    function _useActor(uint256 seed) internal {",
        "        currentActor = _autoActors[seed % _autoActors.length];",
        "    }",
        "",
        "    // Address args resolve to a known address (actor or deployed instance), never a raw",
        "    // fuzzed value that could never match a live contract (which would revert 100%).",
        "    function _pickAddr(uint256 seed) internal view returns (address) {",
        "        uint256 n = _autoActors.length + _addressBook.length;",
        "        if (n == 0) return currentActor;",
        "        uint256 s = seed % n;",
        "        return s < _autoActors.length ? _autoActors[s] : _addressBook[s - _autoActors.length];",
        "    }",
        "",
        "    function _seedAddressBook(address a) internal { _addressBook.push(a); }",
    ])


def render_auto_file(handlers: list[tuple[str, str, str]]) -> str:
    header = [
        "// SPDX-License-Identifier: MIT",
        "pragma solidity ^0.8.20;",
        "",
        "// AUTO-GENERATED by `fuzzpipe gen-handlers` — DO NOT EDIT (regenerate with --force).",
        "// Complete, ABI-driven fuzzer call surface: one clamped, multi-actor, revert-tolerant",
        "// handler per state-changing entry point of every in-scope deployed target. Coverage is",
        "// decoupled from invariant count. Override any handler_* in TargetFunctions.sol to assert.",
        'import {Properties} from "./Properties.sol";',
        'import {vm} from "@chimera/Hevm.sol";',
        "",
        "abstract contract TargetFunctionsAuto is Properties {",
        _preamble(),
        "",
    ]
    bodies = []
    for _name, src, _status in handlers:
        bodies.append(src)
        bodies.append("")
    return "\n".join(header + bodies + ["}", ""])


def generate_handlers(target: Path, project_type: Optional[str] = None, contract: Optional[str] = None,
                      src: Optional[str] = None, force: bool = False) -> int:
    """Auto-generate complete ABI-driven handler surface. Returns 0 on success."""
    pt = _project_type(target, project_type)
    recon = target / ("contracts/recon" if pt == "hardhat" else "test/recon")
    if not recon.exists():
        print(f"[error] no recon harness at {recon}. Run `fuzzpipe scaffold` first.")
        return 1
    instances = discover_instances(target, pt)
    scoped = scope_contracts(target)
    manual = manual_handler_names(target, pt)
    only = contract
    src_override = src
    _, _, privileged = _scan_solidity_surface(target, pt, src_override)

    report = {}
    handlers_list = []
    to_gen = {}
    for typ, var in instances.items():
        if only and typ != only:
            continue
        if scoped and typ not in scoped:
            continue
        abi = load_abi(target, typ)
        if not abi:
            report[typ] = "SKIP(no-abi: run `fuzzpipe build` first)"
            continue
        to_gen[typ] = (var, abi)
    for name in sorted(scoped):
        if name not in instances:
            report[name] = "SKIP(not-deployed)"

    multi = len(to_gen) > 1
    for typ in sorted(to_gen):
        var, abi = to_gen[typ]
        for fn in mutating_functions(abi):
            is_priv = fn["name"] in privileged
            name, src, status = render_handler(var, fn, multi=multi, privileged=is_priv)
            if name in manual:
                report[name] = "MANUAL-OVERRIDE"
                continue
            handlers_list.append((name, src, status))
            report[name] = status

    if not to_gen:
        print("[warn] no in-scope deployed target found (need a typed instance in Setup.sol whose contract "
             "is listed in scope.txt and has a built ABI). Nothing generated.")
        _write_gen_report(target, report)
        return 1

    content = render_auto_file(handlers_list)
    (recon / "TargetFunctionsAuto.sol").write_text(content)
    _ensure_auto_in_chain(target, pt)
    _write_gen_report(target, report)

    gen = sum(1 for _, _, s in handlers_list if s.startswith("GEN"))
    stub = sum(1 for _, _, s in handlers_list if s.startswith("STUB"))
    ovr = sum(1 for v in report.values() if v == "MANUAL-OVERRIDE")
    print(f"[ok] Generated {len(handlers_list)} handler(s) into {recon / 'TargetFunctionsAuto.sol'} "
          f"({gen} full, {stub} struct-stub, {ovr} manual-override).")
    print(f"[fuzzpipe] Spliced TargetFunctionsAuto into the harness inheritance chain.")
    print("\n[fuzzpipe] gen-handlers report (%s)" % target.name)
    for name in sorted(report):
        status = report[name]
        color = "green" if status.startswith("GEN") else ("yellow" if "MANUAL" in status else "red")
        print(f"    [{status}] {name}")
    if stub:
        print("[warn] %d struct/tuple handler(s) are STUBS — fill their `_build_*` hook in TargetFunctions.sol "
             "or they contribute no coverage." % stub)
    print("[fuzzpipe] Next: `fuzzpipe build` (recompile), then `verify-harness` and `run`.")
    set_stage(target, "3-gen-handlers", generated=len(handlers_list), stubs=stub, overrides=ovr)
    return 0


def _write_gen_report(target: Path, report: dict) -> None:
    sd = state_dir(target)
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "gen-handlers.json").write_text(json.dumps(report, indent=2, sort_keys=True))


def _project_type(target: Path, override: Optional[str] = None) -> Optional[str]:
    if override:
        st = load_state(target)
        st["project_type"] = override
        save_state(target, st)
        return override
    st = load_state(target)
    if st.get("project_type"):
        return st["project_type"]
    pt = _detect_project_type(target)
    if pt:
        st["project_type"] = pt
        save_state(target, st)
    return pt


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


def save_state(target: Path, state: dict) -> None:
    sd = state_dir(target)
    sd.mkdir(parents=True, exist_ok=True)
    import datetime
    state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (sd / "state.json").write_text(json.dumps(state, indent=2))


def set_stage(target: Path, stage: str, **extra: Any) -> None:
    st = load_state(target)
    st["stage"] = stage
    st.setdefault("history", []).append(
        {"stage": stage, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra})
    st.update(extra)
    save_state(target, st)


def discover_instances(target: Path, pt: str) -> dict[str, str]:
    """Map contract type -> Setup variable name by scanning Setup.sol."""
    from fuzzpipe.engines.sharding import _recon_dir
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
    f = target / "scope.txt"
    names = set()
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line.endswith(".sol"):
                names.add(Path(line).stem)
    return names


def manual_handler_names(target: Path, pt: str) -> set[str]:
    from fuzzpipe.engines.sharding import _recon_dir
    tf = _recon_dir(target, pt) / "TargetFunctions.sol"
    if not tf.exists():
        return set()
    import re as _re
    return set(_re.findall(r"function\s+(handler_\w+)\s*\(", tf.read_text(errors="replace")))


def _ensure_auto_in_chain(target: Path, pt: str) -> bool:
    from fuzzpipe.engines.sharding import _recon_dir
    tf = _recon_dir(target, pt) / "TargetFunctions.sol"
    if not tf.exists():
        return False
    import re as _re
    text = tf.read_text(errors="replace")
    if "TargetFunctionsAuto" in text:
        return False
    new = _re.sub(
        r"(abstract\s+contract\s+TargetFunctions\s+is\s+[^{]*?)\bProperties\b",
        r"\1TargetFunctionsAuto", text, count=1)
    if new == text:
        new = _re.sub(r"(abstract\s+contract\s+TargetFunctions\s+is\s+[^{]*?)(\s*\{)",
                      r"\1, TargetFunctionsAuto\2", text, count=1)
    if 'import {TargetFunctionsAuto}' not in new:
        imp = 'import {TargetFunctionsAuto} from "./TargetFunctionsAuto.sol";\n'
        if 'from "./Properties.sol";' in new:
            new = new.replace('from "./Properties.sol";', 'from "./Properties.sol";\n' + imp.rstrip(), 1)
        else:
            new = _re.sub(r"(pragma solidity[^\n]*\n)", r"\1" + imp, new, count=1)
    tf.write_text(new)
    return True


def _scan_solidity_surface(target: Path, pt: str, override: Optional[str] = None) -> tuple[set, set, set]:
    from fuzzpipe.engines.sharding import _recon_dir
    entry_points, state_vars, privileged = set(), set(), set()
    _SKIP_SRC_PARTS = ("/test/", "/tests/", "/recon/", "/lib/", "/mock", "/mocks/", "/script/",
                       "/node_modules/", "/foundry-repro/")
    _PRIV_MODS = ("onlyOwner", "onlyRole", "onlyAdmin", "onlyGovernance", "onlyGovernor",
                  "onlyKeeper", "onlyManager", "onlyGuardian", "restricted", "auth")
    _FUNC_HEAD_RE = _re.compile(r"\bfunction\s+(\w+)\s*\(")
    _VAR_RE = _re.compile(
        r"\b(?:uint\d*|int\d*|address|bool|bytes\d*|string|mapping\s*\([^)]*\))\s+public\s+"
        r"(?:constant\s+|immutable\s+)?(\w+)")
    src_dirs = [Path(target) / "src"] if pt == "foundry" else [Path(target) / "contracts"]
    if override:
        src_dirs = [Path(target) / override]
    for base in src_dirs:
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


import datetime
import re as _re