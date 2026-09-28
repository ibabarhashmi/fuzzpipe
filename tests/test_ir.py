"""Typed Invariant IR cross-field validation rules."""
import unittest

import _util  # noqa: F401
import ir


def mk(**kw):
    base = dict(id="INV-SOLVENCY", statement="assets >= owed", category="solvency",
                shape="SAFETY", scope="global", severity_if_broken="high", tier_hint=1,
                status="candidate")
    base.update(kw)
    return ir.Invariant(**base)


class TestIRValidate(unittest.TestCase):
    def test_valid_set_passes(self):
        self.assertEqual(ir.validate([mk(), mk(id="INV-SUPPLY", category="valid-state")]), [])

    def test_bad_id(self):
        self.assertTrue(any("bad id" in e for e in ir.validate([mk(id="solvency")])))

    def test_duplicate_id(self):
        self.assertTrue(any("duplicate" in e for e in ir.validate([mk(), mk()])))

    def test_economic_requires_tier_ge_1(self):
        errs = ir.validate([mk(id="INV-FEE", scope="economic", tier_hint=0)])
        self.assertTrue(any("economic" in e for e in errs))

    def test_tier2_requires_critical_bounded_safety(self):
        # tier_hint>=2 but only high severity -> rejected
        errs = ir.validate([mk(id="INV-X", tier_hint=2, severity_if_broken="high")])
        self.assertTrue(any("tier_hint >= 2" in e for e in errs))
        # critical bounded SAFETY non-economic -> allowed
        self.assertEqual(
            ir.validate([mk(id="INV-Y", tier_hint=2, shape="SAFETY",
                            severity_if_broken="critical", scope="global")]), [])

    def test_bad_enum(self):
        self.assertTrue(any("bad shape" in e for e in ir.validate([mk(shape="LIVELINESS")])))

    def test_can_escalate_to_symbolic(self):
        self.assertTrue(ir.can_escalate_to_symbolic(
            mk(tier_hint=2, shape="CORRECTNESS", severity_if_broken="critical", scope="global")))
        self.assertFalse(ir.can_escalate_to_symbolic(mk(tier_hint=1)))


if __name__ == "__main__":
    unittest.main()
