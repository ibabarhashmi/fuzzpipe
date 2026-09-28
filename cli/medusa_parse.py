"""Legacy medusa_parse API shim over fuzzpipe.medusa_parse.

Preserves the original cli/medusa_parse.py contract. New code should use
fuzzpipe.medusa_parse directly.
"""
from __future__ import annotations

from fuzzpipe.medusa_parse import (
    failing_sequences,
    parse_file,
    _first,
    _extract_step,
)

__all__ = ["failing_sequences", "parse_file"]
