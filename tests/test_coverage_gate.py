"""
test_coverage_gate.py — the HARD coverage gate (`fuzzpipe coverage --gate`).

Guards the enforcement fix: a low-coverage / uncovered-entry-point campaign can no longer pass as
'safe'. The gate blocks (exit 2) on an unwaived MISS or below --min-pct, and passes only when every
uncovered function carries a justified waiver. The DEFAULT (non-gate) behavior must stay identical
to before (test_coverage_cli.py still owns that).
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import run_cli


def _cov(target, body):
    d = target / ".fuzzpipe" / "corpus" / "medusa" / "coverage"
    d.mkdir(parents=True, exist_ok=True)
    (d / "lcov.info").write_text(body)


# 50% lines, withdraw() never hit
LCOV = "SF:src/Vault.sol\nFNDA:5,deposit\nFNDA:0,withdraw\nDA:10,1\nDA:11,0\nend_of_record\n"


class TestCoverageGate(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_gate_"))
        (self.dir / "foundry.toml").write_text("[profile.default]\nsrc='src'\n")
        run_cli(["init", "--target", str(self.dir)])
        _cov(self.dir, LCOV)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _waive(self, obj):
        import json
        (self.dir / ".fuzzpipe" / "coverage-waivers.json").write_text(json.dumps(obj))

    def _run(self, *extra):
        return run_cli(["coverage", "--target", str(self.dir), "--engine", "medusa", *extra])

    def test_gate_blocks_unwaived_miss(self):
        r = self._run("--gate")
        self.assertEqual(r.returncode, 2)
        self.assertIn("GATE FAILED", r.stdout + r.stderr)
        self.assertIn("withdraw", r.stdout)

    def test_gate_passes_with_justified_waiver(self):
        self._waive({"withdraw": "unreachable until migration; out of audit scope"})
        r = self._run("--gate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GATE PASSED", r.stdout)

    def test_empty_reason_waiver_is_ignored(self):
        self._waive({"withdraw": ""})           # empty reason must not silently pass
        self.assertEqual(self._run("--gate").returncode, 2)

    def test_min_pct_floor_enforced(self):
        # fully waive the MISS so only the % floor can fail; 50% < 90% -> block
        self._waive({"withdraw": "waived for this test"})
        self.assertEqual(self._run("--gate", "--min-pct", "90").returncode, 2)
        self.assertEqual(self._run("--gate", "--min-pct", "40").returncode, 0)

    def test_default_behavior_unchanged(self):
        # without --gate: any uncovered in-scope fn is still exit 2 (the classic loop-back signal)
        self.assertEqual(self._run().returncode, 2)


if __name__ == "__main__":
    unittest.main()
