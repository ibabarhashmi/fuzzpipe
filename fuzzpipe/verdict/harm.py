from __future__ import annotations
from typing import Optional
import re

_ASSERT_CMP = ("assertEq", "assertNotEq", "assertLt", "assertGt", "assertLe", "assertGe",
               "assertApproxEqAbs", "assertApproxEqRel",
               # Chimera/Recon assertion primitives (the skill's own scaffold framework):
               # gt/gte/lt/lte/eq take (a, b, "reason") — the same 2-operand comparison shape.
               "gte", "lte", "gt", "lt", "eq", "neq")
_ASSERT_BOOL = {"assertTrue": "true", "assertFalse": "false", "t": ""}   # Chimera `t(cond, "reason")`
_CMP_OPS = ("==", "!=", "<=", ">=", "<", ">")   # two-char first so they win the split
# A literal that carries NO information about protocol state: numbers, hex, bools, type(x).max.
_LIT_RE = re.compile(
    r"^\s*(?:true|false"
    r"|-?0x[0-9a-fA-F]+"
    r"|-?\d[\d_]*(?:\s*(?:ether|wei|gwei|days|hours|minutes|seconds|weeks))?"
    r"|type\([^)]*\)\.(?:max|min)"
    r"|address\(0\)|address\(0x0+\))\s*$", re.I)


def _strip_comments(src: Optional[str]) -> str:
    """Remove /* */ blocks and // line comments so a marker sitting in a comment can never be
    mistaken for a harm assertion (and so a multi-line assertion is scanned as one blob)."""
    src = re.sub(r"/\*.*?\*/", " ", src or "", flags=re.S)
    out = []
    for line in src.splitlines():
        i = line.find("//")
        out.append(line[:i] if i != -1 else line)
    return "\n".join(out)


def _all_call_args(blob: str, fn: str) -> list[str]:
    """Every balanced-paren argument string for each `fn( ... )` occurrence in `blob` — spanning
    NEWLINES, so a `require(cond,\n  "msg")` split across lines is read as one call. `fn` must be a
    whole word immediately followed by `(`, so `assert` never matches inside `assertEq(`."""
    results, start, pat = [], 0, fn + "("
    while True:
        i = blob.find(pat, start)
        if i == -1:
            break
        if i > 0 and (blob[i - 1].isalnum() or blob[i - 1] == "_"):
            start = i + len(pat)                       # not a word boundary (e.g. `_require(`)
            continue
        pre = blob[:i].rstrip()
        if pre.endswith("function"):                   # a DEFINITION named like an assertion, not a call
            start = i + len(pat)
            continue
        depth, argstart, k, found = 0, i + len(fn) + 1, i + len(fn), None
        while k < len(blob):
            if blob[k] == "(":
                depth += 1
            elif blob[k] == ")":
                depth -= 1
                if depth == 0:
                    found = blob[argstart:k]
                    break
            k += 1
        if found is None:
            break
        results.append(found)
        start = k + 1
    return results


def _split_top(args: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in args or "":
        if ch in "([{":
            depth += 1; cur.append(ch)
        elif ch in ")]}":
            depth -= 1; cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip()); cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _is_literal(tok: str) -> bool:
    return bool(_LIT_RE.match(tok or ""))


def _substantive_cmp(a: str, b: str) -> bool:
    """A comparison carries harm only if the two sides differ AND are not both constants —
    `assertEq(x, x)` and `assertEq(1, 1)` assert nothing about protocol state."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b or a == b:
        return False
    return not (_is_literal(a) and _is_literal(b))


def _split_on_cmp(expr: str) -> tuple[str, str] | None:
    depth = 0
    for k in range(len(expr)):
        if expr[k] in "([{":
            depth += 1
        elif expr[k] in ")]}":
            depth -= 1
        elif depth == 0:
            for op in _CMP_OPS:
                if expr[k:k + len(op)] == op:
                    return expr[:k], expr[k + len(op):]
    return None


def _cond_substantive(cond: str) -> bool:
    """A boolean condition (from require/assert) is substantive if it is a non-trivial
    comparison, or a state-reading expression (a call / member access) — but not a bare
    literal or a constant tautology."""
    cond = (cond or "").strip()
    if not cond or cond.lower() == "true":
        return False
    split = _split_on_cmp(cond)
    if split:
        return _substantive_cmp(*split)
    # a comparison NESTED in parens/negation (e.g. `!(out > 0 && fees == before)`) is still
    # substantive as long as it references at least one identifier (not a constant tautology).
    if any(op in cond for op in _CMP_OPS) and re.search(r"[A-Za-z_]\w*", cond) and not _is_literal(cond):
        return True
    # no comparison operator: a call / member access reads state → substantive; a bare literal isn't
    if _is_literal(cond):
        return False
    return bool(re.search(r"[A-Za-z_]\w*\s*[.(]", cond)) or bool(re.match(r"^[A-Za-z_]\w*$", cond))


def asserts_harm(source: Optional[str]) -> bool:
    """Does this PoC assert a CONSEQUENCE (who loses what), not just that a call was possible?

    Hardened against the false-CONFIRMED vector: a *trivially-true* assertion
    (`assertTrue(true)`, `assertEq(1, 1)`, `assertEq(x, x)`, `require(true)`) does NOT count,
    and an invariant marker sitting in a *comment* does NOT count — the harm must live in a real,
    non-tautological assertion. Scans the whole (comment-stripped) source so multi-line assertions
    are read correctly. Conservative on purpose: no substantive harm assertion ⇒ SUSPECTED.
    """
    blob = _strip_comments(source or "")
    for fn, trivial in _ASSERT_BOOL.items():                     # assertTrue/assertFalse
        for args in _all_call_args(blob, fn):
            first = (_split_top(args) or [""])[0]
            if first.strip().lower() != trivial and _cond_substantive(first):
                return True
    for fn in _ASSERT_CMP:                                       # assertEq/Lt/Gt/...
        for args in _all_call_args(blob, fn):
            parts = _split_top(args)
            if len(parts) >= 2 and _substantive_cmp(parts[0], parts[1]):
                return True
    for fn in ("require", "assert"):                             # require(cond,...) / assert(cond)
        for args in _all_call_args(blob, fn):
            if _cond_substantive((_split_top(args) or [""])[0]):
                return True
    return False