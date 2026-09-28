# tests/test_verdict_async.py
import pytest
from fuzzpipe.verdict.gate import reproduces_specific_break
from fuzzpipe.verdict.harm import asserts_harm
def test_marker_required():
    assert reproduces_specific_break("[FAIL] test_repro", "INV-X") is False
    assert reproduces_specific_break("[FAIL] test_repro INV-X", "INV-X") is True
    assert reproduces_specific_break("[PASS] test_repro INV-X", "INV-X") is False
def test_trivial_harm_rejected():
    assert asserts_harm("assertEq(1, 1);") is False
    assert asserts_harm("assertTrue(true);") is False
    assert asserts_harm("// INV-X comment only") is False
def test_real_harm_accepted():
    assert asserts_harm('assertGt(victimBalanceAfter, victimBalanceBefore);') is True