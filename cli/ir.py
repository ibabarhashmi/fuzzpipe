"""
ir.py — the typed Invariant IR: the machine contract between invariant discovery,
the harness generator, and the verdict gate.

The human 9-procedure table (`invariants.md`) stays for auditors; this typed artifact
(`.fuzzpipe/invariants.json`) is what the tooling consumes. Cross-field rules are checked
with stdlib only — no external schema validator, no install.
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


@dataclass
class Invariant:
    id: str                                     # ^INV-[A-Z0-9-]+$
    statement: str                              # plain-English, falsifiable
    category: str                               # CATEGORY
    shape: str                                  # SHAPE
    scope: str                                  # SCOPE
    predicate: dict = field(default_factory=dict)   # {"expr": "assets >= owed", "helpers": [...]}
    priority: str = "P1"                        # P0..P3
    targets: list = field(default_factory=list)     # ["Vault.deposit", ...]
    tolerance: str = ""                         # e.g. "±1 wei/user"
    derived_via: str = ""                       # which of the 9 procedures
    source: str = "discovered"                  # seed|discovered|library|threat-model
    severity_if_broken: str = "high"            # SEVERITY
    tier_hint: int = 1                          # 0..3
    status: str = "candidate"                   # STATUS

    @staticmethod
    def from_dict(d):
        allowed = {f for f in Invariant.__dataclass_fields__}       # tolerate extra keys
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


# -------------------------------------------------------------- persistence (.fuzzpipe/invariants.json)

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
