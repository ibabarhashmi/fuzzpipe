from __future__ import annotations
from typing import Optional
import json

from fuzzpipe.verdict.reproducer import parse_types


def _first(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _extract_step(entry, warnings):
    if not isinstance(entry, dict):
        warnings.append("skipped a non-object sequence entry")
        return None
    call = entry.get("call", entry)
    abiv = call.get("dataAbiValues") if isinstance(call, dict) else None
    abiv = abiv if isinstance(abiv, dict) else {}

    sig = _first(abiv, "methodSignature") or _first(call, "methodSignature", "method", "methodName", "name")
    values = _first(abiv, "inputValues", default=None)
    if values is None:
        values = _first(call, "inputValues", "arguments", "args", default=[])
    if not isinstance(values, list):
        values = [values]

    if not sig:
        warnings.append("entry has no method signature/name — skipped (schema drift?)")
        return None

    method = sig.split("(")[0]
    types = parse_types(sig)
    if "(" in sig and len(types) != len(values):
        warnings.append(
            "arity mismatch for %s: %d type(s) vs %d value(s) — rendering best-effort"
            % (sig, len(types), len(values)))

    sender = _first(call, "from", "sender", "caller", default="0x0") if isinstance(call, dict) else "0x0"
    return {
        "method": method,
        "sig": sig,
        "types": types,
        "values": values,
        "sender": sender,
        "block_delay": entry.get("blockNumberDelay", 0) or 0,
        "time_delay": entry.get("blockTimestampDelay", 0) or 0,
    }


def parse_file(path):
    warnings = []
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        return [], ["could not read %s: %s" % (path.name, e)]

    if isinstance(data, dict):
        data = _first(data, "callSequence", "sequence", "calls", default=[])
    if not isinstance(data, list):
        return [], ["%s: unrecognized top-level shape — skipped" % path.name]

    seq = []
    for entry in data:
        step = _extract_step(entry, warnings)
        if step:
            seq.append(step)
    return seq, warnings


def failing_sequences(results_dir):
    sequences, warnings = [], []
    if not results_dir.exists():
        return sequences, warnings
    for f in sorted(results_dir.glob("*.json")):
        seq, warns = parse_file(f)
        warnings += ["%s: %s" % (f.name, w) for w in warns]
        if seq:
            sequences.append((f.name, seq))
    return sequences, warnings