"""
test_handlers.py — the ABI-driven handler generator (`cli/handlers.py`).

Guards the coverage fix: the fuzzer's call surface must be COMPLETE (one handler per state-changing
entry point) with type-correct, clamped, revert-tolerant bodies — decoupled from invariant count.
Pure unit tests over hand-crafted ABIs; no forge/crytic needed.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _util  # noqa: F401  (puts cli/ on sys.path)
import handlers as h


class TestHandlerArg(unittest.TestCase):
    def test_uint256_clamps_to_cap(self):
        params, body, call = h.handler_arg(0, "uint256")
        self.assertEqual(params, ["uint256 arg0"])
        self.assertIn("between(arg0, 0,", body[0])
        self.assertEqual(call, "arg0")

    def test_narrow_uint_casts_through_uint256(self):
        params, body, call = h.handler_arg(1, "uint64")
        self.assertEqual(params, ["uint64 arg1"])
        self.assertIn("uint64(between(uint256(arg1)", body[0])

    def test_bool_is_raw(self):
        params, body, call = h.handler_arg(0, "bool")
        self.assertEqual((params, body, call), (["bool arg0"], [], "arg0"))

    def test_address_becomes_seed_resolved_to_known_address(self):
        params, body, call = h.handler_arg(2, "address")
        self.assertEqual(params, ["uint256 arg2Seed"])
        self.assertEqual(body, ["address arg2 = _pickAddr(arg2Seed);"])
        self.assertEqual(call, "arg2")

    def test_dynamic_array_is_length_bounded(self):
        params, body, call = h.handler_arg(0, "address[]")
        self.assertIn("uint256 arg0N", params)
        self.assertTrue(any("between(arg0N, 0," in b for b in body))
        self.assertTrue(any("_pickAddr(arg0Seed + i)" in b for b in body))
        self.assertEqual(call, "arg0Arr")

    def test_tuple_returns_none(self):
        self.assertIsNone(h.handler_arg(0, "(uint256,address)"))

    def test_string_and_bytes_are_memory(self):
        self.assertEqual(h.handler_arg(0, "string")[0], ["string memory arg0"])
        self.assertEqual(h.handler_arg(0, "bytes")[0], ["bytes memory arg0"])


class TestRenderHandler(unittest.TestCase):
    def _fn(self, name, inputs, sm="nonpayable"):
        return {"type": "function", "name": name, "stateMutability": sm,
                "inputs": [{"type": t, "name": ""} for t in inputs]}

    def test_plain_handler_shape(self):
        name, src, status = h.render_handler("vault", self._fn("deposit", ["uint256", "address"]))
        self.assertEqual(status, "GEN")
        self.assertEqual(name, "handler_deposit")
        self.assertIn("_useActor(actorSeed)", src)
        self.assertIn("vm.prank(currentActor)", src)
        self.assertIn("try vault.deposit(arg0, arg1) {} catch {}", src)

    def test_privileged_emits_admin_and_attacker(self):
        name, src, status = h.render_handler("t", self._fn("setFee", ["uint256"]), privileged=True)
        self.assertEqual(status, "GEN(privileged)")
        self.assertIn("function handler_setFee(", src)                 # admin (no prank)
        self.assertIn("function handler_setFee_attacker(", src)        # attacker (pranked)

    def test_owner_family_is_privileged_without_flag(self):
        _n, _s, status = h.render_handler("t", self._fn("transferOwnership", ["address"]))
        self.assertEqual(status, "GEN(privileged)")

    def test_payable_adds_value(self):
        _n, src, _s = h.render_handler("t", self._fn("stake", ["uint256"], sm="payable"))
        self.assertIn("uint256 msgValue", src)
        self.assertIn("vm.deal(currentActor, msgValue)", src)
        self.assertIn("{value: msgValue}", src)

    def test_tuple_arg_becomes_stub_hook(self):
        name, src, status = h.render_handler("t", self._fn("setConfig", ["(uint256,bool)"]))
        self.assertEqual(status, "STUB(tuple)")
        self.assertIn("_build_setConfig(seed)", src)
        self.assertIn("internal virtual", src)

    def test_multi_namespaces_by_instance(self):
        name, _s, _st = h.render_handler("pool", self._fn("swap", ["uint256"]), multi=True)
        self.assertEqual(name, "handler_pool_swap")


class TestLoadAbi(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_abi_"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _foundry_artifact(self, contract, abi):
        d = self.dir / "out" / (contract + ".sol")
        d.mkdir(parents=True, exist_ok=True)
        (d / (contract + ".json")).write_text(json.dumps({"abi": abi}))

    def _crytic(self, contract, abi):
        d = self.dir / "crytic-export"
        d.mkdir(parents=True, exist_ok=True)
        (d / "combined_solc.json").write_text(json.dumps(
            {"contracts": {"src/%s.sol:%s" % (contract, contract): {"abi": json.dumps(abi)}}}))

    def test_foundry_out_preferred(self):
        self._foundry_artifact("V", [{"type": "function", "name": "fromOut"}])
        self._crytic("V", [{"type": "function", "name": "fromCrytic"}])
        abi = h.load_abi(self.dir, "V")
        self.assertEqual(abi[0]["name"], "fromOut")

    def test_crytic_string_abi_decoded(self):
        self._crytic("V", [{"type": "function", "name": "fromCrytic",
                            "stateMutability": "nonpayable", "inputs": []}])
        abi = h.load_abi(self.dir, "V")
        self.assertEqual(abi[0]["name"], "fromCrytic")

    def test_missing_returns_empty(self):
        self.assertEqual(h.load_abi(self.dir, "Nope"), [])


class TestMutatingFunctions(unittest.TestCase):
    def test_skips_view_pure_and_events(self):
        abi = [
            {"type": "function", "name": "deposit", "stateMutability": "nonpayable", "inputs": []},
            {"type": "function", "name": "balanceOf", "stateMutability": "view", "inputs": []},
            {"type": "function", "name": "pureCalc", "stateMutability": "pure", "inputs": []},
            {"type": "event", "name": "Deposit"},
            {"type": "function", "name": "pay", "stateMutability": "payable", "inputs": []},
        ]
        names = [f["name"] for f in h.mutating_functions(abi)]
        self.assertEqual(names, ["deposit", "pay"])


if __name__ == "__main__":
    unittest.main()
