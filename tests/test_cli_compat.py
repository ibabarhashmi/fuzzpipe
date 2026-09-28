# tests/test_cli_compat.py
import subprocess
import sys
def test_help_lists_subcommands():
    r = subprocess.run([sys.executable,"-m","fuzzpipe.cli.app","--help"], capture_output=True, text=True)
    out = r.stdout + r.stderr
    for cmd in ["doctor","init","scaffold","build","gen-handlers","run","triage","verify","materiality","ir","coverage","status","selftest"]:
        assert cmd in out