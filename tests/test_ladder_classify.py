"""
test_ladder_classify.py — Tier-1 classification + staged-config path fixes.

Both bugs were found by running the parallel ladder against a REAL medusa (the fake-engine test
could not surface them):
  * a fuzzer that runs its whole wall-clock budget without self-terminating found NO counterexample
    -> a TIMEOUT must classify as 'clean' (no-CE-in-budget), NOT a false 'break';
  * medusa resolves a `--config` file's relative paths against the CONFIG dir, so a staged
    per-invariant config must use ABSOLUTE paths for the compile target and corpus dir;
  * a medusa 'break' must be confirmed by a written failing sequence (artifact), so an engine/compile
    error that exits non-zero can't masquerade as a counterexample.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import proc
from _util import load_fuzzpipe

fz = load_fuzzpipe()


class TestClassifyRc(unittest.TestCase):
    def test_timeout_is_not_a_break(self):
        self.assertEqual(fz._classify_rc("medusa", proc.RC_TIMEOUT, 40), "clean")
        self.assertEqual(fz._classify_rc("echidna", proc.RC_TIMEOUT, 40), "clean")

    def test_missing_is_untested(self):
        self.assertEqual(fz._classify_rc("medusa", proc.RC_MISSING, 40), "untested")

    def test_clean_and_break(self):
        self.assertEqual(fz._classify_rc("medusa", 0, 40), "clean")
        self.assertEqual(fz._classify_rc("medusa", 1, 40), "break_or_error")


class TestStagedConfigAbsolutePaths(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_stage_"))
        (self.dir / "test" / "recon").mkdir(parents=True)
        (self.dir / "test" / "recon" / "CryticTester.sol").write_text("// harness")
        (self.dir / "foundry.toml").write_text("[profile.default]\nsrc='contracts'\n")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_target_and_corpus_are_absolute(self):
        out = fz._stage_medusa_config_for_invariant(self.dir, "INV-X", 64, 1000)
        cfg = json.loads(out.read_text())
        target = cfg["compilation"]["platformConfig"]["target"]
        corpus = cfg["fuzzing"]["corpusDirectory"]
        self.assertTrue(Path(target).is_absolute(), "compile target must be absolute for a staged config")
        self.assertTrue(Path(corpus).is_absolute(), "corpus dir must be absolute for a staged config")
        self.assertTrue(target.endswith("test/recon/CryticTester.sol"))
        self.assertTrue(corpus.endswith("corpus/medusa/INV-X"))


class TestShardHasBreaks(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_shb_"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_false_when_no_artifacts(self):
        self.assertFalse(fz._shard_has_breaks(self.dir, "INV-X"))
        self.assertFalse(fz._shard_has_breaks(self.dir, None))

    def test_true_when_failing_sequence_written(self):
        tr = self.dir / ".fuzzpipe" / "corpus" / "medusa" / "INV-X" / "test_results"
        tr.mkdir(parents=True)
        (tr / "fail.json").write_text("{}")
        self.assertTrue(fz._shard_has_breaks(self.dir, "INV-X"))


if __name__ == "__main__":
    unittest.main()
