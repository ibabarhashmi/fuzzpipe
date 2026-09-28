"""
test_coverage_cli.py — the lcov coverage parser + path binding (`fuzzpipe coverage`).

The parser was previously untested and the lcov path was assumed, never validated. These guard:
  * an uncovered in-scope function -> exit 2 (the actionable loop-back signal) and is named;
  * all-covered in-scope functions -> exit 0;
  * lib/test/recon paths are out of scope and don't count;
  * a missing lcov file -> a clean error, not a crash.
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


class TestCoverageCLI(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_cov_"))
        (self.dir / "foundry.toml").write_text("[profile.default]\nsrc='src'\n")
        run_cli(["init", "--target", str(self.dir)])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_uncovered_function_flags_exit_2(self):
        _cov(self.dir,
             "SF:src/Vault.sol\nFNDA:5,deposit\nFNDA:0,withdraw\nDA:10,1\nDA:11,0\nend_of_record\n")
        r = run_cli(["coverage", "--target", str(self.dir), "--engine", "medusa"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("withdraw", r.stdout)

    def test_all_covered_exit_0(self):
        _cov(self.dir,
             "SF:src/Vault.sol\nFNDA:5,deposit\nFNDA:2,withdraw\nDA:10,1\nDA:11,3\nend_of_record\n")
        r = run_cli(["coverage", "--target", str(self.dir), "--engine", "medusa"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_lib_paths_out_of_scope(self):
        # only a lib file present -> nothing in scope -> warns, exit 1 (not a false 'all covered')
        _cov(self.dir, "SF:lib/forge-std/Test.sol\nFNDA:0,foo\nDA:1,0\nend_of_record\n")
        r = run_cli(["coverage", "--target", str(self.dir), "--engine", "medusa"])
        self.assertEqual(r.returncode, 1)

    def test_missing_lcov_is_clean_error(self):
        r = run_cli(["coverage", "--target", str(self.dir), "--engine", "medusa"])
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
