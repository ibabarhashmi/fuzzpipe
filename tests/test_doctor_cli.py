"""Q1 at the REAL wiring: `fuzzpipe doctor` on a PATH without crytic-compile must exit 0
gracefully, not raise an uncaught FileNotFoundError (the v0.2 crash was at the call site,
not in a helper — so this drives the actual command)."""
import unittest

import _util


class TestDoctorNoCrytic(unittest.TestCase):
    def test_doctor_graceful_without_crytic(self):
        # scrub PATH so crytic-compile (and the other engines) are guaranteed absent — the exact
        # fresh-machine state `doctor` exists to diagnose, and the one that crashed v0.2.
        r = _util.run_cli(["doctor"], env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
        combined = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, "doctor must exit 0 even with tools missing")
        self.assertNotIn("Traceback", combined, "doctor crashed (Q1 regression)")
        self.assertNotIn("FileNotFoundError", combined)
        self.assertIn("crytic-compile", combined)
        self.assertIn("MISSING", combined)


if __name__ == "__main__":
    unittest.main()
