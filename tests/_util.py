"""Shared helpers for the fuzzpipe regression suite (stdlib only)."""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "cli"
FUZZPIPE = CLI / "fuzzpipe"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLES = ROOT / "examples"

# make the cli/ modules importable by the unit tests
if str(CLI) not in sys.path:
    sys.path.insert(0, str(CLI))

_FUZZPIPE_MOD = None


def load_fuzzpipe():
    """Import the extensionless `cli/fuzzpipe` script as a module so unit tests can call its
    internal helpers directly (it has no .py suffix, so a normal import won't find it)."""
    global _FUZZPIPE_MOD
    if _FUZZPIPE_MOD is None:
        spec = importlib.util.spec_from_loader(
            "fuzzpipe_mod", importlib.machinery.SourceFileLoader("fuzzpipe_mod", str(FUZZPIPE)))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _FUZZPIPE_MOD = mod
    return _FUZZPIPE_MOD


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
