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


def test_vp_plan_beam1_same_text():
    """beam<=1 bo lattice DP; ban dich giong beam=4."""
    dic = mini_dict([
        ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
        ("已经", "đã", Layer.BASE_MULTI),
        ("到", "đến", Layer.BASE_SINGLE),
        ("了", "đã", Layer.BASE_SINGLE),
    ])
    src = "凌天已经到了"
    assert vp_plan(dic, src, beam=1).text == vp_plan(dic, src, beam=4).text


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


# ---- AD-9: duong dich deterministic (story 1.4) ----

def test_ad9_same_layer_entry_id_tiebreak():
    """Cung (layer, trust), 2 target -> tie-break entry_id lexical, khong phu thuoc thu tu nap."""
    dic_a = mini_dict([
        ("青龙", "Alpha", Layer.GLOBAL_MANUAL),
        ("青龙", "Beta", Layer.GLOBAL_MANUAL),
    ])
    dic_b = mini_dict([  # dao thu tu nap
        ("青龙", "Beta", Layer.GLOBAL_MANUAL),
        ("青龙", "Alpha", Layer.GLOBAL_MANUAL),
    ])
    out_a = vp_plan(dic_a, "青龙").text
    out_b = vp_plan(dic_b, "青龙").text
    assert out_a == out_b == "Alpha"


def test_ad9_entry_version_id_unique_per_target():
    """2 entry cung (layer, span) khac target -> entry_version_id khac nhau.

    entry_version_id la dinh danh entry (AD-9 tie-break dung truong nay) —
    trung id khi khac target la sai voi data-model entry_versions.
    """
    from zhvi.vietphrase.lattice import _find_edges

    dic = mini_dict([
        ("青龙", "Alpha", Layer.GLOBAL_MANUAL),
        ("青龙", "Beta", Layer.GLOBAL_MANUAL),
    ])
    edges = [e for e in _find_edges(dic.root, "青龙", 0) if e.end == 2]
    ids = [e.entry_version_id for e in edges]
    assert len(ids) == 2
    assert len(set(ids)) == 2  # id phai duy nhat moi entry


def test_ad9_layer_precedence_beats_entry_id():
    """Layer cao hon thang tuyet doi du entry_id lexical lon hon."""
    dic = mini_dict([
        ("青龙", "zzz-base", Layer.BASE_MULTI),
        ("青龙", "mmm-manual", Layer.BOOK_MANUAL),
    ])
    assert vp_plan(dic, "青龙").text == "Mmm-manual"


def test_ad9_literal_beats_pattern_same_layer():
    """Pattern rule va literal cung do dai, cung (layer, trust) -> literal thang."""
    from zhvi.vietphrase.patterns import build_pattern_index, compile_rule

    dic = mini_dict([
        ("天", "Thiên", Layer.BASE_MULTI),  # trust 20 -> {n} entity ok
        ("小天", "Tiểu Thiên Literal", Layer.BASE_MULTI),
    ])
    rule = compile_rule("小{n}", "tiểu {1} pattern", (int(Layer.BASE_MULTI), 20.0, 0), "CONTEXTUAL")
    dic.patterns = build_pattern_index([rule])
    draft = vp_plan(dic, "小天")
    assert "Literal" in draft.text  # literal thang pattern cung do dai


def test_ad9_trad_source_kept_in_trace():
    """Span match bang key giản thể nhung trace luu source GOC (phồn thể)."""
    dic = mini_dict([("龙", "long", Layer.BASE_MULTI)])
    dic.trad_simp = {"龍": "龙"}
    draft = vp_plan(dic, "龍")
    assert draft.text == "Long"
    assert draft.spans[0].source == "龍"


def test_ad9_load_order_independence_real_files(tmp_path):
    """Hai dict dir giong nhau chi khac thu tu dong cung key -> cung output."""
    def make_dict_dir(lines: list[str]) -> Path:
        d = tmp_path / ("d" + str(abs(hash(tuple(lines))) % 10**8))
        d.mkdir()
        (d / "QualityOverrides.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return d

    dir_a = make_dict_dir(["凌天=Alpha", "凌天=Beta"])
    dir_b = make_dict_dir(["凌天=Beta", "凌天=Alpha"])
    dic_a = load_dictionary(dir_a)
    dic_b = load_dictionary(dir_b)
    assert vp_plan(dic_a, "凌天").text == vp_plan(dic_b, "凌天").text == "Alpha"


def test_generic_phrase_does_not_swallow_inner_name(tmp_path):
    """QT prioritizedName: VP '叫张三' khong duoc nuot Names '张三丰' lech 1 chu."""
    d = tmp_path / "name-guard"
    d.mkdir()
    (d / "VietPhrase_1.txt").write_text(
        "叫张三=gọi trương tam\n叫=gọi\n", encoding="utf-8"
    )
    (d / "Names.txt").write_text("张三丰=Trương Tam Phong\n", encoding="utf-8")
    (d / "ChinesePhienAmWords.txt").write_text(
        "丰=phong\n张=trương\n三=tam\n", encoding="utf-8"
    )
    draft = vp_plan(load_dictionary(d), "叫张三丰")
    assert draft.text == "Gọi Trương Tam Phong"


def test_name_span_kept_when_shorter_name_inside(tmp_path):
    """Cụm chinh no la ten -> giu, khong nhường ten ngan hon ben trong."""
    d = tmp_path / "name-self"
    d.mkdir()
    (d / "Names.txt").write_text(
        "张三丰=Trương Tam Phong\n三丰=Tam Phong\n", encoding="utf-8"
    )
    (d / "ChinesePhienAmWords.txt").write_text(
        "张=trương\n三=tam\n丰=phong\n", encoding="utf-8"
    )
    draft = vp_plan(load_dictionary(d), "张三丰")
    assert draft.text == "Trương Tam Phong"


def test_glossary_name_not_swallowed_by_generic(tmp_path):
    """glossary.manual (BOOK_MANUAL) duoc bao ve giong Names.txt."""
    d = tmp_path / "gloss-guard"
    d.mkdir()
    (d / "VietPhrase_1.txt").write_text("看凌=nhìn lăng\n看=nhìn\n", encoding="utf-8")
    (d / "ChinesePhienAmWords.txt").write_text(
        "凌=lăng\n天=thiên\n", encoding="utf-8"
    )
    gloss = tmp_path / "glossary.manual.tsv"
    gloss.write_text("凌天=Lăng Thiên\n", encoding="utf-8")
    draft = vp_plan(load_dictionary(d, manual_glossary=gloss), "看凌天")
    assert draft.text == "Nhìn Lăng Thiên"


def test_contained_names_file_does_not_break_collocation(tmp_path):
    """Names.txt 2-chu nam gon trong VP dai hon -> giu collocation."""
    d = tmp_path / "contained-names"
    d.mkdir()
    (d / "VietPhrase_1.txt").write_text(
        "得天地厚爱=được thiên địa hậu ái\n", encoding="utf-8"
    )
    (d / "Names.txt").write_text("天地=Thiên Địa\n", encoding="utf-8")
    (d / "ChinesePhienAmWords.txt").write_text(
        "得=đắc\n天=thiên\n地=địa\n厚=hậu\n爱=ái\n", encoding="utf-8"
    )
    draft = vp_plan(load_dictionary(d), "得天地厚爱")
    assert draft.text == "Được thiên địa hậu ái"


def test_contained_glossary_still_protected(tmp_path):
    """glossary nam gon trong VP dai hon van duoc tach ra (user khai bao)."""
    d = tmp_path / "contained-gloss"
    d.mkdir()
    (d / "VietPhrase_1.txt").write_text(
        "看凌天=nhìn lăng thiên\n看=nhìn\n", encoding="utf-8"
    )
    (d / "ChinesePhienAmWords.txt").write_text(
        "凌=lăng\n天=thiên\n", encoding="utf-8"
    )
    gloss = tmp_path / "glossary.manual.tsv"
    gloss.write_text("凌天=Lăng Thiên\n", encoding="utf-8")
    draft = vp_plan(load_dictionary(d, manual_glossary=gloss), "看凌天")
    assert draft.text == "Nhìn Lăng Thiên"


def test_two_char_names_file_straddle_ignored(tmp_path):
    """Names 2-chu overlapping 1 ky tu (汉语 vs 大汉) khong cat collocation."""
    d = tmp_path / "straddle"
    d.mkdir()
    (d / "VietPhrase_1.txt").write_text("大汉=đại hán\n", encoding="utf-8")
    (d / "Names.txt").write_text("汉语=Hán ngữ\n", encoding="utf-8")
    (d / "ChinesePhienAmWords.txt").write_text("又=hựu\n", encoding="utf-8")
    draft = vp_plan(load_dictionary(d), "大汉又")
    assert draft.text == "Đại hán hựu"


def test_custom_name_not_split_by_straddle_names(tmp_path):
    """Custom 凌天 khong bi Names 天神 cat thanh Lăng + Thiên Thần."""
    d = tmp_path / "custom-span"
    d.mkdir()
    (d / "Custom.txt").write_text("凌天=Lăng Thiên\n", encoding="utf-8")
    (d / "Names.txt").write_text("天神=Thiên Thần\n", encoding="utf-8")
    (d / "VietPhrase_1.txt").write_text("神尊=thần tôn\n", encoding="utf-8")
    draft = vp_plan(load_dictionary(d), "凌天神尊")
    assert draft.text == "Lăng Thiên thần tôn"
