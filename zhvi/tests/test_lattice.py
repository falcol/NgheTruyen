"""Tests cho lattice VietPhrase (thiet ke muc 11.2/39)."""
from __future__ import annotations

from pathlib import Path

import pytest

from zhvi.vietphrase.layers import Layer
from zhvi.vietphrase.lattice import Edge, best_paths, render, vp_plan
from zhvi.vietphrase.loader import TrieNode, Dictionary, _insert, load_dictionary

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"


def mini_dict(entries: list[tuple[str, str, Layer]]) -> Dictionary:
    root = TrieNode()
    for i, (zh, vi, layer) in enumerate(entries):
        _insert(root, zh, vi, (int(layer), float(layer) * 10, i), "CONTEXTUAL")
    return Dictionary(root=root, trad_simp={}, entry_count=len(entries), fingerprint="mini")


def test_overlapping_matches_kept():
    dic = mini_dict([
        ("天地", "thiên địa", Layer.BASE_MULTI),
        ("天", "thiên", Layer.BASE_SINGLE),
        ("地", "địa", Layer.BASE_SINGLE),
    ])
    paths = best_paths(dic, "天地", k=4)
    # ca hai duong: 1 edge (thiên địa) va 2 edge (thiên + địa)
    assert len(paths) >= 2
    edge_counts = sorted(len(p.edges) for p in paths)
    assert edge_counts[0] == 1 and edge_counts[-1] == 2


def test_multi_char_beats_single_fallback():
    dic = mini_dict([
        ("天地", "thiên địa", Layer.BASE_MULTI),
        ("天", "thiên", Layer.BASE_SINGLE),
        ("地", "địa", Layer.BASE_SINGLE),
    ])
    draft = vp_plan(dic, "天地")
    assert draft.text == "Thiên địa"  # render hoa dau cau (QuickTrans)
    assert draft.single_char_ratio == 0.0


def test_fragmentation_penalty():
    """3 single-char lien ke bi phat nang hon 1 phrase dai."""
    dic = mini_dict([
        ("ABC", "abc", Layer.BASE_MULTI),
        ("A", "a", Layer.BASE_SINGLE),
        ("B", "b", Layer.BASE_SINGLE),
        ("C", "c", Layer.BASE_SINGLE),
    ])
    # CJK moi duoc tinh; dung CJK that
    dic2 = mini_dict([
        ("天地人", "thiên địa nhân", Layer.BASE_MULTI),
        ("天", "thiên", Layer.BASE_SINGLE),
        ("地", "địa", Layer.BASE_SINGLE),
        ("人", "nhân", Layer.BASE_SINGLE),
    ])
    draft = vp_plan(dic2, "天地人")
    assert draft.text == "Thiên địa nhân"


def test_layer_precedence_manual_wins():
    dic = mini_dict([
        ("道", "đạo-MANUAL", Layer.BOOK_MANUAL),
        ("道", "đạo-BASE", Layer.BASE_SINGLE),
    ])
    draft = vp_plan(dic, "道")
    assert "MANUAL" in draft.text


def test_unknown_span_tracked():
    dic = mini_dict([("天", "thiên", Layer.BASE_SINGLE)])
    draft = vp_plan(dic, "天鬼")
    assert len(draft.unknown_spans) == 1
    assert draft.unknown_spans[0].source == "鬼"
    assert "UNKNOWN_SPAN" in draft.warnings


def test_particle_dropped():
    dic = mini_dict([
        ("的", "đích", Layer.BASE_SINGLE),
        ("天", "thiên", Layer.BASE_SINGLE),
    ])
    draft = vp_plan(dic, "天的")
    assert draft.text == "Thiên"  # nhu QuickTrans boc particle


def test_literal_passthrough_and_punct():
    dic = mini_dict([("天", "thiên", Layer.BASE_SINGLE)])
    draft = vp_plan(dic, "天，X。")
    assert "thiên" in draft.text.lower()
    assert "," in draft.text and "." in draft.text  # punct map


def test_render_capitalize():
    dic = mini_dict([("天", "thiên", Layer.BASE_SINGLE)])
    draft = vp_plan(dic, "天。tiếp theo。天")
    # sau dau cham + cach: chu thuong -> hoa
    assert "Tiếp" in draft.text


def test_margin_and_entropy():
    dic = mini_dict([
        ("天地", "thien-dia-A", Layer.BASE_MULTI),
        ("天地", "thien-dia-B", Layer.BASE_MULTI),
    ])
    draft = vp_plan(dic, "天地")
    assert draft.lattice_entropy >= 0.0
    assert isinstance(draft.lattice_margin, float)


def test_empty_text():
    dic = mini_dict([])
    draft = vp_plan(dic, "   ")
    assert draft.text == "   "


# ---- tu dien that ----

@pytest.fixture(scope="module")
def real_dict():
    if not DICT_DIR.is_dir():
        pytest.skip("khong co thu muc tu dien nen")
    return load_dictionary(DICT_DIR)


def test_real_dict_loads(real_dict):
    assert real_dict.entry_count > 100_000
    assert len(real_dict.fingerprint) == 64


def test_real_dict_names(real_dict):
    draft = vp_plan(real_dict, "凌天")
    assert "Lăng Thiên" in draft.text


def test_real_dict_phrase(real_dict):
    draft = vp_plan(real_dict, "混沌道體")
    # hoac 混沌道体 simplified — ca hai key phai co
    assert "hỗn độn" in draft.text.lower()


def test_render_join_rules():
    edges = [
        Edge(0, 1, "thiên", (2, 1.0, 0), "CONTEXTUAL", None, 0),
        Edge(1, 2, "địa", (2, 1.0, 1), "CONTEXTUAL", None, 0),
    ]
    assert render(edges) == "Thiên địa"  # hoa dau cau


# ---- rule chong lap (muc 11.2 + QA) ----

def test_collapse_target_artifact():
    """Hai span nguon khac nhau cung map ve 'có chút' (khong lap nguon) -> giu 1."""
    dic = mini_dict([
        ("有些", "có chút", Layer.BASE_MULTI),
        ("有点儿", "có chút", Layer.BASE_MULTI),
        ("担心", "lo lắng", Layer.BASE_MULTI),
    ])
    draft = vp_plan(dic, "有些有点儿担心")
    assert draft.text == "Có chút lo lắng"
    assert any(w.startswith("REPETITION_COLLAPSED") for w in draft.warnings)


def test_keep_source_reduplication():
    """Nguon lap lai that (磨炼磨炼) -> giu nhip lap, khong collapse."""
    dic = mini_dict([
        ("磨炼", "ma luyện", Layer.BASE_MULTI),
        ("心性", "tâm tính", Layer.BASE_MULTI),
    ])
    draft = vp_plan(dic, "磨炼磨炼心性")
    assert draft.text == "Ma luyện ma luyện tâm tính"
    assert not any(w.startswith("REPETITION_COLLAPSED") for w in draft.warnings)


def test_collapse_prefix_overlap():
    """Target sau bat dau bang target truoc ('đã' + 'đã bị') -> loai edge dau."""
    dic = mini_dict([
        ("已经", "đã", Layer.BASE_MULTI),
        ("被擒", "đã bị bắt", Layer.BASE_MULTI),
    ])
    draft = vp_plan(dic, "已经被擒")
    assert draft.text == "Đã bị bắt"


def test_collapse_disabled_by_flag():
    dic = mini_dict([
        ("有些", "có chút", Layer.BASE_MULTI),
        ("担心", "lo lắng", Layer.BASE_MULTI),
    ])
    draft = vp_plan(dic, "有些有些担心", collapse_reps=False)
    assert draft.text == "Có chút có chút lo lắng"
