"""
test_parallel.py — proc.run_many_bounded, the v2.2 concurrent-campaign primitive.

Guards:
  * concurrency is real (N sleeps run in overlapping wall-clock, not summed);
  * each child keeps its OWN wall-clock bound (a hung child is killed, siblings survive);
  * results are attributable and ORDER-PRESERVING (key -> outcome), so a shard maps to its invariant;
  * a missing binary in one job never takes down the pool.
"""
import time
import unittest

import _util  # noqa: F401  (path setup)
import proc


class TestRunManyBounded(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(proc.run_many_bounded([]), [])

    def test_concurrency_is_real(self):
        # four 1s sleeps with a pool of 4 finish in ~1s wall-clock, not ~4s.
        jobs = [{"key": i, "cmd": ["sleep", "1"], "timeout_s": 5} for i in range(4)]
        t0 = time.time()
        out = proc.run_many_bounded(jobs, max_workers=4)
        elapsed = time.time() - t0
        self.assertEqual([k for k, _, _ in out], [0, 1, 2, 3])   # order preserved
        self.assertTrue(all(rc == 0 for _, rc, _ in out))
        self.assertLess(elapsed, 3.0, "4x1s sleeps took %.2fs — not running concurrently" % elapsed)

    def test_per_child_timeout_isolation(self):
        # one hung child (sleep 5, bound 1s) is killed; its sibling (sleep 0) still succeeds.
        jobs = [
            {"key": "hung", "cmd": ["sleep", "5"], "timeout_s": 1},
            {"key": "fast", "cmd": ["sleep", "0"], "timeout_s": 5},
        ]
        t0 = time.time()
        out = dict((k, rc) for k, rc, _ in proc.run_many_bounded(jobs, max_workers=2))
        elapsed = time.time() - t0
        self.assertEqual(out["hung"], proc.RC_TIMEOUT)
        self.assertEqual(out["fast"], 0)
        self.assertLess(elapsed, 3.0, "hung child was not bounded at 1s (took %.2fs)" % elapsed)

    def test_missing_binary_does_not_break_pool(self):
        jobs = [
            {"key": "missing", "cmd": ["definitely-not-a-real-binary-xyz"], "timeout_s": 5},
            {"key": "ok", "cmd": ["sleep", "0"], "timeout_s": 5},
        ]
        out = dict((k, rc) for k, rc, _ in proc.run_many_bounded(jobs))
        self.assertEqual(out["missing"], proc.RC_MISSING)
        self.assertEqual(out["ok"], 0)

    def test_default_jobs_bounds(self):
        self.assertEqual(proc.default_jobs(1), 1)
        self.assertGreaterEqual(proc.default_jobs(100), 1)
        self.assertLessEqual(proc.default_jobs(3), 3)   # never more workers than items


if __name__ == "__main__":
    unittest.main()
