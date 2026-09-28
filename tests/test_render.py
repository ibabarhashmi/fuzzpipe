"""Q2/Q3 (type-aware rendering) at the unit level, plus a guard proving the v0.2 crash class."""
import unittest

import _util  # noqa: F401
import render


class TestParseTypes(unittest.TestCase):
    def test_scalars(self):
        self.assertEqual(render.parse_types("h(bool,uint256)"), ["bool", "uint256"])

    def test_array(self):
        self.assertEqual(render.parse_types("batch(uint256[])"), ["uint256[]"])

    def test_nested_tuple_respects_commas(self):
        self.assertEqual(render.parse_types("f((uint256,address),bytes)"),
                         ["(uint256,address)", "bytes"])

    def test_no_args(self):
        self.assertEqual(render.parse_types("ping()"), [])


class TestRenderCall(unittest.TestCase):
    def test_bool_and_uint_the_v02_crash_input(self):
        # v0.2 did `", ".join([True, 42])` here -> TypeError. v2.1 renders valid Solidity.
        out = render.render_call(1, "h", [True, 42], ["bool", "uint256"])
        self.assertEqual(out, ["this.h(true, 42);"])

    def test_dynamic_array_prelude(self):
        out = render.render_call(4, "batch", [[1, 2, 3]], ["uint256[]"])
        self.assertIn("uint256[] memory _a4_0 = new uint256[](3);", out)
        self.assertIn("_a4_0[2] = 3;", out)
        self.assertTrue(out[-1].startswith("this.batch(_a4_0);"))

    def test_address_and_bytes_and_string(self):
        self.assertEqual(render.render_call(0, "t", ["0xabc"], ["address"]),
                         ["this.t(address(0xabc));"])
        self.assertEqual(render.render_call(0, "t", ["0xdead"], ["bytes32"]),
                         ["this.t(bytes32(0xdead));"])
        self.assertEqual(render.render_call(0, "t", ["hi"], ["string"]),
                         ['this.t("hi");'])

    def test_never_raises_on_mismatched_arity(self):
        # missing types must degrade gracefully (compile-check backstops), never raise
        out = render.render_call(0, "m", [True, 7], [])
        self.assertTrue(out[-1].startswith("this.m("))

    def test_v02_join_would_have_crashed(self):
        # Documents the exact defect v2.1 fixes: str.join on non-strings raises TypeError.
        with self.assertRaises(TypeError):
            ", ".join([True, 42])


class TestAssertsHarm(unittest.TestCase):
    def test_bare_call_is_not_harm(self):
        self.assertFalse(render.asserts_harm("this.deposit(1);\nthis.withdraw(2);"))

    def test_invariant_assertion_is_harm(self):
        self.assertTrue(render.asserts_harm('require(v.solvent(), "INV-SOLVENCY broken");'))

    def test_comparison_require_is_harm(self):
        self.assertTrue(render.asserts_harm("require(bal < before, 'lost funds');"))

    # ---- adversarial: the false-CONFIRMED vectors (v2.2 hardening) ----

    def test_trivially_true_assert_is_not_harm(self):
        self.assertFalse(render.asserts_harm("assertTrue(true);"))
        self.assertFalse(render.asserts_harm("assertEq(1, 1);"))
        self.assertFalse(render.asserts_harm("assertEq(x, x);"))
        self.assertFalse(render.asserts_harm("require(true);"))
        self.assertFalse(render.asserts_harm("require(1 < 2);"))

    def test_marker_in_comment_is_not_harm(self):
        self.assertFalse(render.asserts_harm("// INV-SOLVENCY broken here\nthis.f();"))
        self.assertFalse(render.asserts_harm("/* INV-X harm */\nthis.f();"))

    def test_multiline_assertion_is_harm(self):
        # the exact shape the reproducer harness emits (require split across lines)
        self.assertTrue(render.asserts_harm(
            'require(v.solvent(),\n    "INV-SOLVENCY broken: assets < owed");'))
        self.assertTrue(render.asserts_harm(
            'require(out <= fair,\n    "INV-ROUNDTRIP broken");'))

    def test_substantive_assert_is_harm(self):
        self.assertTrue(render.asserts_harm("assertLt(vault.totalAssets(), owed);"))
        self.assertTrue(render.asserts_harm("assertTrue(vault.solvent());"))

    def test_nested_negated_condition_is_harm(self):
        # the shape a lowered PoC uses: require(!(<comparison over state>), "INV-X broken")
        self.assertTrue(render.asserts_harm(
            'require(!(out > 0 && feesAfter == feesBefore),\n  "INV-FEE-ALWAYS broken");'))

    def test_nested_tautology_is_not_harm(self):
        self.assertFalse(render.asserts_harm("require(!(1 < 2));"))

    def test_chimera_asserts_are_harm(self):
        # the skill's own scaffold framework (Chimera/Recon) uses gt/gte/lt/lte/eq/t, not assertGt
        self.assertTrue(render.asserts_harm(
            'gt(protocol.claimableProtocolFees(), feesBefore, "INV-FEE-ALWAYS broken");'))
        self.assertTrue(render.asserts_harm('eq(vault.totalAssets(), owed, "INV-SOLVENCY");'))
        self.assertTrue(render.asserts_harm('t(vault.solvent(), "INV-SOLVENCY");'))

    def test_chimera_trivial_and_collisions_are_not_harm(self):
        self.assertFalse(render.asserts_harm('eq(1, 1, "x");'))          # constant tautology
        self.assertFalse(render.asserts_harm("this.handler_gt(5);"))     # handler_gt is not an assert


if __name__ == "__main__":
    unittest.main()
