"""Q6: version-tolerant Medusa parser — schema variants parse or WARN, never crash, never
silently drop a whole sequence."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _util  # noqa: F401
import medusa_parse


class TestMedusaParse(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fuzzpipe_mp_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, obj):
        (self.tmp / name).write_text(json.dumps(obj))

    def test_current_schema_with_bool(self):
        self._write("a.json", [{"call": {"dataAbiValues": {
            "methodSignature": "f(bool)", "inputValues": [True]}}}])
        seqs, warns = medusa_parse.failing_sequences(self.tmp)
        self.assertEqual(len(seqs), 1)
        step = seqs[0][1][0]
        self.assertEqual(step["method"], "f")
        self.assertEqual(step["types"], ["bool"])
        self.assertEqual(step["values"], [True])

    def test_alt_key_method_name(self):
        # older/alt shape: method name under `method`, values under `arguments`
        self._write("b.json", [{"call": {"method": "g(uint256)", "arguments": [7]}}])
        seqs, warns = medusa_parse.failing_sequences(self.tmp)
        self.assertEqual(len(seqs), 1)
        self.assertEqual(seqs[0][1][0]["method"], "g")

    def test_wrapped_call_sequence(self):
        self._write("c.json", {"callSequence": [
            {"call": {"dataAbiValues": {"methodSignature": "h()", "inputValues": []}}}]})
        seqs, warns = medusa_parse.failing_sequences(self.tmp)
        self.assertEqual(len(seqs), 1)

    def test_malformed_warns_not_crashes(self):
        self._write("d.json", [{"call": {"dataAbiValues": {"inputValues": [1]}}}])  # no signature
        seqs, warns = medusa_parse.failing_sequences(self.tmp)
        self.assertEqual(seqs, [])
        self.assertTrue(any("no method signature" in w for w in warns))

    def test_arity_mismatch_warns(self):
        self._write("e.json", [{"call": {"dataAbiValues": {
            "methodSignature": "f(bool,uint256)", "inputValues": [True]}}}])
        seqs, warns = medusa_parse.failing_sequences(self.tmp)
        self.assertEqual(len(seqs), 1)   # still usable, best-effort
        self.assertTrue(any("arity mismatch" in w for w in warns))

    def test_unreadable_json_warns_not_crashes(self):
        (self.tmp / "f.json").write_text("{not json")
        seqs, warns = medusa_parse.failing_sequences(self.tmp)
        self.assertTrue(any("could not read" in w for w in warns))


if __name__ == "__main__":
    unittest.main()
