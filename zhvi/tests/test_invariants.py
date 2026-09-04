"""Tests cho invariant gate (thiet ke muc 17/39)."""
from __future__ import annotations

from zhvi.quality.invariants import run_invariants


def test_clean_output_passes():
    r = run_invariants(source="凌天看着前方", output="Lăng Thiên nhìn phía trước")
    assert r.ok
    assert r.errors == ()


def test_empty_output_fails():
    r = run_invariants(source="有内容", output="")
    assert not r.ok
    assert "EMPTY_OUTPUT" in r.errors


def test_leftover_cjk_fails():
    r = run_invariants(source="天", output="Thiên 天")
    assert not r.ok
    assert "LEFTOVER_CJK:1" in r.errors


def test_cjk_allowlist_passes():
    r = run_invariants(source="第三章", output="Chương 3", cjk_allowlist={"第", "章"})
    assert r.ok


def test_unbalanced_quote_fails():
    r = run_invariants(source="他说“你好", output="Hắn nói “chào")
    assert not r.ok
    assert any(e.startswith("UNBALANCED_QUOTE") for e in r.errors)


def test_guarded_term_missing_fails():
    r = run_invariants(source="万宝宗", output="Vạn Bảo", guarded_terms={"万宝宗": "Vạn Bảo Tông"})
    assert not r.ok
    assert "GUARDED_TERM_MISSING:万宝宗" in r.errors


def test_guarded_term_present_passes():
    r = run_invariants(source="万宝宗", output="Vạn Bảo Tông", guarded_terms={"万宝宗": "Vạn Bảo Tông"})
    assert r.ok


def test_semantic_check_not_false_positive():
    """Source chu Han, output tieng Viet — khong bat 'mat so/don vi' tu character."""
    r = run_invariants(source="三万年", output="ba vạn năm")
    assert r.ok  # '三' (chu Han) khong bi coi la digit mat
