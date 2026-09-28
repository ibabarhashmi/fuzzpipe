"""Legacy render API shim over fuzzpipe.verdict.reproducer + harm.

Preserves the original cli/render.py contract: type-aware Solidity literal
+ call rendering plus harm-assertion detection. New code should use
fuzzpipe.verdict.reproducer and fuzzpipe.verdict.harm directly.
"""
from __future__ import annotations

from fuzzpipe.verdict.reproducer import parse_types, sol_scalar, render_call
from fuzzpipe.verdict.harm import (
    asserts_harm,
    _ASSERT_CMP,
    _ASSERT_BOOL,
    _CMP_OPS,
    _LIT_RE,
    _strip_comments,
    _all_call_args,
    _split_top,
    _is_literal,
    _substantive_cmp,
    _split_on_cmp,
    _cond_substantive,
)
from fuzzpipe.verdict.reproducer import _tuple_parts

__all__ = [
    "parse_types", "sol_scalar", "render_call", "asserts_harm",
]
