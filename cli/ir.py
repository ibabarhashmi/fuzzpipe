"""Legacy Invariant IR shim (tolerant dataclass API).

Preserves the original cli/ir.py contract: a plain dataclass that accepts
any string for enum fields, with validate() reporting bad values as error
strings instead of raising. New code should use fuzzpipe.ir.model
(pydantic) directly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict

CATEGORY = {"function", "valid-state", "stateful-sequence", "solvency", "anti-property"}
SHAPE = {"SAFETY", "LIVENESS", "CORRECTNESS", "AUTHORIZATION"}
SCOPE = {"guard", "global", "cross_contract", "economic"}
SEVERITY = {"critical", "high", "medium", "low", "informational"}
STATUS = {"candidate", "approved", "CONFIRMED", "SUSPECTED",
          "NO-CE-IN-BUDGET", "PROVEN-IN-BOUND-K", "UNTESTED"}
ID_RE = re.compile(r"^INV-[A-Z0-9-]+$")

__all__ = [
    "CATEGORY", "SHAPE", "SCOPE", "SEVERITY", "STATUS", "ID_RE",
    "Invariant", "validate", "can_escalate_to_symbolic", "load", "dump", "asdict",
]


@dataclass
class Invariant:
    id: str
    statement: str
    category: str
    shape: str
    scope: str
    predicate: dict = field(default_factory=dict)
    priority: str = "P1"
    targets: list = field(default_factory=list)
    tolerance: str = ""
    derived_via: str = ""
    source: str = "discovered"
    severity_if_broken: str = "high"
    tier_hint: int = 1
    status: str = "candidate"

    @staticmethod
    def from_dict(d):
        allowed = {f for f in Invariant.__dataclass_fields__}
        return Invariant(**{k: v for k, v in d.items() if k in allowed})


def validate(invs):
    """Return a list of human-readable error strings (empty == valid)."""
    errs, seen = [], set()
    for i in invs:
        if not ID_RE.match(i.id or ""):
            errs.append("%s: bad id (want ^INV-[A-Z0-9-]+$)" % i.id)
        if i.id in seen:
            errs.append("duplicate id: %s" % i.id)
        seen.add(i.id)
        for fld, allowed in (("category", CATEGORY), ("shape", SHAPE), ("scope", SCOPE),
                             ("severity_if_broken", SEVERITY), ("status", STATUS)):
            if getattr(i, fld) not in allowed:
                errs.append("%s: bad %s=%s" % (i.id, fld, getattr(i, fld)))
        if not (isinstance(i.tier_hint, int) and 0 <= i.tier_hint <= 3):
            errs.append("%s: tier_hint must be 0..3" % i.id)
        if i.scope == "economic" and isinstance(i.tier_hint, int) and i.tier_hint < 1:
            errs.append("%s: economic scope requires tier_hint >= 1" % i.id)
        if isinstance(i.tier_hint, int) and i.tier_hint >= 2 and not (
                i.shape in {"SAFETY", "CORRECTNESS"}
                and i.severity_if_broken == "critical"
                and i.scope != "economic"):
            errs.append("%s: tier_hint >= 2 requires critical bounded SAFETY/CORRECTNESS "
                        "(non-economic)" % i.id)
    return errs


def can_escalate_to_symbolic(inv):
    """Tier-2 (symbolic) eligibility — the same rule the ladder enforces."""
    return (inv.tier_hint >= 2 and inv.shape in {"SAFETY", "CORRECTNESS"}
            and inv.severity_if_broken == "critical" and inv.scope != "economic")


def load(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("invariants", [])
    return [Invariant.from_dict(d) for d in data]


def dump(path, invs):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"invariants": [asdict(i) for i in invs]}, indent=2))
