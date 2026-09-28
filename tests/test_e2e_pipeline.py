"""
test_e2e_pipeline.py — the whole pipeline, run as a user, on the golden fixture (forge-only).

Chains init -> ir put -> ir validate -> ir coverage-audit -> run(foundry) -> verify, exactly as the
example README documents, and asserts the regression anchor from expected-findings.md:
  * every seeded bug is CONFIRMED,
  * both control cases stay SUSPECTED (no false CONFIRMED),
  * the completeness gate PASSES on the shipped IR,
  * state.json advances through the stages.

Forge-gated: self-skips (does not fail) when forge is absent, but CI installs forge so it runs there.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import EXAMPLES, have, run_cli

SEEDED = ["INV-SOLVENCY", "INV-SHARE-INFLATION", "INV-ROUNDTRIP", "INV-AUTH-FEE"]


@unittest.skipUnless(have("forge"), "forge not installed")
@unittest.skipUnless((EXAMPLES / "vulnerable-vault" / "src").is_dir(),
                     "examples/vulnerable-vault fixture not present")
class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_e2e_"))
        shutil.copytree(EXAMPLES / "vulnerable-vault", cls.dir, dirs_exist_ok=True)
        cls.poc = "test/recon/CryticToFoundry.sol"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _cli(self, *args):
        return run_cli(list(args) + ["--target", str(self.dir)])

    def test_01_init_and_ir(self):
        self.assertEqual(self._cli("init").returncode, 0)
        r = self._cli("ir", "put", "--file", str(self.dir / "ir.json"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self._cli("ir", "validate").returncode, 0)

    def test_02_completeness_gate_passes(self):
        self._cli("init")
        self._cli("ir", "put", "--file", str(self.dir / "ir.json"))
        r = self._cli("ir", "coverage-audit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASSED", r.stdout)

    def test_03_run_foundry_surfaces_break(self):
        r = self._cli("run", "--engine", "foundry")
        # a failing forge test is a candidate break -> the run reports it (rc 0, status break_or_error)
        self.assertIn("break", (r.stdout + r.stderr).lower())

    def test_04_every_seeded_bug_confirmed(self):
        for inv in SEEDED:
            r = self._cli("verify", "--ce", inv, "--poc", self.poc,
                          "--test", "test_repro_" + inv.replace("-", "_"), "--marker", inv)
            self.assertEqual(r.returncode, 0, "%s not CONFIRMED: %s" % (inv, r.stdout + r.stderr))
            self.assertIn("CONFIRMED", r.stdout + r.stderr)

    def test_05_controls_stay_suspected(self):
        # invariant holds -> did not reproduce
        r = self._cli("verify", "--ce", "INV-SOLVENCY", "--poc", self.poc,
                      "--test", "test_holds_INV_SOLVENCY", "--marker", "INV-SOLVENCY")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SUSPECTED", r.stdout + r.stderr)
        # unrelated revert -> must NOT be mistaken for a reproduction (R7)
        r = self._cli("verify", "--ce", "INV-SOLVENCY", "--poc", self.poc,
                      "--test", "test_unrelated_revert", "--marker", "INV-SOLVENCY")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SUSPECTED", r.stdout + r.stderr)

    def test_06_spoofed_harm_stays_suspected(self):
        # a PoC whose only assertion is trivially true must NOT confirm even though it 'reverts'
        spoof = self.dir / "test" / "Spoof.t.sol"
        spoof.write_text(
            "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n"
            "contract Spoof {\n"
            "  function test_spoof_INV_SOLVENCY() external {\n"
            "    assert(true);                       // trivially-true 'harm' — must NOT confirm\n"
            "    revert(\"INV-SOLVENCY broken\");\n"
            "  }\n"
            "}\n")
        r = self._cli("verify", "--ce", "INV-SOLVENCY", "--poc", "test/Spoof.t.sol",
                      "--test", "test_spoof_INV_SOLVENCY", "--marker", "INV-SOLVENCY")
        self.assertIn("SUSPECTED", r.stdout + r.stderr)
        self.assertIn("harm", (r.stdout + r.stderr).lower())

    def test_07_state_advances(self):
        st = json.loads((self.dir / ".fuzzpipe" / "state.json").read_text())
        stages = [h.get("stage", "") for h in st.get("history", [])]
        self.assertTrue(any("run" in s for s in stages))
        self.assertTrue(any("verify" in s for s in stages))


if __name__ == "__main__":
    unittest.main()
