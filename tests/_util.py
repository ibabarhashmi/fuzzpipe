"""Shared helpers for the fuzzpipe regression suite (stdlib only)."""
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "cli"
FUZZPIPE = CLI / "fuzzpipe"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLES = ROOT / "examples"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# legacy cli/ modules (proc, render, ir, verdict, medusa_parse, handlers shims)
if str(CLI) not in sys.path:
    sys.path.insert(0, str(CLI))


def have(tool):
    return shutil.which(tool) is not None


def run_cli(args, env=None, cwd=None, timeout=600):
    """Invoke the real fuzzpipe CLI as a subprocess. Returns CompletedProcess."""
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(FUZZPIPE)] + list(args),
                          capture_output=True, text=True, env=e, cwd=cwd, timeout=timeout)


def copy_fixture(name):
    """Copy a fixture project into a fresh temp dir. Caller removes it."""
    dst = Path(tempfile.mkdtemp(prefix="fuzzpipe_" + name + "_"))
    shutil.copytree(FIXTURES / name, dst, dirs_exist_ok=True)
    return dst


_FUZZPIPE_MOD = None


def load_fuzzpipe():
    """Compatibility shim exposing legacy cli/fuzzpipe internals from new package layout."""
    global _FUZZPIPE_MOD
    if _FUZZPIPE_MOD is not None:
        return _FUZZPIPE_MOD
    mod = types.ModuleType("fuzzpipe_mod")
    # surface scanner + priv mods (load submodule by path: package __init__ shadows name with function)
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_ca_mod", str(ROOT / "fuzzpipe" / "ir" / "coverage_audit.py"))
    _ca_mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_ca_mod)
    mod._iter_functions = _iter_functions_shim
    mod._PRIV_MODS = _ca_mod._PRIV_MODS
    # classify
    from fuzzpipe.engines.adapters import base as _base
    mod._classify_rc = _base.classify_rc
    # materiality helpers
    from fuzzpipe.cli.commands import materiality as _mat
    mod._parse_amount = _mat._parse_amount
    mod._log_grid = _mat._log_grid
    mod._test_broke = _mat._test_broke
    mod._materiality_verdict = _mat._materiality_verdict
    # sharding / triage helpers
    from fuzzpipe.engines import config as _cfg
    mod._shard_has_breaks = _cfg._shard_has_breaks
    mod._stage_medusa_config_for_invariant = _cfg.stage_shard_config
    # medusa_results_dirs + collect live in triage command; reimplement thin here
    def _medusa_results_dirs(target):
        base = _cfg.state_dir(target) / "corpus" / "medusa"
        dirs = []
        flat = base / "test_results"
        if flat.is_dir():
            dirs.append(flat)
        if base.is_dir():
            for shard in sorted(base.iterdir()):
                if shard.is_dir() and shard.name != "test_results":
                    tr = shard / "test_results"
                    if tr.is_dir():
                        dirs.append(tr)
        return dirs
    mod._medusa_results_dirs = _medusa_results_dirs
    def _collect_medusa_sequences(target):
        import fuzzpipe.medusa_parse as _mp
        sequences, warnings = [], []
        for d in _medusa_results_dirs(target):
            seqs, warns = _mp.failing_sequences(d)
            shard = d.parent.name if d.parent.name != "medusa" else None
            for fname, seq in seqs:
                tag = f"{shard}::{fname}" if shard else fname
                sequences.append((tag, seq))
            warnings += warns
        return sequences, warnings
    mod._collect_medusa_sequences = _collect_medusa_sequences
    # scaffold helper (load by path: package __init__ shadows submodule with function)
    _scaf_spec = _ilu.spec_from_file_location("_scaf_mod", str(ROOT / "fuzzpipe" / "harness" / "scaffold.py"))
    _scaf_mod = _ilu.module_from_spec(_scaf_spec)
    _scaf_spec.loader.exec_module(_scaf_mod)
    mod._ensure_hardhat_foundry_plugin = _scaf_mod._ensure_hardhat_foundry_plugin
    _FUZZPIPE_MOD = mod
    return mod


def _iter_functions_shim(text):
    """Yield (name, modifier_tail) mirroring legacy regex scanner with balanced parens."""
    import re as _re
    _FUNC_HEAD_RE = _re.compile(r"\bfunction\s+(\w+)\s*\(")
    for m in _FUNC_HEAD_RE.finditer(text):
        name = m.group(1)
        depth, j = 0, m.end() - 1
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        k, tail = j + 1, []
        while k < len(text) and text[k] not in "{;":
            tail.append(text[k]); k += 1
        yield name, "".join(tail)