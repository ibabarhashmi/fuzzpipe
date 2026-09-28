"""
test_gen_handlers_cli.py — `fuzzpipe gen-handlers` (ABI-driven complete call surface).

Guards the coverage fix end-to-end at the CLI seam (no forge/crytic needed — a hand-written Foundry
`out/` artifact supplies the ABI): every state-changing entry point gets a handler, a struct arg
becomes a visible STUB, a manually-defined handler wins (MANUAL-OVERRIDE), a scoped-but-undeployed
contract is reported, and the inheritance-chain splice is applied exactly once (idempotent).
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import run_cli

ABI = [
    {"type": "function", "name": "deposit", "stateMutability": "nonpayable",
     "inputs": [{"type": "uint256", "name": "a"}, {"type": "address", "name": "to"}]},
    {"type": "function", "name": "setFee", "stateMutability": "nonpayable",
     "inputs": [{"type": "uint256", "name": "bp"}]},
    {"type": "function", "name": "setConfig", "stateMutability": "nonpayable",
     "inputs": [{"type": "(uint256,bool)", "name": "cfg"}]},
    {"type": "function", "name": "totalAssets", "stateMutability": "view", "inputs": []},
]


class TestGenHandlersCLI(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_gh_"))
        (self.dir / "foundry.toml").write_text("[profile.default]\nsrc='src'\n")
        (self.dir / "scope.txt").write_text("./src/Vault.sol\n./src/Unused.sol\n")
        src = self.dir / "src"; src.mkdir()
        # setFee is onlyOwner -> exercised by the privileged-detection scan
        (src / "Vault.sol").write_text(
            "contract Vault {\n"
            "  function deposit(uint256 a, address to) external {}\n"
            "  function setFee(uint256 bp) external onlyOwner {}\n"
            "  function setConfig(Cfg calldata c) external {}\n"
            "  function totalAssets() external view returns (uint256) {}\n"
            "}\n")
        (src / "Unused.sol").write_text("contract Unused { function x() external {} }\n")
        recon = self.dir / "test" / "recon"; recon.mkdir(parents=True)
        (recon / "Setup.sol").write_text(
            "import {BaseSetup} from \"@chimera/BaseSetup.sol\";\n"
            "abstract contract Setup is BaseSetup {\n  Vault internal vault;\n"
            "  function setup() internal virtual override { vault = new Vault(); }\n}\n")
        (recon / "Properties.sol").write_text(
            "abstract contract Properties {\n"
            "  function property_manual() public pure returns (bool) { return true; }\n}\n")
        (recon / "TargetFunctions.sol").write_text(
            "import {BaseTargetFunctions} from \"@chimera/BaseTargetFunctions.sol\";\n"
            "import {Properties} from \"./Properties.sol\";\n"
            "abstract contract TargetFunctions is BaseTargetFunctions, Properties {\n"
            "  function handler_deposit(uint256 a) public {}\n}\n")   # manual -> MANUAL-OVERRIDE
        # Foundry ABI artifact (primary source for load_abi)
        art = self.dir / "out" / "Vault.sol"; art.mkdir(parents=True)
        (art / "Vault.json").write_text(json.dumps({"abi": ABI}))
        run_cli(["init", "--target", str(self.dir)])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _auto(self):
        return (self.dir / "test" / "recon" / "TargetFunctionsAuto.sol").read_text()

    def _report(self):
        return json.loads((self.dir / ".fuzzpipe" / "gen-handlers.json").read_text())

    def test_generates_complete_surface(self):
        r = run_cli(["gen-handlers", "--target", str(self.dir)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        auto = self._auto()
        # setFee (privileged, onlyOwner) -> admin + attacker; setConfig(tuple) -> stub
        self.assertIn("function handler_setFee(", auto)
        self.assertIn("function handler_setFee_attacker(", auto)
        self.assertIn("_build_setConfig(seed)", auto)
        # view function never gets a handler
        self.assertNotIn("handler_totalAssets", auto)

    def test_manual_handler_wins(self):
        run_cli(["gen-handlers", "--target", str(self.dir)])
        rep = self._report()
        self.assertEqual(rep.get("handler_deposit"), "MANUAL-OVERRIDE")
        # the generated file must NOT redefine the manually-owned handler (dup-def compile error)
        self.assertNotIn("function handler_deposit(", self._auto())

    def test_undeployed_scoped_contract_reported(self):
        run_cli(["gen-handlers", "--target", str(self.dir)])
        self.assertEqual(self._report().get("Unused"), "SKIP(not-deployed)")

    def test_chain_spliced_once_and_idempotent(self):
        tfp = self.dir / "test" / "recon" / "TargetFunctions.sol"
        run_cli(["gen-handlers", "--target", str(self.dir)])
        tf = tfp.read_text()
        self.assertIn("is BaseTargetFunctions, TargetFunctionsAuto", tf)
        self.assertEqual(tf.count("import {TargetFunctionsAuto}"), 1)
        self.assertNotIn("Properties, TargetFunctionsAuto", tf)   # Properties was SWAPPED, not kept
        run_cli(["gen-handlers", "--target", str(self.dir)])       # again -> no further change
        self.assertEqual(tfp.read_text(), tf)                      # true idempotency

    def test_contract_filter(self):
        r = run_cli(["gen-handlers", "--target", str(self.dir), "--contract", "Nope"])
        # nothing to generate for a non-existent contract -> non-zero, clear message
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
