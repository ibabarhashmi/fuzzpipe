"""Q4 (single support-matrix source of truth) + R1 (no env doc/code drift).

Both are 'the docs and the code disagree' defects. These tests fail if any live doc/config/code
file re-introduces a contradiction, or if a FUZZPIPE_* env var is read by code but undocumented
(or documented but never read)."""
import re
import unittest
from pathlib import Path

import _util

ROOT = _util.ROOT
SKILL = ROOT / "skill" / "fuzzpipe-fuzzing" / "SKILL.md"
README = ROOT / "README.md"

# Files that are SUPPOSED to state runtime support. README is intentionally excluded: it carries
# the change narrative (which quotes old behavior), so it is not a support-matrix source.
LIVE_SUPPORT_FILES = [
    ROOT / "cli" / "fuzzpipe",
    ROOT / "templates" / "fuzzpipe.config.json",
    SKILL,
] + list((ROOT / "guidance").glob("*.md"))

# v0.2's self-contradiction: config/comment said HH3 unsupported while README/doctor said supported.
FORBIDDEN = [
    re.compile(r"does not support .{0,10}v3", re.I),
    re.compile(r"Hardhat.{0,30}must be v2", re.I),
    re.compile(r"Hardhat ?3 is NOT supported", re.I),
    re.compile(r"crytic-compile does not support", re.I),
]


class TestSupportMatrixSingleSource(unittest.TestCase):
    def test_no_live_file_contradicts_hh3_support(self):
        for f in LIVE_SUPPORT_FILES:
            if not f.exists():
                continue
            text = f.read_text()
            for rx in FORBIDDEN:
                self.assertIsNone(rx.search(text),
                                  "%s contradicts the Hardhat v2 AND v3 support matrix (Q4): %r"
                                  % (f.name, rx.pattern))

    def test_canonical_statement_present(self):
        self.assertIn("Hardhat v2 AND v3", (ROOT / "cli" / "fuzzpipe").read_text(),
                      "the single support-matrix source of truth is missing from the CLI")


def _env_tokens(text):
    return set(re.findall(r"FUZZPIPE_[A-Z_]+", text))


class TestEnvNoDrift(unittest.TestCase):
    def test_code_and_docs_agree_on_env_vars(self):
        code_text = "\n".join(p.read_text() for p in
                              [ROOT / "cli" / "fuzzpipe"] + list((ROOT / "cli").glob("*.py")))
        code_env = _env_tokens(code_text)
        doc_env = _env_tokens(SKILL.read_text()) | _env_tokens(README.read_text() if README.exists() else "")
        self.assertTrue(code_env, "no FUZZPIPE_* env vars found in code")
        self.assertEqual(code_env, doc_env,
                         "env drift (R1): code=%s docs=%s" % (sorted(code_env), sorted(doc_env)))


if __name__ == "__main__":
    unittest.main()
