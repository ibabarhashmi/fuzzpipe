"""Q1 (guarded probe) + R6 (real wall-clock timeout) at the helper level."""
import time
import unittest

import _util  # noqa: F401  (sets sys.path)
import proc


class TestProc(unittest.TestCase):
    def test_run_probe_missing_tool_never_raises(self):
        """A missing binary must return (127, '') — never a FileNotFoundError (Q1 root cause)."""
        rc, out = proc.run_probe(["fuzzpipe_no_such_tool_xyz", "--version"])
        self.assertEqual(rc, proc.RC_MISSING)
        self.assertEqual(out, "")

    def test_run_bounded_kills_runaway(self):
        """A child that outlives its budget is TERMINATED at the wall-clock bound (R6).
        A no-op timeout would let a hung child outlive its budget (a 4s child surviving a
        sub-second bound); this guard uses a real wall-clock timeout that kills the child."""
        start = time.monotonic()
        rc, out = proc.run_bounded(["sleep", "4"], 1)
        elapsed = time.monotonic() - start
        self.assertEqual(rc, proc.RC_TIMEOUT)
        self.assertEqual(out, "TIMEOUT")
        self.assertLess(elapsed, 3.0, "timeout did not actually kill the child (R6 regression)")

    def test_run_bounded_missing_tool(self):
        rc, out = proc.run_bounded(["fuzzpipe_no_such_tool_xyz"], 5)
        self.assertEqual(rc, proc.RC_MISSING)


if __name__ == "__main__":
    unittest.main()
