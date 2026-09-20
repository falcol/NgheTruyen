"""Mau {p}/{v}, sense chu ben phai, loai cau — khong pha AD-9 longest-match."""
from __future__ import annotations

from pathlib import Path

from zhvi.vietphrase.layers import Layer
from zhvi.vietphrase.lattice import greedy_path, vp_plan
from zhvi.vietphrase.loader import Dictionary, TrieNode, _insert, parse_dict_line
from zhvi.vietphrase.patterns import VERBS, build_pattern_index, compile_rule
from zhvi.vietphrase.sense import clause_is_question

_CTX = Path(__file__).resolve().parents[2] / "crawler/vietphrase/dicts/ContextPatterns.txt"


def context_rules() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in _CTX.read_text(encoding="utf-8").splitlines():
        parsed = parse_dict_line(line)
        if parsed and "{" in parsed[0]:
            out.append(parsed)
    return out


def mini(entries: list[tuple[str, str, Layer]], rules: list[tuple[str, str]] | None = None) -> Dictionary:
    root = TrieNode()
    for i, entry in enumerate(entries):
        zh, vi, layer = entry[0], entry[1], entry[2]
        trust = entry[3] if len(entry) > 3 else float(layer) * 10
        _insert(root, zh, vi, (int(layer), trust, i), "CONTEXTUAL")
    compiled = []
    for zh, vi in rules or []:
        r = compile_rule(zh, vi, (int(Layer.GLOBAL_MANUAL), 25.0, 0), "PREFERRED")
        assert r is not None
        compiled.append(r)
    return Dictionary(
        root=root,
        trad_simp={},
        entry_count=len(entries),
        fingerprint="mini-ctx",
        patterns=build_pattern_index(compiled),
    )


def test_zhuoshang_inverts_noun():
    dic = mini(
        [
            ("拿起", "cầm lấy", Layer.BASE_MULTI),
            ("幼儿书籍", "sách trẻ em", Layer.BASE_MULTI),
            ("桌上的", "trên bàn", Layer.GLOBAL_MANUAL),
            ("就", "liền", Layer.BASE_SINGLE),
            ("看", "xem", Layer.BASE_SINGLE),
            ("了", "", Layer.BASE_SINGLE),
            ("起来", "lên", Layer.BASE_MULTI),
        ],
        [("桌上的{p}", "{p} trên bàn")],
    )
    draft = vp_plan(dic, "拿起桌上的幼儿书籍就看了起来")
    assert "sách trẻ em trên bàn" in draft.text
    assert "trên bàn sách" not in draft.text


def test_yiba_verb_pattern():
    dic = mini(
        [
            ("一把", "một thanh", Layer.BASE_MULTI),
            ("拽住", "níu lấy", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
        ],
        [("一把{v}", "một cái {v}")],
    )
    draft = vp_plan(dic, "一把拽住凌天")
    low = draft.text.lower()
    assert "cái" in low
    assert "thanh" not in low


def test_yiba_reng_not_thanh():
    dic = mini(
        [
            ("一把", "một thanh", Layer.BASE_MULTI),
            ("扔掉", "ném đi", Layer.BASE_MULTI),
        ],
        [("一把{v}", "một cái {v}")],
    )
    draft = vp_plan(dic, "一把扔掉")
    low = draft.text.lower()
    assert "cái" in low
    assert "thanh" not in low


def test_yiba_weapon_keeps_thanh():
    dic = mini(
        [
            ("一把", "một thanh", Layer.BASE_MULTI),
            ("剑", "kiếm", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "一把剑")
    assert "thanh" in draft.text.lower()


def test_sense_dui_pronoun():
    dic = mini(
        [
            ("对", "đúng", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "对他")
    assert "đối" in draft.text.lower() or "Đối" in draft.text


def test_sense_duiziji_drops_voi():
    dic = mini([("对自己", "đối với mình", Layer.BASE_MULTI)])
    draft = vp_plan(dic, "对自己")
    low = draft.text.lower()
    assert "đối mình" in low
    assert "với" not in low


def test_sense_doudui_ziji():
    dic = mini(
        [
            ("都对", "đều đúng", Layer.BASE_MULTI),
            ("自己", "mình", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "都对自己")
    low = draft.text.lower()
    assert "đều đối" in low
    assert "đúng" not in low


def test_sense_de_houai():
    dic = mini(
        [
            ("得", "đến", Layer.BASE_SINGLE),
            ("天地", "thiên địa", Layer.BASE_MULTI),
            ("厚爱", "hậu ái", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "得天地厚爱")
    assert "được" in draft.text or "Được" in draft.text


def test_sense_duoshao_question():
    dic = mini(
        [
            ("多少", "nhiều ít", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
        ]
    )
    q = vp_plan(dic, "多少人？")
    nq = vp_plan(dic, "多少人。")
    assert "bao nhiêu" in q.text.lower() or "Bao nhiêu" in q.text
    assert "nhiều ít" in nq.text.lower() or "Nhiều ít" in nq.text


def test_sense_dao_before_quote():
    dic = mini([("道", "đạo", Layer.BASE_SINGLE)])
    draft = vp_plan(dic, "道：「")
    assert "nói" in draft.text.lower() or "Nói" in draft.text


def test_sense_tun_compound_thon():
    dic = mini(
        [
            ("虚古", "hư cổ", Layer.BASE_MULTI),
            ("吞", "nuốt", Layer.BASE_MULTI),
            ("灵", "linh", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "虚古吞灵")
    low = draft.text.lower()
    assert "thôn linh" in low
    assert "nuốt" not in low


def test_sense_tun_verb_keeps_nuot():
    dic = mini(
        [
            ("吞", "nuốt", Layer.BASE_MULTI),
            ("下", "xuống", Layer.BASE_SINGLE),
            ("丹药", "đan dược", Layer.BASE_MULTI),
            ("了", "", Layer.BASE_SINGLE),
            ("一口", "một ngụm", Layer.BASE_MULTI),
        ]
    )
    down = vp_plan(dic, "吞下丹药")
    sip = vp_plan(dic, "一口吞")
    assert "nuốt" in down.text.lower()
    assert "thôn" not in down.text.lower()
    assert "nuốt" in sip.text.lower()


def test_sense_tun_name_final_thon():
    dic = mini(
        [
            ("吴", "Ngô", Layer.BASE_SINGLE),
            ("吞", "nuốt", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "吴吞。")
    assert "thôn" in draft.text.lower()
    assert "nuốt" not in draft.text.lower()


def test_sense_tun_chi_does_not_swallow_name():
    dic = mini(
        [
            ("吴", "Ngô", Layer.BASE_SINGLE),
            ("吞", "nuốt", Layer.BASE_MULTI),
            ("吞吃", "nuốt ăn", Layer.BASE_MULTI),
            ("着", "đang", Layer.BASE_SINGLE),
            ("东西", "đồ vật", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "吴吞吃着东西")
    low = draft.text.lower()
    assert "thôn" in low
    assert "nuốt" not in low


def test_clause_is_question():
    assert clause_is_question("多少人？", 0) is True
    assert clause_is_question("多少人。", 0) is False


def test_literal_same_length_beats_pattern():
    dic = mini(
        [
            ("一把拽住", "một cái níu lấy", Layer.GLOBAL_MANUAL),
            ("一把", "một thanh", Layer.BASE_MULTI),
            ("拽住", "níu lấy", Layer.BASE_MULTI),
        ],
        [("一把{v}", "một cái {v}")],
    )
    edges = greedy_path(dic, "一把拽住")
    assert edges[0].target == "một cái níu lấy"
    assert edges[0].is_pattern is False


def test_verbs_contains_zhuai():
    assert "拽住" in VERBS


def test_p_stops_before_kan():
    dic = mini(
        [
            ("书籍", "sách", Layer.BASE_MULTI),
            ("看完", "xem hết", Layer.BASE_MULTI),
            ("看", "xem", Layer.BASE_SINGLE),
            ("完", "hết", Layer.BASE_SINGLE),
        ],
        [("桌上的{p}", "{p} trên bàn")],
    )
    draft = vp_plan(dic, "桌上的书籍看完")
    low = draft.text.lower()
    assert "sách trên bàn" in low
    assert "xem hết trên bàn" not in low


def test_p_stops_before_jiu():
    dic = mini(
        [
            ("拿起", "cầm lấy", Layer.BASE_MULTI),
            ("地图", "địa đồ", Layer.BASE_MULTI),
            ("就", "liền", Layer.BASE_SINGLE),
            ("看", "xem", Layer.BASE_SINGLE),
        ],
        [("桌上的{p}", "{p} trên bàn")],
    )
    draft = vp_plan(dic, "拿起桌上的地图就看")
    low = draft.text.lower()
    assert "trên bàn" in low
    assert "thì nhìn trên bàn" not in low


def test_p_de_shihou_not_swallow_subject():
    """{p}的时候 greedy 4 chu se nuot '神女洗澡'. Khong nap rule do."""
    dic = mini(
        [
            ("神女", "thần nữ", Layer.BASE_MULTI),
            ("洗澡的时候", "lúc tắm", Layer.GLOBAL_MANUAL),
            ("洗澡", "tắm rửa", Layer.BASE_MULTI),
        ],
        [("桌上的{p}", "{p} trên bàn")],
    )
    draft = vp_plan(dic, "神女洗澡的时候")
    assert "thần nữ" in draft.text.lower()
    assert "lúc tắm" in draft.text.lower() or "Lúc tắm" in draft.text


def test_hui_future_after_keneng_rang():
    dic = mini(
        [
            ("可能", "có thể", Layer.BASE_MULTI),
            ("会", "hội", Layer.BASE_SINGLE),
            ("让", "để", Layer.BASE_SINGLE),
            ("弟子", "đệ tử", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "可能会让弟子")
    low = draft.text.lower()
    assert "sẽ" in low
    assert "hội" not in low


def test_hui_future_bei():
    dic = mini(
        [
            ("会", "hội", Layer.BASE_SINGLE),
            ("被", "bị", Layer.BASE_SINGLE),
            ("揪", "nhéo", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "会被揪")
    assert "sẽ" in draft.text.lower()


def test_hui_after_yiding():
    dic = mini(
        [
            ("一定", "nhất định", Layer.BASE_MULTI),
            ("会", "hội", Layer.BASE_SINGLE),
            ("来", "tới", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "一定会来")
    assert "sẽ" in draft.text.lower()


def test_hui_keeps_hoi_without_future_cue():
    dic = mini(
        [
            ("会", "hội", Layer.BASE_SINGLE),
            ("说", "nói", Layer.BASE_SINGLE),
            ("汉语", "Hán ngữ", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "会说汉语")
    assert "hội" in draft.text.lower()
    assert "sẽ" not in draft.text.lower()


def test_xiang_verb_keeps_muon():
    dic = mini(
        [
            ("想", "muốn", Layer.BASE_SINGLE),
            ("逼", "bức", Layer.BASE_SINGLE),
            ("我", "ta", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "想逼我")
    assert "muốn" in draft.text.lower()
    assert "nhớ" not in draft.text.lower()


def test_xiang_he_keeps_muon():
    dic = mini(
        [
            ("想", "muốn", Layer.BASE_SINGLE),
            ("和", "cùng", Layer.BASE_SINGLE),
            ("小天", "Tiểu Thiên", Layer.BASE_MULTI),
            ("玩", "chơi", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "想和小天玩")
    assert "muốn" in draft.text.lower()


def test_xiang_pronoun_clause_end_nho():
    dic = mini(
        [
            ("想", "muốn", Layer.BASE_SINGLE),
            ("你", "ngươi", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "想你。")
    assert "nhớ" in draft.text.lower()


def test_xiang_pronoun_then_verb_tuong():
    dic = mini(
        [
            ("想", "muốn", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("来", "tới", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "想他来")
    assert "tưởng" in draft.text.lower()


def test_xiang_ta_yidai_not_nho():
    """Chap1: 想他一代神尊 — nghi, khong nho."""
    dic = mini(
        [
            ("想", "muốn", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("一代", "một đời", Layer.BASE_MULTI),
            ("神尊", "Thần Tôn", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "想他一代神尊")
    low = draft.text.lower()
    assert "nhớ" not in low
    assert "muốn" in low or "hắn" in low


def test_shi_pronoun_then_verb():
    dic = mini(
        [
            ("他", "hắn", Layer.BASE_SINGLE),
            ("是", "là", Layer.BASE_SINGLE),
            ("被", "bị", Layer.BASE_SINGLE),
            ("骗", "lừa", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "他是被骗")
    assert "đúng là" in draft.text.lower() or "Đúng là" in draft.text


def test_ba_pv_does_not_break_zhuoshang():
    dic = mini(
        [
            ("书籍", "sách", Layer.BASE_MULTI),
            ("看完", "xem hết", Layer.BASE_MULTI),
            ("看", "xem", Layer.BASE_SINGLE),
            ("把", "đem", Layer.BASE_SINGLE),
        ],
        [
            ("桌上的{p}", "{p} trên bàn"),
            ("把{p}{v}", "đem {p} {v}"),
        ],
    )
    draft = vp_plan(dic, "把桌上的书籍看完")
    low = draft.text.lower()
    assert "sách trên bàn" in low
    assert "xem hết trên bàn" not in low


def test_ba_pv_inverts_noun_verb():
    dic = mini(
        [
            ("剑", "kiếm", Layer.BASE_SINGLE),
            ("扔掉", "ném đi", Layer.BASE_MULTI),
            ("把", "đem", Layer.BASE_SINGLE),
        ],
        [("把{p}{v}", "đem {p} {v}")],
    )
    draft = vp_plan(dic, "把剑扔掉")
    low = draft.text.lower()
    assert "đem" in low
    assert "kiếm" in low
    assert "ném" in low


def test_n_suffix_zong_without_names():
    dic = mini(
        [("弟子", "đệ tử", Layer.BASE_MULTI)],
        [("{n}弟子", "{n} đệ tử")],
    )
    draft = vp_plan(dic, "逍遥宗弟子")
    assert "đệ tử" in draft.text.lower()
    edges = greedy_path(dic, "逍遥宗弟子")
    assert any(e.is_pattern for e in edges)


def test_n_ziji_not_swallow_wushi():
    dic = mini(
        [
            ("看到", "nhìn thấy", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("居然", "thế mà", Layer.BASE_MULTI),
            ("无视", "vô thị", Layer.BASE_MULTI),
            ("自己", "mình", Layer.BASE_MULTI),
        ],
        [("{n}自己", "{n} mình")],
    )
    draft = vp_plan(dic, "看到凌天居然无视自己")
    low = draft.text.lower()
    assert "vô thị" in low
    assert "lăng thiên" in low


def test_shi_not_but():
    dic = mini(
        [
            ("但", "nhưng", Layer.BASE_SINGLE),
            ("是", "là", Layer.BASE_SINGLE),
            ("来", "tới", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "但是来")
    assert "đúng là" not in draft.text.lower()


def test_zenmehui_phrase_drops_se():
    """怎么会 3 chu — rhetorical lai, khong tach 会 (AD-9)."""
    dic = mini(
        [
            ("怎么会", "làm sao sẽ", Layer.BASE_MULTI),
            ("让", "để", Layer.BASE_SINGLE),
            ("弟子", "đệ tử", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "怎么会让弟子")
    low = draft.text.lower()
    assert "lại" in low
    assert "sẽ" not in low
    edges = greedy_path(dic, "怎么会让弟子")
    assert edges[0].end - edges[0].start == 3


def test_zenmehui_rang_keeps_longest():
    """怎么会让 dai hon 怎么会 — giu span, chi doi se -> lai."""
    dic = mini(
        [
            ("怎么会让", "làm sao sẽ để cho", Layer.BASE_MULTI),
            ("怎么会", "làm sao lại", Layer.BASE_MULTI),
            ("弟子", "đệ tử", Layer.BASE_MULTI),
        ]
    )
    edges = greedy_path(dic, "怎么会让弟子")
    assert edges[0].end - edges[0].start == 4
    low = vp_plan(dic, "怎么会让弟子").text.lower()
    assert "lại" in low
    assert "sẽ" not in low


def test_zenmekenenghui_no_se():
    dic = mini(
        [
            ("怎么可能会", "làm sao sẽ", Layer.BASE_MULTI),
            ("让", "để", Layer.BASE_SINGLE),
            ("弟子", "đệ tử", Layer.BASE_MULTI),
        ]
    )
    draft = vp_plan(dic, "怎么可能会让弟子")
    low = draft.text.lower()
    assert "làm sao lại" in low
    assert "sẽ" not in low
    edges = greedy_path(dic, "怎么可能会让弟子")
    assert edges[0].end - edges[0].start == 5


def test_kenenghui_keeps_span():
    """可能会 khong tach 会; future van 'sẽ'."""
    dic = mini(
        [
            ("可能会", "có thể hội", Layer.BASE_MULTI),
            ("让", "để", Layer.BASE_SINGLE),
            ("弟子", "đệ tử", Layer.BASE_MULTI),
        ]
    )
    edges = greedy_path(dic, "可能会让弟子")
    assert edges[0].end - edges[0].start == 3
    low = vp_plan(dic, "可能会让弟子").text.lower()
    assert "sẽ" in low
    assert "hội" not in low


def test_le_aspect_da_not_dropped():
    """了 1 chu: đã, khong boc QT, khong phien am liễu."""
    dic = mini(
        [
            ("来", "tới", Layer.BASE_SINGLE),
            ("了", "liễu", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "来了")
    low = draft.text.lower()
    assert "đã" in low
    assert "liễu" not in low
    edges = greedy_path(dic, "来了")
    assert edges[-1].end - edges[-1].start == 1
    assert edges[-1].target == "đã"


def test_zhe_aspect_dang():
    dic = mini(
        [
            ("看", "xem", Layer.BASE_SINGLE),
            ("着", "trứ", Layer.BASE_SINGLE),
            ("我", "ta", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "看着我")
    low = draft.text.lower()
    assert "đang" in low
    assert "trứ" not in low


def test_guo_aspect_roi():
    dic = mini(
        [
            ("去", "đi", Layer.BASE_SINGLE),
            ("过", "quá", Layer.BASE_SINGLE),
        ]
    )
    draft = vp_plan(dic, "去过")
    low = draft.text.lower()
    assert "rồi" in low
    assert "quá" not in low


def test_le_inside_phrase_keeps_span():
    """看了起来 dai hon 了 — AD-9 khong tach hat."""
    dic = mini(
        [
            ("看了起来", "xem lên", Layer.BASE_MULTI),
            ("看", "xem", Layer.BASE_SINGLE),
            ("了", "liễu", Layer.BASE_SINGLE),
            ("起来", "lên", Layer.BASE_MULTI),
        ]
    )
    edges = greedy_path(dic, "看了起来")
    assert edges[0].end - edges[0].start == 4
    assert "đã" not in vp_plan(dic, "看了起来").text.lower()


def test_le_after_locative_zai_dropped():
    """了 sau 在 (gioi tu noi cho) khong chen 'đã'."""
    dic = mini(
        [
            ("压制在", "áp chế ở", Layer.BASE_MULTI),
            ("踏在", "đạp ở", Layer.BASE_MULTI),
            ("消失在", "biến mất ở", Layer.BASE_MULTI),
            ("缠绕在", "quấn quanh ở", Layer.BASE_MULTI),
            ("了", "đã", Layer.GLOBAL_MANUAL),
            ("神宫", "thần cung", Layer.BASE_MULTI),
        ]
    )
    for zh in ("压制在了神宫", "踏在了", "消失在了", "缠绕在了"):
        low = vp_plan(dic, zh).text.lower()
        assert "đã" not in low, zh
        assert "ở" in low, zh
    lai = mini(
        [
            ("来", "tới", Layer.BASE_SINGLE),
            ("了", "đã", Layer.GLOBAL_MANUAL),
        ]
    )
    assert "đã" in vp_plan(lai, "来了").text.lower()


def test_le_after_de_modal_dropped():
    """不可思议的了: 了 sau 的 la tieu tu, khong 'đã'."""
    dic = mini(
        [
            ("不可思议的", "bất khả tư nghị", Layer.BASE_MULTI),
            ("已经是", "đã là", Layer.BASE_MULTI),
            ("极其", "cực kỳ", Layer.BASE_MULTI),
            ("这", "đây", Layer.BASE_SINGLE),
            ("了", "đã", Layer.GLOBAL_MANUAL),
            ("的", "", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "这已经是极其不可思议的了").text.lower()
    assert "bất khả tư nghị" in t
    assert not t.rstrip(".。").endswith("đã")
    assert t.count("đã") == 1


def test_le_after_yijing_dropped_lai_kept():
    """已经...了: mot 'đã'; 来了 khong co 已经 van giu aspect."""
    dic = mini(
        [
            ("已经", "đã", Layer.BASE_MULTI),
            ("有些", "có chút", Layer.BASE_MULTI),
            ("麻木", "chết lặng", Layer.BASE_MULTI),
            ("了", "đã", Layer.GLOBAL_MANUAL),
            ("来", "tới", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他已经有些麻木了").text.lower()
    assert t.count("đã") == 1
    assert "chết lặng" in t
    lai = mini(
        [
            ("来", "tới", Layer.BASE_SINGLE),
            ("了", "đã", Layer.GLOBAL_MANUAL),
        ]
    )
    assert "đã" in vp_plan(lai, "来了").text.lower()


def test_le_after_locative_dao_gei_dropped():
    """了 sau 到/给 khong chen 'đã' — 来了 van giu aspect."""
    dic = mini(
        [
            ("走", "đi", Layer.BASE_SINGLE),
            ("到", "đến", Layer.BASE_SINGLE),
            ("给", "cho", Layer.BASE_SINGLE),
            ("了", "đã", Layer.GLOBAL_MANUAL),
            ("他", "hắn", Layer.BASE_SINGLE),
        ]
    )
    assert "đã" not in vp_plan(dic, "走到了").text.lower()
    assert "đến" in vp_plan(dic, "走到了").text.lower()
    assert "đã" not in vp_plan(dic, "给了他").text.lower()
    assert "cho" in vp_plan(dic, "给了他").text.lower()
    lai = mini(
        [
            ("来", "tới", Layer.BASE_SINGLE),
            ("了", "đã", Layer.GLOBAL_MANUAL),
        ]
    )
    assert "đã" in vp_plan(lai, "来了").text.lower()


def test_long_name_vs_animal():
    """龙 1 chu: ho+ten -> Long; classifier con vat -> rồng. 青龙 2 chu khong doi."""
    name = mini(
        [
            ("郑晓", "Trịnh Hiểu", Layer.BASE_MULTI),
            ("龙", "rồng", Layer.BASE_SINGLE),
        ]
    )
    assert "Long" in vp_plan(name, "郑晓龙").text
    assert "rồng" not in vp_plan(name, "郑晓龙").text.lower()
    animal = mini(
        [
            ("一条", "một con", Layer.BASE_MULTI),
            ("龙", "rồng", Layer.BASE_SINGLE),
        ]
    )
    assert "rồng" in vp_plan(animal, "一条龙").text.lower()
    compound = mini(
        [
            ("青龙", "Thanh Long", Layer.BASE_MULTI),
            ("龙", "rồng", Layer.BASE_SINGLE),
            ("从", "từ", Layer.BASE_SINGLE),
            ("天", "trời", Layer.BASE_SINGLE),
        ]
    )
    assert "Thanh Long" in vp_plan(compound, "青龙从天").text
    assert "rồng" not in vp_plan(compound, "青龙从天").text.lower()


def test_collapse_da_da_and_bi_bi():
    """đã đã / bị bị la artifact convert; phòng bị + bị đánh giu."""
    da = mini(
        [
            ("已经", "đã", Layer.GLOBAL_MANUAL),
            ("了", "đã", Layer.GLOBAL_MANUAL),
            ("有", "có", Layer.BASE_SINGLE),
        ]
    )
    out = vp_plan(da, "已经有了").text.lower()
    assert "đã đã" not in out
    assert "đã có" in out or "có" in out
    bi = mini(
        [
            ("被", "bị", Layer.BASE_SINGLE),
            ("吓", "hù", Layer.BASE_SINGLE),
        ]
    )
    hout = vp_plan(bi, "被吓").text.lower()
    assert "bị bị" not in hout
    assert "bị hù" in hout or "hù" in hout
    phong = mini(
        [
            ("防备", "phòng bị", Layer.BASE_MULTI),
            ("被", "bị", Layer.BASE_SINGLE),
            ("打", "đánh", Layer.BASE_SINGLE),
        ]
    )
    pout = vp_plan(phong, "防备被打").text.lower()
    assert "phòng bị bị đánh" in pout or "phòng bị" in pout
    doat = mini(
        [
            ("已经", "đã", Layer.GLOBAL_MANUAL),
            ("被", "bị", Layer.BASE_SINGLE),
            ("抢走", "đoạt", Layer.BASE_MULTI),
            ("了", "đã", Layer.GLOBAL_MANUAL),
        ]
    )
    dout = vp_plan(doat, "已经被抢走了").text.lower()
    assert "đã bị đoạt đã" not in dout


def test_shuodao_strips_rang():
    dic = mini(
        [
            ("说道", "nói rằng", Layer.BASE_MULTI),
            ("知道", "biết", Layer.BASE_MULTI),
        ]
    )
    said = vp_plan(dic, "说道").text.lower()
    assert "nói" in said
    assert "rằng" not in said
    know = vp_plan(dic, "知道").text.lower()
    assert "rằng" not in know
    assert "biết" in know


def test_de_particle_still_dropped():
    dic = mini(
        [
            ("天", "thiên", Layer.BASE_SINGLE),
            ("的", "đích", Layer.BASE_SINGLE),
        ]
    )
    assert vp_plan(dic, "天的").text == "Thiên"


def test_jingzhi_inverts_from_context_file():
    """精致的{p} neo literal — Adj+N dao, khong POS toan cuc."""
    dic = mini(
        [
            ("精致的", "tinh xảo", Layer.GLOBAL_MANUAL),
            ("鹅蛋脸", "mặt trứng ngỗng", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "精致的鹅蛋脸").text.lower()
    assert "mặt trứng ngỗng tinh xảo" in low
    assert "tinh xảo mặt" not in low


def test_lianshang_inverts_from_context_file():
    dic = mini(
        [
            ("脸上的", "trên mặt", Layer.GLOBAL_MANUAL),
            ("笑容", "nụ cười", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "脸上的笑容").text.lower()
    assert "nụ cười trên mặt" in low
    assert "trên mặt nụ" not in low


def test_ta_lianshang_inverts_from_context_file():
    """他脸上的 dai hon 脸上的 — van dao N."""
    dic = mini(
        [
            ("他脸上的", "trên mặt hắn", Layer.BASE_MULTI),
            ("笑容", "nụ cười", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "他脸上的笑容").text.lower()
    assert "nụ cười trên mặt hắn" in low
    assert "trên mặt hắn nụ" not in low


def test_ruoda_inverts_from_context_file():
    dic = mini(
        [
            ("偌大的", "lớn như vậy", Layer.GLOBAL_MANUAL),
            ("教室", "phòng học", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "偌大的教室").text.lower()
    assert "phòng học lớn như vậy" in low
    assert "lớn như vậy phòng" not in low


def test_liusui_inverts_from_context_file():
    dic = mini(
        [
            ("六岁", "sáu tuổi", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "六岁的凌天").text.lower()
    assert "lăng thiên sáu tuổi" in low
    assert "sáu tuổi lăng" not in low


def test_liusui_p_stops_before_shang():
    """六岁的凌天上的学前班 — {p} khong nuot 上."""
    dic = mini(
        [
            ("六岁", "sáu tuổi", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("上的", "trên", Layer.BASE_MULTI),
            ("学前班", "học tiền ban", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "六岁的凌天上的学前班").text.lower()
    assert "lăng thiên sáu tuổi" in low
    assert "bên trên sáu tuổi" not in low


def test_lingtian_de_p_stops_before_hou():
    dic = mini(
        [
            ("看到", "nhìn thấy", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("动作", "động tác", Layer.BASE_MULTI),
            ("后", "sau", Layer.BASE_SINGLE),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "看到凌天的动作后").text.lower()
    assert "động tác của lăng thiên" in low
    assert "động tác sau" not in low


def test_shenzong_li_inverts_from_context_file():
    dic = mini(
        [
            ("神宗", "thần tông", Layer.BASE_MULTI),
            ("圣女", "Thánh nữ", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    low = vp_plan(dic, "神宗里的圣女").text.lower()
    assert "thánh nữ trong thần tông" in low
    assert "thần tông" in low
    assert not low.startswith("thần tông")


def test_shihou_still_not_in_context_file():
    """{p}的时候 cam over-match — khong nam trong ContextPatterns."""
    assert not any(k.startswith("{p}的时候") or "的时候" in k for k, _ in context_rules())


def _dehua_dic() -> Dictionary:
    return mini(
        [
            ("女厕所", "nhà vệ sinh nữ", Layer.BASE_MULTI),
            ("的话", "nếu", Layer.GLOBAL_MANUAL),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("听到", "nghe tới", Layer.BASE_MULTI),
            ("如果", "nếu như", Layer.BASE_MULTI),
            ("没有", "không có", Layer.BASE_MULTI),
            ("恢复好", "khôi phục tốt", Layer.BASE_MULTI),
        ]
    )


def test_dehua_topic_thi():
    """女厕所的话 — particle cuoi de → thì, khong nếu."""
    t = vp_plan(_dehua_dic(), "女厕所的话，凌天又不太好进去").text.lower()
    assert "nhà vệ sinh nữ thì" in t
    assert "nữ nếu" not in t


def test_dehua_speech_loi():
    """听到凌天的话 — loi, khong nếu/thì."""
    t = vp_plan(_dehua_dic(), "听到凌天的话，转身向外走").text.lower()
    assert "lăng thiên lời" in t
    assert "nếu" not in t
    assert "thì" not in t


def test_dehua_ruguo_neu_thi():
    """如果…的话 → nếu … thì, het nếu…nếu."""
    t = vp_plan(_dehua_dic(), "如果没有恢复好的话").text.lower()
    assert "nếu như" in t
    assert "thì" in t
    assert t.count("nếu") == 1


def _diyi_dic() -> Dictionary:
    return mini(
        [
            ("禀告", "bẩm báo", Layer.BASE_MULTI),
            ("第一", "thứ nhất", Layer.BASE_MULTI),
            ("第二", "thứ hai", Layer.BASE_MULTI),
            ("第三", "thứ ba", Layer.BASE_MULTI),
            ("第四", "thứ tư", Layer.BASE_MULTI),
            ("第七", "thứ bảy", Layer.BASE_MULTI),
            ("第十一", "thứ mười một", Layer.BASE_MULTI),
            ("第十八", "thứ mười tám", Layer.BASE_MULTI),
            ("第二十", "thứ hai mươi", Layer.BASE_MULTI),
            ("始祖", "thủy tổ", Layer.BASE_MULTI),
            ("神尊", "Thần Tôn", Layer.BASE_MULTI),
            ("长老", "trưởng lão", Layer.BASE_MULTI),
            ("波", "đợt", Layer.BASE_SINGLE),
            ("攻击", "công kích", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("个", "cái", Layer.BASE_SINGLE),
        ]
    )


def test_diyi_shizu_de_nhat():
    t = vp_plan(_diyi_dic(), "禀告第一始祖").text.lower()
    assert "đệ nhất thủy tổ" in t
    assert "thứ nhất" not in t


def test_dier_disan_shizu():
    t = vp_plan(_diyi_dic(), "第二始祖").text.lower()
    assert "đệ nhị thủy tổ" in t
    t = vp_plan(_diyi_dic(), "第三始祖").text.lower()
    assert "đệ tam thủy tổ" in t


def test_diyi_shenzun_de_nhat():
    t = vp_plan(_diyi_dic(), "第一神尊").text.lower()
    assert "đệ nhất" in t
    assert "thứ nhất" not in t


def test_diyi_counter_keeps_thu_nhat():
    """第一波 / 第二个人 — thu tu, khong phai danh hieu."""
    t = vp_plan(_diyi_dic(), "第一波攻击").text.lower()
    assert "thứ nhất" in t
    assert "đệ nhất" not in t
    t = vp_plan(_diyi_dic(), "第二个人").text.lower()
    assert "thứ hai" in t
    assert "đệ nhị" not in t


def test_diyi_ren_de_nhat_nhan():
    t = vp_plan(_diyi_dic(), "第一人").text.lower()
    assert "đệ nhất" in t


def test_ordinal_title_scales():
    """第X + ton hieu -> de + so Han-Viet (tu, that, thap nhat...)."""
    cases = [
        ("第四始祖", "đệ tứ thủy tổ"),
        ("第七神尊", "đệ thất"),
        ("第十一始祖", "đệ thập nhất thủy tổ"),
        ("第十八始祖", "đệ thập bát thủy tổ"),
        ("第二十神尊", "đệ nhị thập"),
        ("第十一长老", "đệ thập nhất trưởng lão"),
    ]
    for zh, want in cases:
        t = vp_plan(_diyi_dic(), zh).text.lower()
        assert want in t, (zh, t)
        assert "thứ" not in t, (zh, t)


def test_ordinal_counter_keeps_thu():
    t = vp_plan(_diyi_dic(), "第四波攻击").text.lower()
    assert "thứ tư" in t
    assert "đệ tứ" not in t


def _zhangmen_dic(with_title: bool = True) -> Dictionary:
    entries = [
        ("第一", "thứ nhất", Layer.BASE_MULTI),
        ("第一掌", "chưởng thứ nhất", Layer.BASE_MULTI),
        ("掌", "chưởng", Layer.BASE_SINGLE),
        ("门", "cửa", Layer.BASE_SINGLE),
        ("掌门人", "chưởng môn nhân", Layer.BASE_MULTI),
    ]
    if with_title:
        entries.append(("掌门", "chưởng môn", Layer.BASE_MULTI))
    return mini(entries)


def test_ordinal_zhangmen_not_split():
    """第一掌门 — 第X + title thang, khong che thanh chuong phap + cua."""
    t = vp_plan(_zhangmen_dic(), "第一掌门").text.lower()
    assert "đệ nhất chưởng môn" in t
    assert "cửa" not in t


def test_ordinal_zhangmenren():
    t = vp_plan(_zhangmen_dic(), "第一掌门人").text.lower()
    assert "đệ nhất chưởng môn nhân" in t


def test_ordinal_palm_strike_kept():
    """第一掌 don le (chuong phap) — khong title theo sau, giu nguyen."""
    t = vp_plan(_zhangmen_dic(), "第一掌").text.lower()
    assert "chưởng thứ nhất" in t


def test_ordinal_guard_needs_title_in_trie():
    """Title khong co trong trie -> khong che (giu hanh vi cu)."""
    t = vp_plan(_zhangmen_dic(with_title=False), "第一掌门").text.lower()
    assert "chưởng thứ nhất" in t


def _busi_dic() -> Dictionary:
    return mini(
        [
            ("弱", "yếu", Layer.BASE_SINGLE),
            ("到不", "không đến được", Layer.BASE_MULTI),
            ("到", "đến", Layer.BASE_SINGLE),
            ("不可思议", "không thể tưởng tượng nổi", Layer.BASE_MULTI),
            ("可", "nhưng", Layer.BASE_SINGLE),
            ("思议", "tư nghị", Layer.BASE_MULTI),
            ("不了", "không xong", Layer.BASE_MULTI),
            ("了", "đã", Layer.BASE_SINGLE),
        ]
    )


def test_busi_not_split_by_daobu():
    """弱到不可思议 — 到不 cuop 不, drop de 不可思议 thang."""
    t = vp_plan(_busi_dic(), "弱到不可思议").text.lower()
    assert "không thể tưởng tượng nổi" in t
    assert "không đến được" not in t
    assert "nhưng tư nghị" not in t


def test_daobuliao_kept():
    """到不了 that — 不了 (2) khong dai hon 到不 (2), giu nguyen."""
    t = vp_plan(_busi_dic(), "到不了").text.lower()
    assert "không đến được" in t


def _bu_keep_dic() -> Dictionary:
    return mini(
        [
            ("要不", "nếu không", Layer.BASE_MULTI),
            ("要", "muốn", Layer.BASE_SINGLE),
            ("这不", "đây không phải", Layer.BASE_MULTI),
            ("这", "này", Layer.BASE_SINGLE),
            ("毫不", "không chút nào", Layer.BASE_MULTI),
            ("毫", "hào", Layer.BASE_SINGLE),
            ("开着车", "lái xe", Layer.BASE_MULTI),
            ("还没到", "còn chưa tới", Layer.BASE_MULTI),
            ("设防", "phòng bị", Layer.BASE_MULTI),
            ("不设防", "không đề phòng", Layer.BASE_MULTI),
            ("莫不", "không ai không", Layer.BASE_MULTI),
            ("莫", "chớ", Layer.BASE_SINGLE),
            ("并不", "cũng không", Layer.BASE_MULTI),
            ("并", "cũng", Layer.BASE_SINGLE),
            ("多见", "thấy nhiều", Layer.BASE_MULTI),
        ]
    )


def test_yaobu_kept():
    """要不 da thanh lap — khong drop du 不开着 dai hon."""
    t = vp_plan(_bu_keep_dic(), "要不开着车").text.lower()
    assert "nếu không" in t
    assert "muốn" not in t


def test_zhebu_kept():
    t = vp_plan(_bu_keep_dic(), "这不还没到").text.lower()
    assert "đây không phải" in t


def test_haobu_kept():
    """毫不 da thanh lap — khong drop du 不设防 dai hon."""
    t = vp_plan(_bu_keep_dic(), "毫不设防").text.lower()
    assert "không chút nào phòng bị" in t
    assert "hào" not in t


def test_mobu_bingbu_kept():
    """莫不/并不 da thanh lap — khong drop."""
    t = vp_plan(_bu_keep_dic(), "莫不都是").text.lower()
    assert "không ai không" in t
    t = vp_plan(_bu_keep_dic(), "并不多见").text.lower()
    assert "cũng không" in t


def test_custom_name_beats_glue():
    """左边是小美 — glue 是小 khong duoc nuot ten Custom 小美."""
    dic = mini(
        [
            ("左边", "bên trái", Layer.BASE_MULTI),
            ("是", "là", Layer.BASE_SINGLE),
            ("是小", "là nhỏ", Layer.BASE_MULTI),
            ("小", "nhỏ", Layer.BASE_SINGLE),
            ("美", "đẹp", Layer.BASE_SINGLE),
            ("小美", "Tiểu Mỹ", Layer.GLOBAL_MANUAL, 100.0),
        ]
    )
    t = vp_plan(dic, "左边是小美").text
    assert "Tiểu Mỹ" in t
    assert "nhỏ đẹp" not in t.lower()


def test_yiyue_tiao_no_dup():
    """一跃跳上 — nhay vot len, khong 'nhay len nhay len'."""
    dic = mini(
        [
            ("一跃", "nhảy lên", Layer.BASE_MULTI),
            ("跳上", "nhảy lên", Layer.BASE_MULTI),
            ("洗手台", "bồn rửa tay", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "一跃跳上洗手台").text.lower()
    assert "nhảy vọt lên" in t
    assert t.count("nhảy") == 1


def test_yiyue_erqi_kept():
    """一跃而起 — phrase dai thang, giu nguyen."""
    dic = mini(
        [
            ("一跃", "nhảy lên", Layer.BASE_MULTI),
            ("一跃而起", "nhảy lên một cái", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "一跃而起").text.lower()
    assert "nhảy lên một cái" in t


def _idiom_dic() -> Dictionary:
    return mini(
        [
            ("人望", "nhân vọng", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("望其项背", "nhìn theo bóng lưng", Layer.BASE_MULTI),
            ("早就", "đã sớm", Layer.BASE_MULTI),
            ("早", "sớm", Layer.BASE_SINGLE),
            ("就忍不住", "liền không nhịn được", Layer.BASE_MULTI),
        ]
    )


def test_idiom_head_not_glued():
    """人望 + 望其项背 — drop edge 2 chu de thanh ngu thang."""
    t = vp_plan(_idiom_dic(), "人望其项背").text.lower()
    assert "nhìn theo bóng lưng" in t
    assert "nhân vọng" not in t


def test_compositional_phrase_not_idiom():
    """早就 — 就忍不住 chia doi duoc, khong bao ve, giu nguyen."""
    t = vp_plan(_idiom_dic(), "早就忍不住").text.lower()
    assert "đã sớm" in t


def _dehua_possessive_dic() -> Dictionary:
    return mini(
        [
            ("要是", "nếu là", Layer.BASE_MULTI),
            ("杀掉", "giết chết", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("的话", "nếu", Layer.GLOBAL_MANUAL),
            ("话", "lời nói", Layer.BASE_SINGLE),
            ("剑", "kiếm", Layer.BASE_SINGLE),
            ("他说", "hắn nói", Layer.BASE_MULTI),
        ],
        [("凌天的{p}", "{p} của Lăng Thiên")],
    )


def test_dehua_conditional_not_possessive():
    """要是杀掉凌天的话，他… — conditional thi, khong 'loi noi cua'."""
    t = vp_plan(_dehua_possessive_dic(), "要是杀掉凌天的话，他说").text.lower()
    assert "lăng thiên thì" in t
    assert "lời nói" not in t


def test_possessive_still_works_for_noun():
    """凌天的剑 — so huu that, pattern van dao N."""
    t = vp_plan(_dehua_possessive_dic(), "凌天的剑").text.lower()
    assert "kiếm của lăng thiên" in t


def test_dehua_topic_keeps_possessive():
    """凌天的话让... — topic + dong tu, giu 'loi noi cua', khong thi."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("的话", "nếu", Layer.GLOBAL_MANUAL),
            ("话", "lời nói", Layer.BASE_SINGLE),
            ("让", "khiến", Layer.BASE_SINGLE),
            ("一群", "một đám", Layer.BASE_MULTI),
        ],
        [("凌天的{p}", "{p} của Lăng Thiên")],
    )
    t = vp_plan(dic, "凌天的话让一群").text.lower()
    assert "lời nói của lăng thiên" in t
    assert "thì" not in t


def test_dehua_speech_keeps_possessive():
    """听到凌天的话，转身 — ngu canh nghe, giu 'loi noi cua' (dao ngu)."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI),
            ("的话", "nếu", Layer.GLOBAL_MANUAL),
            ("话", "lời nói", Layer.BASE_SINGLE),
            ("听到", "nghe tới", Layer.BASE_MULTI),
            ("转身", "quay người", Layer.BASE_MULTI),
        ],
        [("凌天的{p}", "{p} của Lăng Thiên")],
    )
    t = vp_plan(dic, "听到凌天的话，转身").text.lower()
    assert "lời nói của lăng thiên" in t
    assert "nếu" not in t
    assert "thì" not in t


def test_called_named_person_not_possessive():
    """一个叫凌天的人: ten, khong 'người của Lăng Thiên' (凌天的{p})."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.GLOBAL_MANUAL, 100.0),
            ("一个", "một", Layer.BASE_MULTI),
            ("叫", "gọi", Layer.BASE_SINGLE),
            ("人", "người", Layer.BASE_SINGLE),
        ],
        [
            ("一个叫{n}的人", "một người tên {n}"),
            ("凌天的{p}", "{p} của Lăng Thiên"),
        ],
    )
    t = vp_plan(dic, "一个叫凌天的人").text
    assert "tên Lăng Thiên" in t or "tên lăng thiên" in t.lower()
    assert "của Lăng Thiên" not in t


def test_name_de_phone_inverts():
    """邱东的电话 -> điện thoại của Khâu Đông, khong 'Khâu Đông điện thoại của'."""
    dic = mini(
        [
            ("邱东", "Khâu Đông", Layer.GLOBAL_MANUAL, 100.0),
            ("电话", "điện thoại", Layer.BASE_MULTI),
            ("拨通了", "gọi điện", Layer.GLOBAL_MANUAL),
        ],
        [
            ("拨通了{n}的电话", "gọi điện cho {n}"),
            ("{n}的电话", "điện thoại của {n}"),
        ],
    )
    t = vp_plan(dic, "拨通了邱东的电话").text.lower()
    assert "cho khâu đông" in t
    assert "khâu đông điện thoại của" not in t


def test_car_parked_subject_not_imperative():
    """车停在了 = xe đậu, khong 'đậu xe' (停车)."""
    dic = mini(
        [
            ("车停在了", "xe đậu ở", Layer.GLOBAL_MANUAL),
            ("一家", "một nhà", Layer.BASE_MULTI),
            ("高档会所", "hội sở cao cấp", Layer.GLOBAL_MANUAL),
            ("前", "trước", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "车停在了一家高档会所前").text
    low = t.lower()
    assert "xe đậu" in low
    assert not low.startswith("đậu xe")


def test_tinei_xuemai_zhili_not_split():
    """体内血脉 (4) cuop 血脉之力 — stolen_compound drop, khong can khoa 6 chu."""
    dic = mini(
        [
            ("体内", "trong cơ thể", Layer.GLOBAL_MANUAL),
            ("体内血脉", "huyết mạch trong cơ thể", Layer.BASE_MULTI),
            ("血脉之力", "huyết mạch chi lực", Layer.BASE_MULTI),
            ("之力", "chi lực", Layer.BASE_MULTI),
            ("太多", "quá nhiều", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "体内血脉之力太多").text.lower()
    assert "huyết mạch chi lực" in t
    assert "huyết mạch trong cơ thể chi lực" not in t


def test_xuemai_kunrao_not_boi_roi():
    """困扰 first-sense VP la bối rối; 受到血脉困扰 = bị huyết mạch quấy nhiễu."""
    dic = mini(
        [
            ("受到血脉困扰", "bị huyết mạch quấy nhiễu", Layer.GLOBAL_MANUAL),
            ("困扰", "quấy nhiễu", Layer.GLOBAL_MANUAL),
            ("受到", "nhận", Layer.BASE_MULTI),
            ("血脉", "huyết mạch", Layer.BASE_MULTI),
        ],
        [("受到{p}困扰", "bị {p} quấy nhiễu")],
    )
    t = vp_plan(dic, "我知道你受到血脉困扰").text.lower()
    assert "bị huyết mạch quấy nhiễu" in t
    assert "bối rối" not in t
    assert "nhận huyết mạch" not in t


def test_bushou_kunrao_typo_as_bushou():
    """不收困扰 (typo 不受) -> không bị quấy nhiễu, khong 'không thu bối rối'."""
    dic = mini(
        [
            ("不收困扰", "không bị quấy nhiễu", Layer.GLOBAL_MANUAL),
            ("不收", "không thu", Layer.BASE_MULTI),
            ("困扰", "bối rối", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "不收困扰").text.lower()
    assert "không bị quấy nhiễu" in t
    assert "không thu" not in t
    assert "bối rối" not in t


def test_juling_filter_array_not_loai_bo():
    """聚灵阵内 + 连环着的是 + 灵气过滤阵法 + 最耗费能量; 着=đang khong nuot 连环着."""
    dic = mini(
        [
            ("再接着", "tiếp theo", Layer.GLOBAL_MANUAL),
            ("又一个聚灵阵", "một tụ linh trận nữa", Layer.GLOBAL_MANUAL),
            ("聚灵阵内", "trong tụ linh trận", Layer.GLOBAL_MANUAL),
            ("聚灵阵", "tụ linh trận", Layer.BASE_MULTI),
            ("连环着的是", "nối liền chính là", Layer.GLOBAL_MANUAL),
            ("连环", "liên hoàn", Layer.BASE_MULTI),
            ("着", "đang", Layer.GLOBAL_MANUAL),
            ("的是", "chính là", Layer.BASE_MULTI),
            ("灵气过滤阵法", "trận pháp lọc linh khí", Layer.GLOBAL_MANUAL),
            ("过滤", "loại bỏ", Layer.BASE_MULTI),
            ("灵气", "linh khí", Layer.BASE_MULTI),
            ("阵法", "trận pháp", Layer.BASE_MULTI),
            ("最耗费能量", "tốn năng lượng nhất", Layer.GLOBAL_MANUAL),
            ("耗费", "hao phí", Layer.BASE_MULTI),
            ("能量", "năng lượng", Layer.BASE_MULTI),
            ("最", "nhất", Layer.BASE_SINGLE),
            ("都从来没用过", "cũng chưa từng dùng", Layer.GLOBAL_MANUAL),
            ("从来没", "cũng chưa hề", Layer.BASE_MULTI),
            ("用过", "dùng qua", Layer.BASE_MULTI),
            ("是", "là", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(
        dic,
        "再接着，是又一个聚灵阵，聚灵阵内，连环着的是，灵气过滤阵法，这阵法最耗费能量，凌天都从来没用过",
    ).text.lower()
    assert "tiếp theo" in t
    assert "lại nói tiếp" not in t
    assert "trong tụ linh trận" in t
    assert "tụ linh trận bên trong" not in t
    assert "nối liền chính là" in t
    assert "liên hoàn đang" not in t
    assert "trận pháp lọc linh khí" in t
    assert "loại bỏ" not in t
    assert "tốn năng lượng nhất" in t
    assert "hao nhất phí" not in t
    assert "chưa từng dùng" in t


def test_zaijiezhe_peiyang_keeps_continue():
    """不敢再接着培养: khoa ca cau — 不敢再 (3) nuot 再 cua 再接着."""
    dic = mini(
        [
            ("不敢再接着培养", "không dám tiếp tục bồi dưỡng", Layer.GLOBAL_MANUAL),
            ("再接着", "tiếp theo", Layer.GLOBAL_MANUAL),
            ("不敢再", "không còn dám", Layer.BASE_MULTI),
            ("接着", "tiếp lấy", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "不敢再接着培养").text.lower()
    assert "không dám tiếp tục bồi dưỡng" in t
    assert "tiếp theo" not in t
    assert "tiếp lấy" not in t


def test_xuemai_not_split_by_duoshaoxue():
    """多少血 (3) / 这么多血 (4) nuot 血脉 -> mau+mach. Khoa dai hon."""
    dic = mini(
        [
            ("有多少血脉", "có bao nhiêu huyết mạch", Layer.GLOBAL_MANUAL),
            ("这么多血脉", "nhiều huyết mạch như vậy", Layer.GLOBAL_MANUAL),
            ("任其中一种血脉", "bất kỳ một loại huyết mạch nào", Layer.GLOBAL_MANUAL),
            ("多少血", "máu nhiêu", Layer.BASE_MULTI),
            ("这么多血", "nhiều máu như vậy", Layer.BASE_MULTI),
            ("血脉", "huyết mạch", Layer.BASE_MULTI),
            ("任其", "mặc kệ", Layer.BASE_MULTI),
            ("中", "trúng", Layer.BASE_SINGLE),
            ("一种", "một loại", Layer.BASE_MULTI),
            ("脉", "mạch", Layer.BASE_SINGLE),
            ("血", "máu", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "这是有多少血脉？任其中一种血脉，这么多血脉").text.lower()
    assert "bao nhiêu huyết mạch" in t
    assert "máu nhiêu" not in t
    assert "nhiều huyết mạch như vậy" in t
    assert "nhiều máu như vậy mạch" not in t
    assert "bất kỳ một loại huyết mạch nào" in t
    assert "mặc kệ" not in t


def test_stolen_compound_keeps_xuemai_without_long_key():
    """Code: 多少血/这么多血 cuop 血 cua 血脉 — drop, khong can khoa 多少血脉."""
    dic = mini(
        [
            ("多少血", "máu nhiêu", Layer.BASE_MULTI),
            ("这么多血", "nhiều máu như vậy", Layer.BASE_MULTI),
            ("这么多", "nhiều như vậy", Layer.BASE_MULTI),
            ("多少", "bao nhiêu", Layer.BASE_MULTI),
            ("血脉", "huyết mạch", Layer.BASE_MULTI),
            ("血", "máu", Layer.BASE_SINGLE),
            ("脉", "mạch", Layer.BASE_SINGLE),
            ("有", "có", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "有多少血脉，这么多血脉").text.lower()
    assert "huyết mạch" in t
    assert "máu nhiêu" not in t
    assert "mạch" not in t.replace("huyết mạch", "")


def test_zhennei_filter_zui_patterns():
    """Khung {p}阵内 / {p}过滤阵法 — khong can khoa tung cum."""
    dic = mini(
        [
            ("聚灵", "tụ linh", Layer.BASE_MULTI),
            ("阵", "trận", Layer.BASE_SINGLE),
            ("内", "nội", Layer.BASE_SINGLE),
            ("灵气", "linh khí", Layer.BASE_MULTI),
            ("过滤", "lọc", Layer.GLOBAL_MANUAL),
            ("阵法", "trận pháp", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    t1 = vp_plan(dic, "聚灵阵内").text.lower()
    assert "trong tụ linh trận" in t1
    t2 = vp_plan(dic, "灵气过滤阵法").text.lower()
    assert "trận pháp lọc linh khí" in t2
    assert "loại bỏ" not in t2
    t3 = vp_plan(
        mini(
            [
                ("这么多", "nhiều như vậy", Layer.BASE_MULTI),
                ("多少", "bao nhiêu", Layer.BASE_MULTI),
                ("血脉", "huyết mạch", Layer.BASE_MULTI),
                ("这么多血", "nhiều máu như vậy", Layer.BASE_MULTI),
                ("多少血", "máu nhiêu", Layer.BASE_MULTI),
            ],
            context_rules(),
        ),
        "这么多血脉，有多少血脉",
    ).text.lower()
    assert "nhiều huyết mạch như vậy" in t3
    assert "bao nhiêu huyết mạch" in t3


def test_stolen_compound_does_not_split_yige_ren():
    """一个+人 khong bi 个人 (tail 人 khong bound) cat thanh mot+ca nhan."""
    dic = mini(
        [
            ("一个", "một", Layer.BASE_MULTI),
            ("个人", "cá nhân", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("一", "một", Layer.BASE_SINGLE),
            ("个", "cái", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "一个人").text.lower()
    assert "cá nhân" not in t
    assert "người" in t


def test_duoshaoxue_real_blood_kept():
    """多少血 khong phai 血脉: van 'bao nhiêu máu'."""
    dic = mini(
        [
            ("多少血脉", "bao nhiêu huyết mạch", Layer.GLOBAL_MANUAL),
            ("多少血", "bao nhiêu máu", Layer.GLOBAL_MANUAL),
            ("她昨天被放了", "nàng hôm qua bị phóng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "她昨天被放了多少血？").text.lower()
    assert "bao nhiêu máu" in t
    assert "huyết mạch" not in t


def test_stolen_compound_zaihu_not_split_by_tazai():
    """他在 (2) cuop 在 của 在乎 → 'hắn ở đây hồ'. Bound-tail 乎 drop 他在.

    在乎的 (3) dai hon 在乎: phai xet moi word 2-4, khong chi longest.
    """
    dic = mini(
        [
            ("他在", "hắn ở đây", Layer.BASE_MULTI),
            ("你在", "ngươi đang ở đây", Layer.BASE_MULTI),
            ("在乎", "quan tâm", Layer.BASE_MULTI),
            ("在乎的", "quan tâm", Layer.BASE_MULTI),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("你", "ngươi", Layer.BASE_SINGLE),
            ("在", "tại", Layer.BASE_SINGLE),
            ("乎", "hồ", Layer.BASE_SINGLE),
            ("是", "là", Layer.BASE_SINGLE),
            ("小白", "Tiểu Bạch", Layer.BASE_MULTI),
            ("吗", "sao", Layer.BASE_SINGLE),
        ]
    )
    t1 = vp_plan(dic, "他在乎的，是小白").text.lower()
    assert "quan tâm" in t1
    assert "ở đây hồ" not in t1
    assert "hồ" not in t1
    t2 = vp_plan(dic, "你在乎吗").text.lower()
    assert "quan tâm" in t2
    assert "ở đây" not in t2


def test_stolen_compound_zayi_not_split_by_tazai():
    """他在 (2) cuop 在 của 在意 → 'hắn ở đây ý'. Bound-tail 意 drop 他在."""
    dic = mini(
        [
            ("他在", "hắn ở đây", Layer.BASE_MULTI),
            ("在意", "để ý", Layer.BASE_MULTI),
            ("在意的", "để ý", Layer.BASE_MULTI),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("在", "tại", Layer.BASE_SINGLE),
            ("意", "ý", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他在意的").text.lower()
    assert "để ý" in t
    assert "ở đây" not in t


def test_tazai_end_of_clause_kept():
    """他在 het menh de van 'hắn ở đây' — khong co tu ghep tran khoi."""
    dic = mini(
        [
            ("他在", "hắn ở đây", Layer.BASE_MULTI),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("在", "tại", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他在。").text.lower()
    assert "ở đây" in t


def test_jianchi_xialai_not_noun_plus_ra_roi():
    """它坚持 (NP) cuop 坚持下来了 → 'sự kiên trì của nó ra rồi'."""
    dic = mini(
        [
            ("它坚持下来了", "nó kiên trì nổi", Layer.GLOBAL_MANUAL),
            ("它坚持", "sự kiên trì của nó", Layer.BASE_MULTI),
            ("坚持下来了", "kiên trì nổi", Layer.BASE_MULTI),
            ("下来了", "ra rồi", Layer.BASE_MULTI),
            ("它", "nó", Layer.BASE_SINGLE),
            ("坚持", "kiên trì", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "它坚持下来了").text.lower()
    assert "kiên trì nổi" in t
    assert "ra rồi" not in t
    assert "sự kiên trì" not in t


def test_huai_zhong_not_mang_of_name():
    """凌天的{p} nuot 怀; 怀中 phai thang 'mang của Lăng Thiên trong'."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("撞在了", "đụng vào", Layer.BASE_MULTI),
            ("怀中", "trong ngực", Layer.BASE_MULTI),
            ("怀", "mang", Layer.BASE_SINGLE),
            ("中", "trong", Layer.BASE_SINGLE),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "撞在了凌天的怀中").text.lower()
    assert "lòng" in t or "ngực" in t
    assert "mang" not in t


def test_lingtian_de_huaiyi_not_swallowed():
    """凌天的怀疑 van '{p} của Lăng Thiên' — khong bi 怀里."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("怀疑", "nghi ngờ", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "凌天的怀疑").text.lower()
    assert "nghi ngờ của lăng thiên" in t


def test_you_wanghou_fei_not_sau_nay():
    """又往后 (lại sau này) cuop 往后飞."""
    dic = mini(
        [
            ("又往后飞了", "lại bay về phía sau", Layer.GLOBAL_MANUAL),
            ("又往后飞", "lại bay về phía sau", Layer.GLOBAL_MANUAL),
            ("又往后", "lại sau này", Layer.BASE_MULTI),
            ("往后", "về sau", Layer.BASE_MULTI),
            ("飞了", "đã bay", Layer.BASE_MULTI),
            ("了百米", "trăm thước", Layer.BASE_MULTI),
            ("百米", "trăm mét", Layer.BASE_MULTI),
            ("后来", "về sau", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "又往后飞了百米").text.lower()
    assert "phía sau" in t
    assert "sau này" not in t
    assert "thước" not in t
    assert "trăm mét" in t
    t2 = vp_plan(dic, "后来他来了").text.lower()
    assert "về sau" in t2


def test_xiaobai_lian_shang_not_kiem():
    """小白脸 (Names) cuop 脸上 → tiểu bạch kiểm bên trên."""
    dic = mini(
        [
            ("小白脸上", "trên mặt Tiểu Bạch", Layer.GLOBAL_MANUAL),
            ("小白脸", "tiểu bạch kiểm", Layer.BASE_MULTI, 20.0),
            ("小白", "Tiểu Bạch", Layer.BASE_MULTI, 20.0),
            ("脸上", "trên mặt", Layer.BASE_MULTI),
            ("露出", "lộ ra", Layer.BASE_MULTI),
            ("笑意", "ý cười", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "小白脸上露出笑意").text.lower()
    assert "trên mặt" in t
    assert "tiểu bạch kiểm" not in t
    t2 = vp_plan(dic, "想要他做小白脸").text.lower()
    assert "tiểu bạch kiểm" in t2


def test_quan_tou_zhuang_not_pattern_swallow():
    """凌天的{p} nuot 拳头撞 → nắm đấm đụng của Lăng Thiên."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("爪子和凌天的拳头撞在了一起", "móng vuốt và nắm đấm của Lăng Thiên đụng vào nhau", Layer.GLOBAL_MANUAL),
            ("凌天的拳头撞在了一起", "nắm đấm của Lăng Thiên đụng vào nhau", Layer.GLOBAL_MANUAL),
            ("拳头", "nắm đấm", Layer.BASE_MULTI),
            ("撞在了一起", "đụng vào nhau", Layer.BASE_MULTI),
            ("在了一起", "lại với nhau", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "爪子和凌天的拳头撞在了一起").text.lower()
    assert "đụng vào nhau" in t
    assert "nắm đấm đụng của" not in t


def test_zhaozi_xiamian_not_mat():
    """爪子下 (3) cuop 下面 → leftover 面=mặt."""
    dic = mini(
        [
            ("四个爪子下面", "dưới bốn móng vuốt", Layer.GLOBAL_MANUAL),
            ("爪子下面", "dưới móng vuốt", Layer.GLOBAL_MANUAL),
            ("爪子下", "dưới móng vuốt", Layer.BASE_MULTI),
            ("下面", "phía dưới", Layer.BASE_MULTI),
            ("四个", "bốn cái", Layer.BASE_MULTI),
            ("面", "mặt", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "四个爪子下面出现一股风").text.lower()
    assert "mặt" not in t
    assert "dưới" in t


def test_pengpai_energy_not_person():
    """彭湃 person vs 彭湃的能量 typo 澎湃."""
    dic = mini(
        [
            ("彭湃的能量", "năng lượng cuồn cuộn", Layer.GLOBAL_MANUAL),
            ("彭湃", "Bành Phái", Layer.GLOBAL_MANUAL),
            ("能量", "năng lượng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "体内彭湃的能量").text.lower()
    assert "cuồn cuộn" in t
    assert "bành phái" not in t
    t2 = vp_plan(dic, "彭湃大长老").text.lower()
    assert "bành phái" in t2


def test_yiwei_zhongle_not_coi_la_trong():
    dic = mini(
        [
            ("以为中了凌天的计谋", "tưởng trúng mưu của Lăng Thiên", Layer.GLOBAL_MANUAL),
            ("以为中了", "tưởng trúng", Layer.GLOBAL_MANUAL),
            ("以为", "tưởng rằng", Layer.GLOBAL_MANUAL),
            ("中了", "trúng", Layer.GLOBAL_MANUAL),
            ("计谋", "mưu kế", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
        ]
    )
    t = vp_plan(dic, "以为中了凌天的计谋").text.lower()
    assert "trúng" in t
    assert "coi là" not in t
    assert "trong mưu" not in t


def test_yongru_lingtian_liliang_word_order():
    dic = mini(
        [
            ("涌入凌天的力量", "lực lượng tràn vào Lăng Thiên", Layer.GLOBAL_MANUAL),
            ("涌入", "tràn vào", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("力量", "lực lượng", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "涌入凌天的力量也变得更多").text.lower()
    assert "tràn vào lăng thiên" in t
    assert "tràn vào lực lượng" not in t


def test_zaichuan_not_dich_truyen():
    dic = mini(
        [
            ("再传授给", "lại truyền thụ cho", Layer.GLOBAL_MANUAL),
            ("再传", "đích truyền", Layer.BASE_MULTI),
            ("传授", "truyền thụ", Layer.BASE_MULTI),
            ("给你", "cho ngươi", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "我再传授给你妖族功法").text.lower()
    assert "đích truyền" not in t
    assert "truyền thụ" in t


def test_shuoyzhe_zouzhe_not_trailing_dang():
    dic = mini(
        [
            ("轻声说着", "nhẹ nói", Layer.GLOBAL_MANUAL),
            ("往前走着", "đi về phía trước", Layer.GLOBAL_MANUAL),
            ("轻声说", "nhẹ nói", Layer.BASE_MULTI),
            ("往前走", "đi lên phía trước", Layer.BASE_MULTI),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    assert "đang" not in vp_plan(dic, "凌天轻声说着").text.lower()
    assert "đang" not in vp_plan(dic, "往前走着").text.lower()


def test_shuiyue_lika_not_nuoc_thang():
    dic = mini(
        [
            ("离开水月的路上", "trên đường rời Thủy Nguyệt", Layer.GLOBAL_MANUAL),
            ("离开水月", "rời Thủy Nguyệt", Layer.GLOBAL_MANUAL),
            ("离开水", "rời khỏi nước", Layer.BASE_MULTI),
            ("水月", "Thủy Nguyệt", Layer.BASE_MULTI, 20.0),
            ("月的", "tháng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "离开水月的路上").text.lower()
    assert "thủy nguyệt" in t
    assert "nước" not in t
    assert "tháng" not in t


def test_shiyi_not_nay_day():
    dic = mini(
        [
            ("是以，", "vì vậy,", Layer.GLOBAL_MANUAL),
            ("是以", "này đây", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "是以，彭家的人").text.lower()
    assert "vì vậy" in t
    assert "này đây" not in t
    t2 = vp_plan(dic, "是以晶石作为货币").text.lower()
    assert "vì vậy" not in t2


def test_liangren_neijin_not_trong_hai_nguoi():
    dic = mini(
        [
            ("两人内劲初期", "hai người nội kình sơ kỳ", Layer.GLOBAL_MANUAL),
            ("内劲初期", "nội kình sơ kỳ", Layer.GLOBAL_MANUAL),
            ("两人内", "trong hai người", Layer.BASE_MULTI),
            ("内劲", "nội kình", Layer.BASE_MULTI),
            ("初期", "sơ kỳ", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "两人内劲初期").text.lower()
    assert "nội kình sơ kỳ" in t
    assert "trong hai người" not in t


def test_hengzhezou_not_di_ngang():
    dic = mini(
        [
            ("横着走都行了", "ngang nhiên muốn đi đâu cũng được", Layer.GLOBAL_MANUAL),
            ("横着走", "ngang nhiên", Layer.GLOBAL_MANUAL),
            ("都行了", "đều được", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "横着走都行了").text.lower()
    assert "ngang nhiên" in t
    assert "đi ngang" not in t


def test_duole_pengjia_not_hon_nhieu():
    dic = mini(
        [
            ("多了彭家", "có thêm Bành gia", Layer.GLOBAL_MANUAL),
            ("多了", "hơn nhiều", Layer.BASE_MULTI),
            ("彭家", "Bành gia", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "因为多了彭家").text.lower()
    assert "thêm" in t
    assert "hơn nhiều" not in t


def test_meitou_long_may():
    dic = mini(
        [
            ("眉头轻轻挑了挑", "nhướn nhẹ lông mày", Layer.GLOBAL_MANUAL),
        ]
    )
    t = vp_plan(dic, "眉头轻轻挑了挑").text.lower()
    assert "lông mày" in t


def test_yaoyou_maifu_conditional():
    dic = mini(
        [
            ("要有埋伏", "nếu có mai phục", Layer.GLOBAL_MANUAL),
            ("要有", "phải có", Layer.BASE_MULTI),
            ("埋伏", "mai phục", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "要有埋伏，我们肯定就知道了").text.lower()
    assert "nếu có" in t
    assert "phải có mai phục" not in t


def test_tazai_moshi_mianqian():
    dic = mini(
        [
            ("他在墨师面前", "hắn ở trước mặt Mặc Sư", Layer.GLOBAL_MANUAL),
            ("墨师", "Mặc Sư", Layer.BASE_MULTI, 20.0),
            ("他在", "hắn ở đây", Layer.BASE_MULTI),
            ("面前", "trước mặt", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "他在墨师面前").text.lower()
    assert "ở đây" not in t
    assert "trước mặt" in t


def test_zaibuji_not_lai_khong_tot():
    dic = mini(
        [
            ("再不济", "cùng lắm", Layer.GLOBAL_MANUAL),
            ("不济", "không tốt", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "再不济，我们也能逃走").text.lower()
    assert "cùng lắm" in t
    assert "không tốt" not in t


def test_le_after_keneng_dropped():
    dic = mini(
        [
            ("基本不可能", "cơ bản không có khả năng", Layer.BASE_MULTI),
            ("不可能了", "không thể nào", Layer.BASE_MULTI),
            ("了", "đã", Layer.BASE_SINGLE),
            ("就", "liền", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "就基本不可能了").text.lower()
    assert "đã" not in t


def test_le_before_chuqu_dropped():
    dic = mini(
        [
            ("直接飞", "bay thẳng", Layer.BASE_MULTI),
            ("飞了出去", "bay ra ngoài", Layer.BASE_MULTI),
            ("出去", "ra ngoài", Layer.BASE_MULTI),
            ("了", "đã", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "直接飞了出去").text.lower()
    assert "đã" not in t
    assert "ra ngoài" in t


def test_jiang_xiu_jian_not_sap():
    dic = mini(
        [
            ("也将锈剑收了起来", "cũng thu kiếm rỉ vào", Layer.GLOBAL_MANUAL),
            ("也将", "cũng sắp", Layer.BASE_MULTI),
            ("锈剑", "kiếm rỉ", Layer.BASE_MULTI),
            ("收了起来", "thu vào", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "也将锈剑收了起来").text.lower()
    assert "sắp" not in t
    assert "thu" in t


def test_butingzai_not_khong_dung():
    dic = mini(
        [
            ("不停在", "không ngừng ở", Layer.GLOBAL_MANUAL),
            ("不停", "không ngừng", Layer.BASE_MULTI),
            ("停", "đứng", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "不停在凌天怀中蹭着").text.lower()
    assert "không ngừng" in t
    assert "đứng" not in t


def test_yousuochi_typo():
    dic = mini(
        [
            ("仿佛由所持一样", "phảng phất như có chỗ dựa", Layer.GLOBAL_MANUAL),
            ("仿佛", "phảng phất", Layer.BASE_MULTI),
            ("由", "từ", Layer.BASE_SINGLE),
            ("所持", "cầm", Layer.BASE_MULTI),
            ("一样", "một dạng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "仿佛由所持一样").text.lower()
    assert "chỗ dựa" in t
    assert "từ cầm" not in t


def test_gujihui_not_doan_chung():
    dic = mini(
        [
            ("估计会", "chắc sẽ", Layer.GLOBAL_MANUAL),
            ("估计", "đoán chừng", Layer.BASE_MULTI),
            ("会很", "sẽ rất", Layer.BASE_MULTI),
            ("强", "mạnh", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "实力估计会很强").text.lower()
    assert "chắc sẽ" in t


def test_chedi_qijue_not_diqi():
    dic = mini(
        [
            ("彻底气绝", "chết hẳn", Layer.GLOBAL_MANUAL),
            ("底气", "lực lượng", Layer.BASE_MULTI),
            ("彻底", "triệt để", Layer.BASE_MULTI),
            ("气绝", "tắt thở", Layer.GLOBAL_MANUAL),
            ("彻", "triệt", Layer.BASE_SINGLE),
            ("绝", "tuyệt", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "彻底气绝").text.lower()
    assert "chết hẳn" in t or "tắt thở" in t
    assert "lực lượng" not in t


def test_zaidishang_not_ngoi():
    dic = mini(
        [
            ("拍死在地上", "vỗ chết trên mặt đất", Layer.GLOBAL_MANUAL),
            ("在地上", "trên mặt đất", Layer.GLOBAL_MANUAL),
            ("拍死", "chụp chết", Layer.BASE_MULTI),
            ("坐在地上", "ngồi trên mặt đất", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "拍死在地上").text.lower()
    assert "ngồi" not in t
    assert "mặt đất" in t
    t2 = vp_plan(dic, "坐在地上").text.lower()
    assert "ngồi" in t2


def test_dajia_ne_taunt_not_bare_danh_nhau():
    """打架呢 taunt != 擅长打架呢 / 喜欢打架呢."""
    dic = mini(
        [
            ("打架呢，你再想啥呢", "đang đánh nhau mà, ngươi còn nghĩ gì nữa", Layer.GLOBAL_MANUAL),
            ("你再想啥呢", "ngươi còn nghĩ gì nữa", Layer.GLOBAL_MANUAL),
            ("打架", "đánh nhau", Layer.BASE_MULTI),
            ("再想", "lại nghĩ", Layer.BASE_MULTI),
            ("啥呢", "gì chứ", Layer.BASE_MULTI),
            ("喜欢", "thích", Layer.BASE_MULTI),
            ("擅长", "sở trường", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "打架呢，你再想啥呢？").text.lower()
    assert "đang đánh nhau mà" in t
    assert "còn nghĩ gì nữa" in t
    assert "lại nghĩ" not in t
    t2 = vp_plan(dic, "怎么就喜欢打架呢").text.lower()
    assert "đang đánh nhau mà" not in t2
    assert "đánh nhau" in t2
