"""
test_coverage_audit.py — the machine-enforced completeness gate (`fuzzpipe ir coverage-audit`).

Guards:
  * the surface scanner sees functions WITH a `returns (...)` clause (the balanced-paren fix — a
    greedy regex silently dropped them, an under-report = false PASS);
  * view/pure functions, internal helpers and the constructor are NOT counted as entry points;
  * a gap (uncovered entry point) fails the gate (exit 2);
  * a justified waiver clears a gap; an empty-reason waiver does NOT;
  * a privileged (modifier-gated) function with no AUTHORIZATION invariant is flagged.
"""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import load_fuzzpipe, run_cli

fz = load_fuzzpipe()

SRC = """
pragma solidity ^0.8.20;
contract T {
    uint256 public totalAssets;
    address public owner;
    function deposit(uint256 a) external returns (uint256 minted) { totalAssets += a; }
    function redeem(uint256 s) public returns (uint256 out) { return s; }
    function poke() external { }
    function setFee(uint256 f) external onlyOwner { }
    function preview(uint256 a) external view returns (uint256) { return a; }
    function _helper() internal { }
    constructor() { owner = msg.sender; }
    modifier onlyOwner() { _; }
}
"""


def _scan(src):
    eps, priv = set(), set()
    for name, tail in fz._iter_functions(src):
        if name == "constructor":
            continue
        if not re.search(r"\b(external|public)\b", tail):
            continue
        if re.search(r"\b(view|pure)\b", tail):
            continue
        eps.add(name)
        if any(m in tail for m in fz._PRIV_MODS):
            priv.add(name)
    return eps, priv


class TestSurfaceScan(unittest.TestCase):
    def test_returns_clause_functions_detected(self):
        eps, _ = _scan(SRC)
        self.assertIn("deposit", eps)   # has `returns (uint256 minted)`
        self.assertIn("redeem", eps)    # has `returns (uint256 out)`
        self.assertIn("poke", eps)
        self.assertIn("setFee", eps)

    def test_view_internal_constructor_excluded(self):
        eps, _ = _scan(SRC)
        self.assertNotIn("preview", eps)
        self.assertNotIn("_helper", eps)
        self.assertNotIn("constructor", eps)

    def test_privileged_detected(self):
        _, priv = _scan(SRC)
        self.assertIn("setFee", priv)

    def test_iter_functions_never_crashes(self):
        list(fz._iter_functions("function f(uint256 a"))   # unbalanced, no crash
        list(fz._iter_functions("function"))


class TestCoverageAuditCLI(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_cvaudit_"))
        (self.dir / "src").mkdir()
        (self.dir / "src" / "T.sol").write_text(SRC)
        (self.dir / "foundry.toml").write_text("[profile.default]\nsrc = 'src'\n")
        run_cli(["init", "--target", str(self.dir)])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _put_ir(self, invs):
        f = self.dir / "ir.json"
        f.write_text(json.dumps({"invariants": invs}))
        run_cli(["ir", "put", "--target", str(self.dir), "--file", str(f)])

    def _inv(self, iid, targets, shape="SAFETY", scope="global", stmt="x"):
        return {"id": iid, "statement": stmt, "category": "valid-state", "shape": shape,
                "scope": scope, "predicate": {"expr": "x"}, "targets": targets,
                "severity_if_broken": "high", "tier_hint": 0, "status": "approved"}

    def test_gap_fails_with_exit_2(self):
        self._put_ir([self._inv("INV-A", ["T.deposit"], stmt="deposit and totalAssets")])
        r = run_cli(["ir", "coverage-audit", "--target", str(self.dir)])
        self.assertEqual(r.returncode, 2)
        self.assertIn("GAP", r.stdout + r.stderr)

    def test_full_coverage_passes(self):
        self._put_ir([
            self._inv("INV-A", ["T.deposit", "T.redeem", "T.poke"], stmt="deposit redeem poke totalAssets"),
            self._inv("INV-AUTH", ["T.setFee"], shape="AUTHORIZATION", stmt="only owner setFee"),
        ])
        # owner state var covered via a waiver
        (self.dir / ".fuzzpipe" / "coverage-waivers.json").write_text(
            json.dumps({"owner": "read-only address; no fund-flow invariant needed"}))
        r = run_cli(["ir", "coverage-audit", "--target", str(self.dir)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASSED", r.stdout)

    def test_empty_waiver_does_not_clear_gap(self):
        self._put_ir([
            self._inv("INV-A", ["T.deposit", "T.redeem", "T.poke", "T.setFee"],
                      stmt="deposit redeem poke setFee totalAssets owner")])
        # empty reason must be ignored -> setFee still needs authz, but owner/totalAssets covered
        (self.dir / ".fuzzpipe" / "coverage-waivers.json").write_text(json.dumps({"setFee": ""}))
        r = run_cli(["ir", "coverage-audit", "--target", str(self.dir)])
        # setFee is privileged and has no AUTHORIZATION invariant -> still a gap despite empty waiver
        self.assertEqual(r.returncode, 2)
        self.assertIn("privileged-no-authz", r.stdout)


if __name__ == "__main__":
    unittest.main()
