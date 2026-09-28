"""R5: harnesses land in engine-discoverable paths + a preflight catches the undiscovered case.

A harness written where forge never looks comes back UNTESTED while looking like it ran — the
failure mode this guard designs out. v2.1 puts the harness at test/recon/ (which forge compiles)
and ships `verify-harness` to assert discovery BEFORE a campaign is spent."""
import shutil
import tempfile
import unittest
from pathlib import Path

import _util


class TestReconPathDiscoverable(unittest.TestCase):
    def test_recon_dir_is_a_forge_discoverable_path(self):
        # load the extensionless fuzzpipe script with an explicit source loader
        import importlib.util
        from importlib.machinery import SourceFileLoader
        loader = SourceFileLoader("fuzzpipe_cli", str(_util.FUZZPIPE))
        spec = importlib.util.spec_from_loader("fuzzpipe_cli", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        self.assertTrue(str(mod._recon_dir("/x", "foundry")).endswith("test/recon"))
        self.assertTrue(str(mod._recon_dir("/x", "hardhat")).endswith("contracts/recon"))


@unittest.skipUnless(_util.have("forge"), "forge required for the discovery preflight")
class TestVerifyHarnessPreflight(unittest.TestCase):
    def test_preflight_passes_when_harness_present(self):
        proj = _util.copy_fixture("harness_ok_project")
        try:
            r = _util.run_cli(["verify-harness", "--target", str(proj)])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(proj, ignore_errors=True)

    def test_preflight_fails_when_harness_missing(self):
        proj = Path(tempfile.mkdtemp(prefix="fuzzpipe_empty_"))
        (proj / "foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\n")
        try:
            r = _util.run_cli(["verify-harness", "--target", str(proj)])
            self.assertEqual(r.returncode, 1,
                             "preflight must FAIL when no harness is discoverable (R5)")
        finally:
            shutil.rmtree(proj, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
