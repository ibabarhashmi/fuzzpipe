"""R7: the verdict gate is the trust core — a break is CONFIRMED only if its PoC compiles,
re-executes the SPECIFIC break, and asserts harm. The adversarial case that matters is #3: a PoC
that reverts for an UNRELATED reason must be SUSPECTED, not CONFIRMED. 'any revert == reproduction'
(the defect this avoids) would wrongly confirm it.

Runs against a self-contained Foundry fixture (no forge-std/chimera) so it compiles offline."""
import shutil
import unittest

import _util
import verdict


@unittest.skipUnless(_util.have("forge"), "forge required to re-execute the PoC")
class TestVerdictGate(unittest.TestCase):
    def setUp(self):
        self.proj = _util.copy_fixture("verdict_project")
        self.src = (self.proj / "test" / "PoC.t.sol").read_text()

    def tearDown(self):
        shutil.rmtree(self.proj, ignore_errors=True)

    def test_real_break_is_confirmed(self):
        v, reason, _ = verdict.lower_and_verify(
            self.proj, self.src, "test_repro_INV_SOLVENCY", "INV-SOLVENCY")
        self.assertEqual(v, "CONFIRMED", reason)

    def test_passing_poc_is_suspected(self):
        v, reason, _ = verdict.lower_and_verify(
            self.proj, self.src, "test_holds_INV_SOLVENCY", "INV-SOLVENCY")
        self.assertEqual(v, "SUSPECTED")
        self.assertIn("did not reproduce", reason)

    def test_unrelated_revert_is_suspected_not_confirmed(self):
        # THE R7 discriminator: the test fails, but for an unrelated reason (no invariant marker
        # in the revert). A gate keyed on exit code / 'any revert' would confirm this. Ours must not.
        v, reason, out = verdict.lower_and_verify(
            self.proj, self.src, "test_unrelated_INV_SOLVENCY", "INV-SOLVENCY")
        self.assertEqual(v, "SUSPECTED",
                         "an unrelated revert was mistaken for reproduction (R7 regression)\n" + out[-2000:])
        self.assertIn("did not reproduce", reason)

    def test_reproduces_specific_break_keys_on_marker_not_exit(self):
        # unit-level guard on the discriminator
        self.assertTrue(verdict.reproduces_specific_break(
            "[FAIL: INV-SOLVENCY broken: assets < owed] test_repro_INV_SOLVENCY()", "INV-SOLVENCY"))
        self.assertFalse(verdict.reproduces_specific_break(
            "[FAIL: some other unrelated failure] test_unrelated_INV_SOLVENCY()", "INV-SOLVENCY"))
        self.assertFalse(verdict.reproduces_specific_break("[PASS] test()", "INV-SOLVENCY"))


if __name__ == "__main__":
    unittest.main()
