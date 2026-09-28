from fuzzpipe.proc.runner import RC_MISSING, RC_TIMEOUT
from typing import Optional


def classify_rc(engine: str, rc: int, budget_s: int) -> str:
    if rc == RC_TIMEOUT:
        return "clean"
    if rc == RC_MISSING:
        return "untested"
    return "clean" if rc == 0 else "break_or_error"