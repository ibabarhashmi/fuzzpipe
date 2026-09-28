"""
test_hardhat.py — the Hardhat config rewrite (`_ensure_hardhat_foundry_plugin`).

This is the most complex mutating path (it rewrites the user's hardhat.config in place) and was
previously zero-tested. We pre-create the node_modules marker so the npm install is skipped and only
the config-rewrite runs — asserting it: injects the plugin, backs up the original, is idempotent,
and picks the right import/require form.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import load_fuzzpipe

fz = load_fuzzpipe()


class TestHardhatFoundryPlugin(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_hh_"))
        # pre-create the installed-plugin marker so the install step is skipped
        (self.dir / "node_modules" / "@nomicfoundation" / "hardhat-foundry").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _cfg(self, name, text):
        (self.dir / name).write_text(text)
        return self.dir / name

    def test_ts_config_gets_import_and_backup(self):
        cfg = self._cfg("hardhat.config.ts",
                        'import { HardhatUserConfig } from "hardhat/config";\n'
                        'export default { solidity: "0.8.20" };\n')
        rc = fz._ensure_hardhat_foundry_plugin(self.dir)
        self.assertEqual(rc, 0)
        out = cfg.read_text()
        self.assertIn('import "@nomicfoundation/hardhat-foundry";', out)
        self.assertTrue((self.dir / "hardhat.config.ts.bak").exists())
        # original content preserved below the injected line
        self.assertIn("export default", out)

    def test_js_config_gets_require(self):
        cfg = self._cfg("hardhat.config.js", 'module.exports = { solidity: "0.8.20" };\n')
        rc = fz._ensure_hardhat_foundry_plugin(self.dir)
        self.assertEqual(rc, 0)
        self.assertIn('require("@nomicfoundation/hardhat-foundry");', cfg.read_text())

    def test_idempotent(self):
        cfg = self._cfg("hardhat.config.js", 'module.exports = {};\n')
        fz._ensure_hardhat_foundry_plugin(self.dir)
        first = cfg.read_text()
        rc = fz._ensure_hardhat_foundry_plugin(self.dir)   # second call is a no-op
        self.assertEqual(rc, 0)
        self.assertEqual(cfg.read_text(), first)

    def test_no_config_is_graceful(self):
        rc = fz._ensure_hardhat_foundry_plugin(self.dir)   # no hardhat.config.* present
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
