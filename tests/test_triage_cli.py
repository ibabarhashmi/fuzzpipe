"""Q2/Q3 at the REAL wiring: `fuzzpipe triage` on a Medusa sequence carrying bool + array +
address args must NOT crash (v0.2 raised `TypeError: expected str instance, bool found`) and must
emit valid, type-aware Solidity. This drives the parse->render seam through the real command."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _util


BOOL_ARRAY_SEQ = [
    {"call": {"from": "0x0000000000000000000000000000000000001111",
              "dataAbiValues": {"methodSignature": "handler_toggle(bool,uint256)",
                                "inputValues": [True, 42]}},
     "blockNumberDelay": 0, "blockTimestampDelay": 3},
    {"call": {"dataAbiValues": {"methodSignature": "handler_batch(uint256[])",
                                "inputValues": [[1, 2, 3]]}},
     "blockNumberDelay": 1, "blockTimestampDelay": 0},
    {"call": {"dataAbiValues": {"methodSignature": "handler_transfer(address,uint256)",
                                "inputValues": ["0x00000000000000000000000000000000000000aa", 1000]}}},
]


class TestTriageBoolAndArrayArgs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fuzzpipe_triage_"))
        rd = self.tmp / ".fuzzpipe" / "corpus" / "medusa" / "test_results"
        rd.mkdir(parents=True)
        (rd / "seq1.json").write_text(json.dumps(BOOL_ARRAY_SEQ))
        (self.tmp / "test" / "recon").mkdir(parents=True)
        (self.tmp / "foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_triage_does_not_crash_and_renders_typed_solidity(self):
        r = _util.run_cli(["triage", "--target", str(self.tmp)])
        combined = r.stdout + r.stderr
        self.assertNotIn("Traceback", combined, "triage crashed (Q2 regression)")
        self.assertNotIn("TypeError", combined)
        self.assertEqual(r.returncode, 0)
        repro = (self.tmp / "test" / "MedusaReproducers.t.sol").read_text()
        # bool + uint render inline (was the exact TypeError input)
        self.assertIn("this.handler_toggle(true, 42);", repro)
        # dynamic array renders as a valid memory prelude, not `uint256[](1,2,3)`
        self.assertIn("new uint256[](3);", repro)
        self.assertIn("this.handler_batch(_a1_0);", repro)
        # address is wrapped
        self.assertIn("address(0x00000000000000000000000000000000000000aa)", repro)


if __name__ == "__main__":
    unittest.main()
