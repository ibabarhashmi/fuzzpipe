"""
handlers.py — ABI-driven auto-generation of a COMPLETE Chimera handler surface.

Root cause it fixes: the scaffold writes an EMPTY `TargetFunctions.sol`, so the fuzzer's call
surface = only the handlers the skill hand-wrote per invariant. Every state-changing entry point
without a handler is never called -> 0 coverage (e.g. the Upside example wired 4 of 14 mutating
functions of `UpsideProtocol`). This module enumerates EVERY external/public non-view function of
every in-scope, *deployed* target contract and emits one clamped, multi-actor, revert-tolerant
`handler_<fn>` — decoupling coverage from invariant count. The skill then only tunes clamps/Setup
and adds invariant assertions; it no longer authors the call surface.

MECHANICAL ONLY (stdlib), mirrors render.py. Reuses `render.parse_types` for tuple splitting.
The generated Solidity leans on the Chimera framework the scaffold already vendors:
  * `between(uint256|int256, lo, hi)` from `@chimera/Asserts.sol` (clamps + returns).
  * `vm` (IHevm at the cheatcode address) from `@chimera/Hevm.sol` — Medusa supports prank/deal/warp.
Both are already in scope inside a `is Properties` contract; we import `vm` explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

import render  # sibling module; reuse parse_types for nested-type splitting

# Wide + tunable defaults (operator choice): reach overflow/whale edges; the skill narrows the
# named constant once if reverts dominate. Emitted as Solidity constants at the top of the file.
CLAMP_CAP = "type(uint128).max"
MAX_ARR = "4"
ETH_CAP = "1_000 ether"

# Owner-family functions OpenZeppelin injects whose onlyOwner modifier lives in lib/ (so the source
# scan can miss it). Treat as privileged so they get the admin/attacker pair.
_OWNER_FNS = ("transferOwnership", "renounceOwnership")


# --------------------------------------------------------------------------- ABI loading


def _decode_abi(raw):
    """crytic combined_solc stores the ABI as a JSON *string*; forge out/ stores it as a list.
    Normalize to a python list. Never raises."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


def load_abi(target, contract):
    """Return the ABI (list of entries) for `contract`, or [] if unavailable.

    Source precedence, first hit wins:
      1. Foundry `out/<contract>.sol/<contract>.json` -> "abi" (fresh after `forge build`).
      2. `crytic-export/combined_solc.json` -> contracts["<path>:<contract>"]["abi"]
         (cross-platform; the Medusa path already produces it).
    The regex fallback (names only, no types) is handled by the caller, not here.
    """
    target = Path(target)
    # 1. Foundry artifact
    out = target / "out" / (contract + ".sol") / (contract + ".json")
    if out.exists():
        try:
            j = json.loads(out.read_text())
            abi = _decode_abi(j.get("abi"))
            if abi:
                return abi
        except Exception:
            pass
    # 2. crytic-export combined_solc
    combined = target / "crytic-export" / "combined_solc.json"
    if combined.exists():
        try:
            j = json.loads(combined.read_text())
            contracts = j.get("contracts", {})
            for key, val in contracts.items():
                # key is "<path>:<ContractName>"
                if key.rsplit(":", 1)[-1] == contract:
                    abi = _decode_abi(val.get("abi"))
                    if abi:
                        return abi
        except Exception:
            pass
    return []


def mutating_functions(abi):
    """Yield the state-changing external/public function entries (skip view/pure, ctor, events)."""
    seen = set()
    for e in abi or []:
        if e.get("type") != "function":
            continue
        if e.get("stateMutability") in ("view", "pure"):
            continue
        name = e.get("name")
        if not name:
            continue
        # ABI overloads collapse to one handler on the first signature (rare in practice); a second
        # same-named entry is skipped to avoid a duplicate handler definition.
        if name in seen:
            continue
        seen.add(name)
        yield e


# --------------------------------------------------------------------- per-type argument rendering


def _is_auto_renderable(t):
    """A leaf type we can synthesize a fuzzer value for. Tuples/structs and nested/array-of-array
    and array-of-tuple are NOT (return False) -> the caller emits a delegating stub instead."""
    t = (t or "").strip()
    if t.startswith("("):
        return False                     # tuple / struct
    if t.endswith("[]"):
        base = t[:-2]
        return _is_leaf(base)            # only single-depth arrays of a leaf
    return _is_leaf(t)


def _is_leaf(t):
    t = (t or "").strip()
    if t in ("bool", "address", "string", "bytes"):
        return True
    if t.startswith(("uint", "int")):
        return True
    if t.startswith("bytes"):            # fixed bytesN
        return True
    return False


def _int_bounds(t):
    """(lo, hi) Solidity expressions for a uint*/int* clamp, plus whether a cast is needed."""
    t = t.strip()
    if t in ("uint", "uint256"):
        return ("0", CLAMP_CAP, None)
    if t in ("int", "int256"):
        return ("-int256(%s)" % CLAMP_CAP, "int256(%s)" % CLAMP_CAP, None)
    if t.startswith("uint"):             # narrow unsigned: clamp in uint256 then cast
        return ("0", "uint256(type(%s).max)" % t, t)
    if t.startswith("int"):              # narrow signed
        return ("-int256(uint256(type(%s).max) / 2)" % t.replace("int", "uint"),
                "int256(uint256(type(%s).max) / 2)" % t.replace("int", "uint"), t)
    return ("0", CLAMP_CAP, None)


def handler_arg(idx, abi_type):
    """Render one ABI input as (params, body, call_arg).

    params   : list of Solidity parameter declarations to add to the handler signature.
    body     : list of statement lines to emit before the call (clamps / resolves / builds).
    call_arg : the expression passed at the call site.

    Returns None for a type we cannot synthesize (tuple/struct/nested) — the caller then emits a
    delegating stub so the selector still exists but its construction is left to the skill.
    """
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

    if t.startswith("bytes"):                                   # fixed bytesN — raw fuzzer value
        return (["%s %s" % (t, p)], [], p)

    if t.startswith(("uint", "int")):
        lo, hi, cast = _int_bounds(t)
        decl = "%s %s" % (t, p)
        if cast is None:
            return ([decl], ["%s = between(%s, %s, %s);" % (p, p, lo, hi)], p)
        base = "int256" if t.startswith("int") else "uint256"
        return ([decl],
                ["%s = %s(between(%s(%s), %s, %s));" % (p, cast, base, p, lo, hi)], p)

    if t.endswith("[]"):                                        # single-depth array of a leaf
        base = t[:-2]
        var = "%sArr" % p
        body = ["uint256 %sLen = between(%sN, 0, %s);" % (p, p, MAX_ARR),
                "%s[] memory %s = new %s[](%sLen);" % (base, var, base, p),
                "for (uint256 i; i < %sLen; ++i) {" % p,
                "    %s" % _array_elem_fill(base, var, p),
                "}"]
        return (["uint256 %sN" % p, "uint256 %sSeed" % p], body, var)

    return None


def _array_elem_fill(base, var, p):
    """One statement filling element i of a bounded array whose base is a leaf type. Elements are
    derived deterministically from a per-index seed so the fuzzer still varies them across runs."""
    seed = "%sSeed + i" % p
    if base == "address":
        return "%s[i] = _pickAddr(%s);" % (var, seed)
    if base == "bool":
        return "%s[i] = ((%s) %% 2 == 0);" % (var, seed)
    if base in ("uint", "uint256"):
        return "%s[i] = uint256(keccak256(abi.encode(%s))) %% (%s);" % (var, seed, CLAMP_CAP)
    if base.startswith("uint"):                             # narrow unsigned
        return "%s[i] = %s(uint256(keccak256(abi.encode(%s))) %% (uint256(type(%s).max) + 1));" % (
            var, base, seed, base)
    if base.startswith("int"):                              # signed: keep it simple/bounded
        return "%s[i] = %s(int256(uint256(keccak256(abi.encode(%s))) %% (%s)));" % (
            var, base, seed, CLAMP_CAP)
    # bytes / string element: cheap deterministic value derived from the seed
    return "%s[i] = abi.encodePacked(%s);" % (var, seed)


# --------------------------------------------------------------------------- handler rendering


def _handler_name(instance, fn_name, multi):
    return "handler_%s_%s" % (instance, fn_name) if multi else "handler_%s" % fn_name


def render_handler(instance, fn, multi=False, privileged=False):
    """Emit the Solidity for one handler. Returns (name, source, status) where status is one of
    GEN / STUB(tuple) / STUB(privileged) — reported to the operator via .fuzzpipe/gen-handlers.json."""
    fn_name = fn["name"]
    inputs = fn.get("inputs", []) or []
    payable = fn.get("stateMutability") == "payable"
    hname = _handler_name(instance, fn_name, multi)
    is_priv = privileged or fn_name in _OWNER_FNS

    # Resolve each argument; a single un-renderable arg forces a delegating stub for the whole call.
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


def _call_line(instance, fn_name, call_args, payable, value_expr=None):
    val = "{value: %s}" % value_expr if (payable and value_expr) else ""
    return "try %s.%s%s(%s) {} catch {}" % (instance, fn_name, val, ", ".join(call_args))


def _render_plain(hname, instance, fn_name, params, body, call_args, payable):
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


def _render_privileged(hname, instance, fn_name, params, body, call_args, payable):
    """Pattern D: an admin variant (called as the deployer/owner == address(this), no prank) that
    exercises the happy path, and an attacker variant (random actor) that must be rejected. The
    attacker variant is a neutral try/catch by default; the skill promotes the catch-less success
    to `t(false, ...)` where an AUTHORIZATION invariant is approved."""
    sig = params + (["uint256 msgValue"] if payable else [])
    admin_sig = ", ".join(sig) if sig else ""
    # admin: no prank — Setup deploys as address(this), which is the owner in these harnesses.
    admin = ["    function %s(%s) public updateGhosts {" % (hname, admin_sig)]
    admin += ["        " + b for b in body]
    if payable:
        admin += ["        msgValue = between(msgValue, 0, %s);" % ETH_CAP]
    admin += ["        " + _call_line(instance, fn_name, call_args, payable, "msgValue"),
              "    }"]
    # attacker: pranked as a random actor; success is suspicious (skill upgrades to t(false,...)).
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


def _render_stub(hname, instance, fn_name):
    """A selector-preserving stub for a function with a struct/tuple/nested arg auto-gen can't
    synthesize. The fuzzer still sees `hname` (so coverage-audit finds a handler), but construction
    is delegated to a virtual the skill fills in TargetFunctions.sol."""
    hook = "_build_%s" % fn_name
    return ("    // STUB(tuple): %s.%s takes a struct/nested arg auto-gen cannot synthesize.\n"
            "    // Fill `%s(seed)` in TargetFunctions.sol to build the args and call the target.\n"
            "    function %s(uint256 seed) public updateGhosts {\n"
            "        _useActor(seed);\n"
            "        %s(seed);\n"
            "    }\n"
            "    function %s(uint256 seed) internal virtual {}"
            % (instance, fn_name, hook, hname, hook, hook))


# --------------------------------------------------------------------------- file rendering


def _preamble():
    """Shared constants + actor/address helpers, emitted once inside the Auto contract. Setup should
    fund `_autoActors` and push key target addresses into `_addressBook` (via `_seedAddressBook`)."""
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


def render_auto_file(handlers):
    """Assemble the full TargetFunctionsAuto.sol from a list of (name, source, status) tuples."""
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
