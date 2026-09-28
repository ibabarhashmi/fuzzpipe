from __future__ import annotations
import re
from enum import Enum
from pydantic import BaseModel, Field
from typing import Annotated

ID_RE = re.compile(r"^INV-[A-Z0-9-]+$")
class Category(str, Enum):
    FUNCTION="function"; VALID_STATE="valid-state"; STATEFUL_SEQUENCE="stateful-sequence"; SOLVENCY="solvency"; ANTI_PROPERTY="anti-property"
class Shape(str, Enum):
    SAFETY="SAFETY"; LIVENESS="LIVENESS"; CORRECTNESS="CORRECTNESS"; AUTHORIZATION="AUTHORIZATION"
class Scope(str, Enum):
    GUARD="guard"; GLOBAL="global"; CROSS_CONTRACT="cross_contract"; ECONOMIC="economic"
class Severity(str, Enum):
    CRITICAL="critical"; HIGH="high"; MEDIUM="medium"; LOW="low"; INFORMATIONAL="informational"
class Status(str, Enum):
    CANDIDATE="candidate"; APPROVED="approved"; CONFIRMED="CONFIRMED"; SUSPECTED="SUSPECTED"; NO_CE_IN_BUDGET="NO-CE-IN-BUDGET"; PROVEN_IN_BOUND_K="PROVEN-IN-BOUND-K"; UNTESTED="UNTESTED"
class Predicate(BaseModel):
    expr: str = ""
    helpers: list[str] = Field(default_factory=list)
class Invariant(BaseModel):
    id: str
    statement: str
    category: Category
    shape: Shape
    scope: Scope
    predicate: Predicate = Field(default_factory=Predicate)
    priority: str = "P1"
    targets: list[str] = Field(default_factory=list)
    tolerance: str = ""
    derived_via: str = ""
    source: str = "discovered"
    severity_if_broken: Severity = Severity.HIGH
    tier_hint: int = 1
    status: Status = Status.CANDIDATE
    @classmethod
    def from_dict(cls, d: dict) -> "Invariant":
        allowed = set(cls.model_fields)
        return cls(**{k: v for k, v in d.items() if k in allowed})

def validate(invs: list[Invariant]) -> list[str]:
    errs: list[str] = []
    seen: set[str] = set()
    for i in invs:
        if not ID_RE.match(i.id or ""):
            errs.append(f"{i.id}: bad id (want ^INV-[A-Z0-9-]+$)")
        if i.id in seen:
            errs.append(f"duplicate id: {i.id}")
        seen.add(i.id)
        if not isinstance(i.tier_hint, int) or not (0 <= i.tier_hint <= 3):
            errs.append(f"{i.id}: tier_hint must be 0..3")
        if i.scope == Scope.ECONOMIC and isinstance(i.tier_hint, int) and i.tier_hint < 1:
            errs.append(f"{i.id}: economic scope requires tier_hint >= 1")
        if isinstance(i.tier_hint, int) and i.tier_hint >= 2 and not (
            i.shape in {Shape.SAFETY, Shape.CORRECTNESS}
            and i.severity_if_broken == Severity.CRITICAL
            and i.scope != Scope.ECONOMIC):
            errs.append(f"{i.id}: tier_hint >= 2 requires critical bounded SAFETY/CORRECTNESS (non-economic)")
    return errs

def can_escalate_to_symbolic(inv: Invariant) -> bool:
    return (inv.tier_hint >= 2 and inv.shape in {Shape.SAFETY, Shape.CORRECTNESS}
            and inv.severity_if_broken == Severity.CRITICAL and inv.scope != Scope.ECONOMIC)