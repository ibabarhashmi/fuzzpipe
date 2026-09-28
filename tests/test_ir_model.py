# tests/test_ir_model.py
from fuzzpipe.ir.model import Invariant, validate
def test_bad_id_rejected():
    inv = Invariant(id="bad lower", statement="x", category="function", shape="SAFETY", scope="global")
    errs = validate([inv])
    assert any("bad id" in e for e in errs)
def test_tier2_requires_critical_safety():
    inv = Invariant(id="INV-X", statement="x", category="function", shape="LIVENESS", scope="global", tier_hint=2, severity_if_broken="high")
    errs = validate([inv])
    assert any("tier_hint >= 2" in e for e in errs)
def test_economic_requires_tier1():
    inv = Invariant(id="INV-E", statement="x", category="solvency", shape="SAFETY", scope="economic", tier_hint=0, severity_if_broken="critical")
    errs = validate([inv])
    assert any("economic" in e for e in errs)