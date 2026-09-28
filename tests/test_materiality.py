"""
test_materiality.py — the `fuzzpipe materiality` sweep (guidance/07 filter 3, mechanical FP gate).

Replays an invariant reproducer across log-spaced input scales and classifies the break:
  * DUST-ONLY (exit 2) — breaks only below the materiality threshold -> a bad-invariant false positive;
  * MATERIAL  (exit 0) — breaks at a material scale -> a genuine candidate;
  * HELD      (exit 0) — never falsified in the sweep.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import have, load_fuzzpipe, run_cli

fz = load_fuzzpipe()


class TestMaterialityPure(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(fz._parse_amount("1e24"), 10 ** 24)
        self.assertEqual(fz._parse_amount("5_000"), 5000)
        self.assertEqual(fz._parse_amount("2e18"), 2 * 10 ** 18)

    def test_log_grid_endpoints_and_shape(self):
        g = fz._log_grid(1, 1000)
        self.assertEqual(g[0], 1)
        self.assertEqual(g[-1], 1000)
        self.assertIn(500, g)           # 1-2-5 spacing
        self.assertEqual(g, sorted(set(g)))

    def test_verdict(self):
        dust = [(1, True), (500, True), (1000, False), (10 ** 6, False)]
        self.assertEqual(fz._materiality_verdict(dust, 1000)[:2], ("DUST-ONLY", 2))
        material = [(1, True), (1000, True), (10 ** 6, True)]
        self.assertEqual(fz._materiality_verdict(material, 1000)[:2], ("MATERIAL", 0))
        held = [(1, False), (1000, False)]
        self.assertEqual(fz._materiality_verdict(held, 1000)[:2], ("HELD", 0))

    def test_test_broke(self):
        self.assertTrue(fz._test_broke("[FAIL: dust] test_x() (gas: 1)", "test_x"))
        self.assertFalse(fz._test_broke("[PASS] test_x() (gas: 1)", "test_x"))
        self.assertIsNone(fz._test_broke("compile error", "test_x"))


# A self-contained sweep test that reads the amount via the hevm cheatcode (no forge-std needed) and
# "breaks" (out == 0) only for amount < 1000 — the canonical dust-only shape.
_SWEEP_SOL = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
interface IVm { function envOr(string calldata, uint256) external returns (uint256); }
contract Sweep {
    IVm constant vm = IVm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
    function test_sweep() external {
        uint256 amount = vm.envOr("FUZZPIPE_SWEEP_AMOUNT", uint256(1));
        require(amount / 1000 > 0, "dust-only break: out==0 for amount < 1000");
    }
}
"""


@unittest.skipUnless(have("forge"), "forge not installed")
class TestMaterialityCLI(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_mat_"))
        (self.dir / "test").mkdir()
        (self.dir / "test" / "Sweep.t.sol").write_text(_SWEEP_SOL)
        (self.dir / "foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\n")
        (self.dir / "src").mkdir()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_dust_only_is_flagged_exit_2(self):
        # breaks up to 500 (all < 1e6 material) -> DUST-ONLY
        r = run_cli(["materiality", "--target", str(self.dir), "--test", "test_sweep",
                     "--min", "1", "--max", "100000", "--material", "1000000"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("DUST", (r.stdout + r.stderr).upper())

    def test_material_break_is_genuine_exit_0(self):
        # with a low threshold (100), the break at 500 is 'material' -> genuine candidate
        r = run_cli(["materiality", "--target", str(self.dir), "--test", "test_sweep",
                     "--min", "1", "--max", "100000", "--material", "100"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("MATERIAL", (r.stdout + r.stderr).upper())

    def test_held_when_never_breaks(self):
        # sweep only amounts >= 1000 -> never breaks -> HELD
        r = run_cli(["materiality", "--target", str(self.dir), "--test", "test_sweep",
                     "--min", "1000", "--max", "100000", "--material", "1000000"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("HELD", (r.stdout + r.stderr).upper())


if __name__ == "__main__":
    unittest.main()
