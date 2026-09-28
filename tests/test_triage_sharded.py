"""
test_triage_sharded.py — the per-invariant corpus-path fix (B1).

v2.1 bug: a per-invariant (sharded) medusa run wrote failing sequences under
`.fuzzpipe/corpus/medusa/<INV>/test_results`, but triage only ever read the flat
`.fuzzpipe/corpus/medusa/test_results` — so a multi-invariant run silently found NOTHING.
These guard that triage now collects from the flat dir AND every shard dir, and attributes
each sequence to the shard (invariant) it came from.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _util import load_fuzzpipe

fz = load_fuzzpipe()

# a minimal current-schema medusa failing sequence
_SEQ = {"callSequence": [
    {"call": {"dataAbiValues": {"methodSignature": "handler_deposit(uint256)",
                                "inputValues": [42]}}}]}


class TestShardedCollection(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fuzzpipe_shard_"))
        self.base = self.dir / ".fuzzpipe" / "corpus" / "medusa"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel):
        p = self.base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_SEQ))

    def test_reads_flat_dir(self):
        self._write("test_results/seq1.json")
        seqs, _ = fz._collect_medusa_sequences(self.dir)
        self.assertEqual(len(seqs), 1)
        self.assertNotIn("::", seqs[0][0])   # flat sequences are not shard-tagged

    def test_reads_shard_dirs(self):
        self._write("INV-SOLVENCY/test_results/seq1.json")
        self._write("INV-ROUNDTRIP/test_results/seq1.json")
        seqs, _ = fz._collect_medusa_sequences(self.dir)
        self.assertEqual(len(seqs), 2)
        tags = sorted(name for name, _ in seqs)
        self.assertTrue(any(t.startswith("INV-SOLVENCY::") for t in tags))
        self.assertTrue(any(t.startswith("INV-ROUNDTRIP::") for t in tags))

    def test_reads_flat_and_shards_together(self):
        self._write("test_results/seq1.json")
        self._write("INV-SOLVENCY/test_results/seq1.json")
        dirs = fz._medusa_results_dirs(self.dir)
        self.assertEqual(len(dirs), 2)
        seqs, _ = fz._collect_medusa_sequences(self.dir)
        self.assertEqual(len(seqs), 2)

    def test_no_artifacts_is_empty_not_crash(self):
        seqs, warns = fz._collect_medusa_sequences(self.dir)
        self.assertEqual(seqs, [])


if __name__ == "__main__":
    unittest.main()
