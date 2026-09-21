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


def test_sense_duiziji_keeps_voi():
    """对自己 giu "với" — "đối với mình cảm mến" moi dung ngu phap."""
    dic = mini([("对自己", "đối với mình", Layer.BASE_MULTI)])
    draft = vp_plan(dic, "对自己")
    low = draft.text.lower()
    assert "đối với mình" in low


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


def test_jianchi_xialai_without_long_pronoun_key():
    """Code: drop 它坚持 khi 坚持下来了 (5) tran — khong can khoa 它坚持下来了."""
    dic = mini(
        [
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


def test_xinbuguo_not_thu_cua_nang():
    """她信 (NP thư của nàng) cuop 信 của 信不过我."""
    dic = mini(
        [
            ("她信", "thư của nàng", Layer.BASE_MULTI),
            ("不过我", "bất quá ta", Layer.BASE_MULTI),
            ("信不过", "không tin được", Layer.BASE_MULTI),
            ("信不过我", "không tin được ta", Layer.BASE_MULTI),
            ("不过", "bất quá", Layer.BASE_MULTI),
            ("她", "nàng", Layer.BASE_SINGLE),
            ("信", "tin", Layer.BASE_SINGLE),
            ("我", "ta", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "她信不过我").text.lower()
    assert "không tin được" in t
    assert "thư của nàng" not in t
    assert "bất quá" not in t


def test_tamen_lai_not_split():
    """他们 + 来: 们 skip, khong cat thanh hắn + các."""
    dic = mini(
        [
            ("他们", "bọn họ", Layer.BASE_MULTI),
            ("来处理", "đến xử lý", Layer.BASE_MULTI),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("们", "các", Layer.BASE_SINGLE),
            ("来", "đến", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他们来处理").text.lower()
    assert "bọn họ" in t
    assert "hắn" not in t


def test_takan_lai_two_char_overflow_kept():
    """他看|来: overflow 看来 chi 2 chu — khong drop (min 3)."""
    dic = mini(
        [
            ("他看", "nhìn hắn", Layer.BASE_MULTI),
            ("看来", "xem ra", Layer.BASE_MULTI),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("看", "nhìn", Layer.BASE_SINGLE),
            ("来", "tới", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他看来").text.lower()
    assert "nhìn hắn" in t
    assert "xem ra" not in t


def test_pronoun_yuanyin_lai_typo_yuanxi():
    """只要她原因来: Han go 原因 (muốn 愿意) — sense đồng ý, khong nguyên nhân."""
    dic = mini(
        [
            ("只要", "chỉ cần", Layer.BASE_MULTI),
            ("她原因", "nàng nguyên nhân", Layer.BASE_MULTI),
            ("原因", "nguyên nhân", Layer.BASE_MULTI),
            ("我们公司", "công ty của chúng ta", Layer.BASE_MULTI),
            ("她", "nàng", Layer.BASE_SINGLE),
            ("来", "đến", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "只要她原因来我们公司").text.lower()
    assert "đồng ý" in t
    assert "nguyên nhân" not in t


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


def test_yigeniantou_not_trong_dau():
    dic = mini(
        [
            ("一个念头", "một ý niệm", Layer.GLOBAL_MANUAL),
            ("闪过一个念头", "vụt qua một ý niệm", Layer.GLOBAL_MANUAL),
            ("念头", "suy nghĩ", Layer.BASE_MULTI),
            ("闪过", "hiện lên", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "心底突然闪过一个念头").text.lower()
    assert "ý niệm" in t
    assert "trong đầu" not in t
    assert "niệm đầu" not in t
    t2 = vp_plan(dic, "脑海里闪过一个念头").text.lower()
    assert "vụt qua" in t2


def test_zaisu_skin_not_double_neg():
    dic = mini(
        [
            ("再无一片肌肤是没有受过伤的", "không còn mảnh da nào nguyên vẹn", Layer.GLOBAL_MANUAL),
            ("再无", "không tiếp tục", Layer.BASE_MULTI),
            ("再无聊", "lại buồn chán", Layer.BASE_MULTI),
            ("是没有", "là không có", Layer.BASE_MULTI),
            ("受过伤的", "đã bị thương", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "身上再无一片肌肤是没有受过伤的").text.lower()
    assert "nguyên vẹn" in t
    assert "chưa bị thương" not in t
    t2 = vp_plan(dic, "小胖再无聊下来").text.lower()
    assert "không còn" not in t2


def test_jilei_kept_gan_ga():
    dic = mini([("鸡肋", "gân gà", Layer.BASE_MULTI), ("实在", "thực sự", Layer.BASE_MULTI)])
    t = vp_plan(dic, "实在鸡肋").text.lower()
    assert "gân gà" in t


def test_zhejinshu_not_vang_nay_thuoc():
    dic = mini(
        [
            ("这金属", "kim loại này", Layer.GLOBAL_MANUAL),
            ("这金", "vàng này", Layer.BASE_MULTI),
            ("金属", "kim loại", Layer.BASE_MULTI),
            ("属", "thuộc", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "被这金属，刺穿了神念").text.lower()
    assert "kim loại" in t
    assert "vàng này" not in t


def test_stolen_compound_keeps_dantian_after_noun():
    """蒙面人 (3) bi 人丹 (duoi 丹) drop -> che mat + nhan dan + ruong.

    Glue last-char 2 chu khi 丹田 (2+) bat dau dung edge.end: giu NP 3+ chu.
    """
    dic = mini(
        [
            ("蒙面人", "người bịt mặt", Layer.BASE_MULTI),
            ("蒙面", "che mặt", Layer.GLOBAL_MANUAL),
            ("人丹", "nhân đan", Layer.BASE_MULTI),
            ("丹田", "đan điền", Layer.BASE_MULTI),
            ("部位", "bộ vị", Layer.BASE_MULTI),
            ("丹", "đan", Layer.BASE_SINGLE),
            ("田", "ruộng", Layer.BASE_SINGLE),
            ("人", "nhân", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "蒙面人丹田部位").text.lower()
    assert "đan điền" in t
    assert "người bịt mặt" in t
    assert "ruộng" not in t
    assert "nhân đan" not in t
    assert "che mặt" not in t


def test_rendan_kept_when_real_word():
    """人丹 that: khong phai glue truoc 丹田."""
    dic = mini(
        [
            ("人丹", "nhân đan", Layer.BASE_MULTI),
            ("一枚", "một viên", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("丹", "đan", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "一枚人丹").text.lower()
    assert "nhân đan" in t


def test_wo_clan_name_possessive():
    """灭我赵家: 我+ten X家 -> X gia cua ta, khong 'diệt ta Triệu Gia'."""
    dic = mini(
        [
            ("花家", "Hoa gia", Layer.BASE_MULTI, 20.0),
            ("赵家", "Triệu Gia", Layer.GLOBAL_MANUAL, 100.0),
            ("想要", "muốn", Layer.BASE_MULTI),
            ("灭", "diệt", Layer.BASE_SINGLE),
            ("我", "ta", Layer.BASE_SINGLE),
            ("很轻松", "rất nhẹ nhàng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "花家想要灭我赵家，很轻松").text
    low = t.lower()
    assert "triệu gia của ta" in low
    assert "diệt ta" not in low
    assert "hoa gia" in low


def test_wo_huijia_not_clan_possessive():
    """回家 la VP, khong phai ten ho: giu 'ta về nhà'."""
    dic = mini(
        [
            ("我", "ta", Layer.BASE_SINGLE),
            ("回家", "về nhà", Layer.BASE_MULTI),
            ("送", "tiễn", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "送我回家").text.lower()
    assert "về nhà" in t
    assert "của ta" not in t


def test_women_clan_name_possessive():
    """我们温家 = Ôn gia của chúng ta."""
    dic = mini(
        [
            ("我们", "chúng ta", Layer.BASE_MULTI),
            ("温家", "Ôn gia", Layer.BASE_MULTI, 20.0),
        ]
    )
    t = vp_plan(dic, "我们温家").text.lower()
    assert "ôn gia của chúng ta" in t


def test_xinzhong_not_zhongqi():
    """心中 (locative 2) khong bi 中气 (duoi 气) cat thanh tam + trung khi."""
    dic = mini(
        [
            ("心中", "trong lòng", Layer.BASE_MULTI),
            ("中气", "trung khí", Layer.BASE_MULTI),
            ("气急", "tức giận", Layer.BASE_MULTI),
            ("心", "tâm", Layer.BASE_SINGLE),
            ("中", "trung", Layer.BASE_SINGLE),
            ("气", "khí", Layer.BASE_SINGLE),
            ("急", "gấp", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "霍德华心中气急").text.lower()
    assert "trong lòng" in t
    assert "trung khí" not in t


def test_zhirenqing_not_qingren():
    """是知 cuop 知 của 知情人 → 'ấy là biết tình nhân'."""
    dic = mini(
        [
            ("是知", "ấy là biết", Layer.BASE_MULTI),
            ("知情人", "người biết chuyện", Layer.BASE_MULTI),
            ("情人", "tình nhân", Layer.BASE_MULTI),
            ("知情", "hiểu rõ tình hình", Layer.BASE_MULTI),
            ("是", "là", Layer.BASE_SINGLE),
            ("万冲", "Vạn Xung", Layer.BASE_MULTI, 20.0),
            ("只有", "chỉ có", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "只有万冲是知情人").text.lower()
    assert "người biết chuyện" in t
    assert "tình nhân" not in t
    assert "ấy là biết" not in t


def test_yaome_not_split_by_niyao():
    """你要 cuop 要 của 要么."""
    dic = mini(
        [
            ("你要", "ngươi muốn", Layer.BASE_MULTI),
            ("要么", "hoặc là", Layer.BASE_MULTI),
            ("乖乖听话", "ngoan ngoãn nghe lời", Layer.BASE_MULTI),
            ("杀了", "giết", Layer.BASE_MULTI),
            ("你", "ngươi", Layer.BASE_SINGLE),
            ("我", "ta", Layer.BASE_SINGLE),
            ("么", "a", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "你要么乖乖听话，要么我杀了你").text.lower()
    assert t.count("hoặc là") >= 2
    assert "ngươi muốn" not in t
    assert " a " not in f" {t} "


def test_renjie_not_split_jiejue():
    """人解 cuop 解 của 解决 → 'người hiểu quyết'."""
    dic = mini(
        [
            ("人解", "người hiểu", Layer.BASE_MULTI),
            ("解决", "giải quyết", Layer.BASE_MULTI),
            ("被人", "bị người", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("解", "hiểu", Layer.BASE_SINGLE),
            ("决", "quyết", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "这么轻松就被人解决").text.lower()
    assert "giải quyết" in t
    assert "hiểu quyết" not in t
    assert "người hiểu" not in t


def test_derenkou_splits_to_kouzhong():
    """的人口 cuop 口 của 口中 → 'nhân khẩu bên trong'."""
    dic = mini(
        [
            ("的人口", "nhân khẩu", Layer.BASE_MULTI),
            ("人口", "nhân khẩu", Layer.BASE_MULTI),
            ("人口中", "nhân khẩu bên trong", Layer.BASE_MULTI),
            ("口中", "trong miệng", Layer.BASE_MULTI),
            ("的人", "nhân", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("中", "bên trong", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "买凶杀人的人口中").text.lower()
    assert "trong miệng" in t
    assert "nhân khẩu" not in t


def test_shitade_hua_is_conditional():
    """是他的 + 话: 的话 dieu kien, khong 'là của hắn lời nói'."""
    dic = mini(
        [
            ("是他的", "là của hắn", Layer.BASE_MULTI),
            ("的话", "nếu", Layer.BASE_MULTI),
            ("话", "lời nói", Layer.BASE_SINGLE),
            ("是", "là", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("冒名", "mạo danh", Layer.BASE_MULTI),
            ("应该是", "hẳn là", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "是他的话，他应该是冒名了").text.lower()
    assert "lời nói" not in t
    assert "của hắn" not in t


def test_name_de_shihou_not_possessive_time():
    """凌天的{p} khong nuot 时候 → 'thời điểm của Lăng Thiên'."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("的时候", "thời điểm", Layer.BASE_MULTI),
            ("时候", "thời gian", Layer.BASE_MULTI),
            ("看向", "nhìn về phía", Layer.BASE_MULTI),
            ("再", "lại", Layer.BASE_SINGLE),
        ],
        [("凌天的{p}", "{p} của Lăng Thiên")],
    )
    t = vp_plan(dic, "再看向凌天的时候").text.lower()
    assert "lăng thiên" in t
    assert "của lăng thiên" not in t
    assert "lúc" in t


def test_name_yijing_not_da_o():
    """凌天已经 glue VP → 'Lăng Thiên đã ở'. Tach ten | 已经."""
    dic = mini(
        [
            ("凌天已经", "Lăng Thiên đã ở", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("已经", "đã", Layer.BASE_MULTI),
            ("不再管", "không quan tâm", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "凌天已经不再管什么了").text.lower()
    assert "lăng thiên" in t
    assert "đã ở" not in t
    assert "ở" not in t.replace("lăng thiên", "")


def test_le_after_dao_place_dropped():
    """到水月了: 了 sau dia danh, khong 'đã'."""
    dic = mini(
        [
            ("到", "đến", Layer.BASE_SINGLE),
            ("水月", "Thủy Nguyệt", Layer.BASE_MULTI, 20.0),
            ("了", "đã", Layer.GLOBAL_MANUAL),
            ("来", "tới", Layer.BASE_SINGLE),
        ]
    )
    assert "đã" not in vp_plan(dic, "到水月了").text.lower()
    assert "đã" in vp_plan(dic, "来了").text.lower()


def test_deren_nguoi_not_nhan():
    """的人 first-sense 'nhân' → người; {n}的人 dao ngu."""
    dic = mini(
        [
            ("花家", "Hoa gia", Layer.BASE_MULTI, 20.0),
            ("的人", "nhân", Layer.BASE_MULTI),
            ("人", "nhân", Layer.BASE_SINGLE),
            ("不是", "không phải", Layer.BASE_MULTI),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "不是花家的人").text.lower()
    assert "người" in t
    assert "nhân" not in t


def test_called_named_person_still_not_possessive():
    """{n}的人 khong pha 一个叫{n}的人."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.GLOBAL_MANUAL, 100.0),
            ("一个", "một", Layer.BASE_MULTI),
            ("叫", "gọi", Layer.BASE_SINGLE),
            ("人", "người", Layer.BASE_SINGLE),
        ],
        context_rules(),
    )
    t = vp_plan(dic, "一个叫凌天的人").text
    assert "tên Lăng Thiên" in t or "tên lăng thiên" in t.lower()
    assert "của Lăng Thiên" not in t


def test_renrenyurou_not_nham_chuc():
    """就任 cuop 任 của 任人鱼肉."""
    dic = mini(
        [
            ("就任", "nhậm chức", Layer.BASE_MULTI),
            ("任人鱼肉", "mặc người xẻ thịt", Layer.GLOBAL_MANUAL),
            ("任人", "mặc người", Layer.BASE_MULTI),
            ("人鱼", "nhân ngư", Layer.BASE_MULTI),
            ("鱼肉", "thịt cá", Layer.BASE_MULTI),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("就", "liền", Layer.BASE_SINGLE),
            ("了", "đã", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他就任人鱼肉了").text.lower()
    assert "xẻ thịt" in t
    assert "nhậm chức" not in t
    assert "nhân ngư" not in t


def test_jiezhe_phone_nhac():
    dic = mini(
        [
            ("接起", "tiếp", Layer.BASE_MULTI),
            ("电话", "điện thoại", Layer.BASE_MULTI),
            ("了", "đã", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "接起了电话").text.lower()
    assert "nhấc" in t
    assert "tiếp" not in t
    assert "đã" not in t


def test_chensizhe_not_trailing_dang():
    dic = mini(
        [
            ("低头沉思", "cúi đầu trầm tư", Layer.BASE_MULTI),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    assert "đang" not in vp_plan(dic, "低头沉思着").text.lower()


def test_rangziji_de_minh():
    dic = mini(
        [
            ("让自己", "chính để", Layer.BASE_MULTI),
            ("紧张", "khẩn trương", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "让自己紧张").text.lower()
    assert "để mình" in t
    assert "chính để" not in t


def test_rang_custom_not_entity_n_ziji():
    """Custom 让=để (dong tu) khong duoc {n}自己 → 'chính để'."""
    dic = mini(
        [
            ("让", "để", Layer.GLOBAL_MANUAL, 100.0),
            ("让自己", "để cho mình", Layer.BASE_MULTI),
            ("自己", "mình", Layer.BASE_MULTI),
            ("紧张", "khẩn trương", Layer.BASE_MULTI),
        ],
        [("{n}自己", "chính {n}")],
    )
    t = vp_plan(dic, "让自己紧张").text.lower()
    assert "chính để" not in t
    assert "để cho mình" in t or "để mình" in t


def test_name_de_noun_possessive():
    """花少的耻辱: 的 boc + ten -> sỉ nhục của Hoa thiếu."""
    dic = mini(
        [
            ("花少", "Hoa thiếu", Layer.BASE_MULTI, 20.0),
            ("耻辱", "sỉ nhục", Layer.BASE_MULTI),
            ("花", "hoa", Layer.BASE_SINGLE),
            ("少", "thiếu", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "花少的耻辱").text.lower()
    assert "sỉ nhục của hoa thiếu" in t


def test_ouyang_de_noun_possessive():
    """欧阳的麻烦 -> phiền phức của Âu Dương."""
    dic = mini(
        [
            ("欧阳", "Âu Dương", Layer.BASE_MULTI, 20.0),
            ("麻烦", "phiền phức", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "欧阳的麻烦").text.lower()
    assert "phiền phức của âu dương" in t


def test_pronoun_de_noun_possessive():
    """我的女人 -> người phụ nữ của ta."""
    dic = mini(
        [
            ("我", "ta", Layer.BASE_SINGLE),
            ("女人", "người phụ nữ", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "我的女人").text.lower()
    assert "người phụ nữ của ta" in t


def test_adj_de_not_possessive():
    """新的老师: 新 khong phai ten -> khong 'thầy của mới'."""
    dic = mini(
        [
            ("新", "mới", Layer.BASE_SINGLE),
            ("老师", "thầy", Layer.BASE_MULTI),
            ("的", "đích", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "新的老师").text.lower()
    assert "của" not in t
    assert "thầy" in t


def test_relative_de_not_possessive():
    """打不晕的凌天: ve trai dong tu, khong 'Lăng Thiên của'."""
    dic = mini(
        [
            ("打不晕", "đánh không ngất", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("打", "đánh", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "打不晕的凌天").text.lower()
    assert "của" not in t
    assert "lăng thiên" in t


def test_meiyou_not_stolen_by_youdiyi():
    """没有 bi 有敌意 (duoi 意) drop -> không có + có địch ý."""
    dic = mini(
        [
            ("没有", "không có", Layer.BASE_MULTI),
            ("有敌意", "có địch ý", Layer.BASE_MULTI),
            ("敌意", "địch ý", Layer.BASE_MULTI),
            ("我", "ta", Layer.BASE_SINGLE),
            ("没", "không có", Layer.BASE_SINGLE),
            ("有", "có", Layer.BASE_SINGLE),
            ("意", "ý", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "我没有敌意").text.lower()
    assert "không có địch ý" in t
    assert "có có" not in t


def test_wo_bu_suan_not_khong_co_tinh():
    """我不 cuop 不 của 不算."""
    dic = mini(
        [
            ("我不", "ta không có", Layer.BASE_MULTI),
            ("不算", "không tính", Layer.BASE_MULTI),
            ("我", "ta", Layer.BASE_SINGLE),
            ("不", "không", Layer.BASE_SINGLE),
            ("算", "tính", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "我不算").text.lower()
    assert "không tính" in t
    assert "không có" not in t


def test_hui_after_number_is_hoi():
    """十会: hoi, khong future se."""
    dic = mini(
        [
            ("一力", "dốc hết sức", Layer.BASE_MULTI),
            ("斩", "trảm", Layer.BASE_SINGLE),
            ("十", "mười", Layer.BASE_SINGLE),
            ("会", "sẽ", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "一力斩十会").text.lower()
    assert "hội" in t
    assert "sẽ" not in t


def test_hui_future_still_se():
    """明天会来 van se."""
    dic = mini(
        [
            ("明天", "ngày mai", Layer.BASE_MULTI),
            ("会", "hội", Layer.BASE_SINGLE),
            ("来", "đến", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "明天会来").text.lower()
    assert "sẽ" in t
    assert "hội" not in t


def test_daikezhidao_not_dao_dai_khach():
    dic = mini(
        [
            ("待客之道", "cách đãi khách", Layer.GLOBAL_MANUAL, 100.0),
            ("待客", "đãi khách", Layer.BASE_MULTI),
            ("之道", "chi đạo", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "不懂待客之道").text.lower()
    assert "cách đãi khách" in t
    assert "đạo đãi khách" not in t


def test_xingshiwenzi_not_hung_su():
    dic = mini(
        [
            ("兴师问罪", "kéo quân hỏi tội", Layer.GLOBAL_MANUAL, 100.0),
            ("兴师", "khởi binh", Layer.BASE_MULTI),
            ("问罪", "hỏi tội", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "过来兴师问罪").text.lower()
    assert "kéo quân hỏi tội" in t
    assert "hưng sư" not in t


def test_fengbo_song_gio_not_phong_ba():
    dic = mini(
        [
            ("风波", "sóng gió", Layer.GLOBAL_MANUAL, 100.0),
            ("玩具枪风波", "sóng gió súng đồ chơi", Layer.GLOBAL_MANUAL, 100.0),
            ("玩具枪", "súng đồ chơi", Layer.BASE_MULTI),
            ("一场", "một trận", Layer.BASE_MULTI),
        ]
    )
    t1 = vp_plan(dic, "玩具枪风波").text.lower()
    assert "sóng gió súng đồ chơi" in t1
    assert "phong ba" not in t1
    t2 = vp_plan(dic, "一场风波").text.lower()
    assert "một trận sóng gió" in t2
    assert "phong ba" not in t2


def test_woqu_chuiniu_title():
    dic = mini(
        [
            ("我去吹牛", "ta đi chém gió", Layer.GLOBAL_MANUAL, 100.0),
            ("我去", "ta đi", Layer.BASE_MULTI),
            ("吹牛", "khoác lác", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "我去吹牛").text.lower()
    assert "chém gió" in t
    assert "khoác lác" not in t


def test_jiudao_before_quote_is_noi():
    """就道=lên đường, truoc ngoac thoai phai 'nói'."""
    dic = mini(
        [
            ("就道", "lên đường", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("就", "liền", Layer.BASE_SINGLE),
            ("道", "đạo", Layer.BASE_SINGLE),
            ("烤肉串", "que thịt nướng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "凌天就道：“烤肉串").text.lower()
    assert "nói" in t
    assert "lên đường" not in t


def test_jiudao_without_quote_kept():
    dic = mini(
        [
            ("就道", "lên đường", Layer.BASE_MULTI),
            ("我们", "chúng ta", Layer.BASE_MULTI),
            ("了", "đã", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "我们就道了").text.lower()
    assert "lên đường" in t


def test_dui_name_de_noun_attitude():
    """对凌天的尊敬 = tôn kính đối với Lăng Thiên, khong 'đối tôn kính của'."""
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("是对", "là đối", Layer.BASE_MULTI),
            ("尊敬", "tôn kính", Layer.BASE_MULTI),
            ("是", "là", Layer.BASE_SINGLE),
            ("对", "đối", Layer.BASE_SINGLE),
        ],
        [("对{n}的{p}", "{p} đối với {n}")],
    )
    t = vp_plan(dic, "是对凌天的尊敬").text.lower()
    assert "tôn kính đối với lăng thiên" in t
    assert "đối tôn kính" not in t


def test_dashengpaoxiao_not_english():
    dic = mini(
        [
            ("大声咆哮", "gào thét", Layer.GLOBAL_MANUAL, 100.0),
            ("大声咆哮", "Snarl", Layer.BASE_MULTI),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他大声咆哮着").text.lower()
    assert "gào thét" in t
    assert "snarl" not in t


def test_chi_dongxi_eat():
    dic = mini(
        [
            ("先吃东西", "ăn trước", Layer.GLOBAL_MANUAL, 100.0),
            ("吃东西", "ăn", Layer.GLOBAL_MANUAL, 100.0),
            ("先吃", "ăn trước", Layer.BASE_MULTI),
            ("东西", "đồ vật", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "先吃东西").text.lower()
    assert "ăn trước" in t
    assert "đồ vật" not in t


def test_yanwudan_not_split_by_nayenwu():
    dic = mini(
        [
            ("那烟雾", "sương khói kia", Layer.BASE_MULTI),
            ("烟雾弹", "bom khói", Layer.BASE_MULTI),
            ("那", "kia", Layer.BASE_SINGLE),
            ("弹", "đạn", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "那烟雾弹").text.lower()
    assert "bom khói" in t
    assert "đạn" not in t
    assert "sương khói kia" not in t


def test_paoxiao_zhe_drops_dang():
    dic = mini(
        [
            ("大声咆哮", "gào thét", Layer.GLOBAL_MANUAL, 100.0),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "他大声咆哮着").text.lower()
    assert "gào thét" in t
    assert "đang" not in t


def test_chuan_after_number_is_xien():
    dic = mini(
        [
            ("一百", "một trăm", Layer.BASE_MULTI),
            ("二十", "hai mươi", Layer.BASE_MULTI),
            ("串", "xuyên", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "一百串").text.lower()
    assert "xiên" in t
    assert "xuyên" not in t


def test_qugen_not_split_genzhe():
    """去跟 cuop 跟 của 跟着 → 'đi cùng đang'."""
    dic = mini(
        [
            ("跟着", "đi theo", Layer.BASE_MULTI),
            ("去跟", "đi cùng", Layer.BASE_MULTI),
            ("雅樱姐姐", "Nhã Anh tỷ tỷ", Layer.BASE_MULTI, 20.0),
            ("让我", "để cho ta", Layer.BASE_MULTI),
            ("去", "đi", Layer.BASE_SINGLE),
            ("跟", "cùng", Layer.BASE_SINGLE),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "让我去跟着雅樱姐姐").text.lower()
    assert "đi theo" in t
    assert "cùng đang" not in t
    dic2 = mini(
        [
            ("跟着我", "đi theo ta", Layer.BASE_MULTI),
            ("跟着", "đi theo", Layer.BASE_MULTI),
            ("看着我", "nhìn ta", Layer.BASE_MULTI),
            ("我", "ta", Layer.BASE_SINGLE),
        ]
    )
    assert "đi theo ta" in vp_plan(dic2, "跟着我").text.lower()
    assert "nhìn ta" in vp_plan(dic2, "看着我").text.lower()


def test_place_de_evening_youtian():
    """桐城的晚上有点冷: 晚上有 cuop 有点; 的+time dung 'ở'."""
    dic = mini(
        [
            ("桐城", "Đồng Thành", Layer.BASE_MULTI, 20.0),
            ("晚上有", "buổi tối có", Layer.BASE_MULTI),
            ("有点冷", "có chút lạnh", Layer.BASE_MULTI),
            ("有点", "có chút", Layer.BASE_MULTI),
            ("晚上", "ban đêm", Layer.BASE_MULTI),
            ("点冷", "chút lạnh", Layer.BASE_MULTI),
            ("耻辱", "sỉ nhục", Layer.BASE_MULTI),
            ("花少", "Hoa thiếu", Layer.BASE_MULTI, 20.0),
        ]
    )
    t = vp_plan(dic, "桐城的晚上有点冷").text.lower()
    assert "ở đồng thành" in t
    assert "của" not in t
    assert "buổi tối có" not in t
    t2 = vp_plan(dic, "花少的耻辱").text.lower()
    assert "sỉ nhục của hoa thiếu" in t2


def test_wucaibinfen_not_ngu_thai():
    dic = mini(
        [
            ("五彩缤纷", "rực rỡ muôn màu", Layer.GLOBAL_MANUAL, 100.0),
            ("五彩缤纷", "ngũ thải tân phân", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "五彩缤纷").text.lower()
    assert "rực rỡ" in t
    assert "ngũ thải" not in t


def test_zaichi_zhe_dongxi():
    dic = mini(
        [
            ("吃着东西", "đang ăn", Layer.GLOBAL_MANUAL, 100.0),
            ("在吃", "đang ăn", Layer.BASE_MULTI),
            ("东西", "đồ vật", Layer.BASE_MULTI),
            ("在", "ở", Layer.BASE_SINGLE),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "在吃着东西").text.lower()
    assert "đang ăn" in t
    assert "đồ vật" not in t
    assert t.count("đang") == 1


def test_haiyaochi_not_split_chidongxi():
    """还要吃 cuop 吃 của 吃东西."""
    dic = mini(
        [
            ("吃东西", "ăn", Layer.GLOBAL_MANUAL, 100.0),
            ("还要吃", "còn muốn ăn", Layer.BASE_MULTI),
            ("东西", "đồ vật", Layer.BASE_MULTI),
            ("我们", "chúng ta", Layer.BASE_MULTI),
            ("还要", "còn muốn", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "我们还要吃东西").text.lower()
    assert "ăn" in t
    assert "đồ vật" not in t


def test_xingshiwenzi_de_tail_not_hung_su():
    """兴师问罪的 (5) nuot Custom 4 chu."""
    dic = mini(
        [
            ("兴师问罪", "kéo quân hỏi tội", Layer.GLOBAL_MANUAL, 100.0),
            ("兴师问罪的", "hưng sư vấn tội", Layer.BASE_MULTI),
            ("过来", "tới", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "过来兴师问罪的").text.lower()
    assert "kéo quân hỏi tội" in t
    assert "hưng sư" not in t


def test_mudengkoudai_zhe_drops_dang():
    dic = mini(
        [
            ("目瞪口呆", "trợn mắt hốc mồm", Layer.BASE_MULTI),
            ("着", "đang", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "目瞪口呆着").text.lower()
    assert "trợn mắt hốc mồm" in t
    assert "đang" not in t


def test_haoxiang_yiban_drops_binh_thuong():
    dic = mini(
        [
            ("这好像", "cái này thật giống như", Layer.BASE_MULTI),
            ("成年人", "người trưởng thành", Layer.BASE_MULTI),
            ("一般", "bình thường", Layer.BASE_MULTI),
            ("是", "là", Layer.BASE_SINGLE),
            ("两个", "hai cái", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "这好像是两个成年人一般").text.lower()
    assert "bình thường" not in t
    assert "giống như" in t


def test_meichen_jie_name():
    dic = mini(
        [
            ("美辰姐", "Mỹ Thần tỷ", Layer.SERIES_MANUAL, 1000.0),
            ("美", "đẹp", Layer.BASE_SINGLE),
            ("姐", "tỷ", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "美辰姐").text
    assert "Mỹ Thần tỷ" in t
    assert "đẹp" not in t.lower()


def test_hua_shao_chi_nhuc_still_cua():
    dic = mini(
        [
            ("花少", "Hoa thiếu", Layer.BASE_MULTI, 20.0),
            ("耻辱", "sỉ nhục", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "花少的耻辱").text.lower()
    assert "sỉ nhục của hoa thiếu" in t


def test_haosi_yiban_drops_binh_thuong():
    dic = mini(
        [
            ("好似被", "thật giống như bị", Layer.BASE_MULTI),
            ("冰水", "nước đá", Layer.BASE_MULTI),
            ("一般", "bình thường", Layer.BASE_MULTI),
            ("泼了", "giội cho", Layer.BASE_MULTI),
            ("人", "người", Layer.BASE_SINGLE),
            ("盆", "bồn", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "好似被人泼了盆冰水一般").text.lower()
    assert "bình thường" not in t
    assert "giống như" in t


def test_rangren_qu_is_bao_nguoi():
    dic = mini(
        [
            ("让人", "làm cho người ta", Layer.BASE_MULTI),
            ("去查", "đi thăm dò", Layer.BASE_MULTI),
            ("去", "đi", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "让人去查").text.lower()
    assert "bảo người" in t
    assert "làm cho người ta" not in t


def test_yiba_noun_not_thanh():
    dic = mini(
        [
            ("一把", "một thanh", Layer.BASE_MULTI),
            ("红蛤蟆", "cóc đỏ", Layer.GLOBAL_MANUAL, 100.0),
            ("拿出", "xuất ra", Layer.BASE_MULTI),
            ("刀", "đao", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "拿出一把红蛤蟆").text.lower()
    assert "thanh" not in t
    assert "cóc đỏ" in t
    t2 = vp_plan(dic, "一把刀").text.lower()
    assert "thanh" in t2


def test_zunyan_wenti_inverts():
    dic = mini(
        [
            ("尊严", "tôn nghiêm", Layer.BASE_MULTI),
            ("问题", "vấn đề", Layer.BASE_MULTI),
        ],
        [("{p}问题", "vấn đề {p}")],
    )
    t = vp_plan(dic, "尊严问题").text.lower()
    assert "vấn đề tôn nghiêm" in t


def test_yunling_zhuangyuan_nei():
    dic = mini(
        [
            ("云岭庄园", "Vân Lĩnh Trang Viên", Layer.SERIES_MANUAL, 1000.0),
            ("庄园内", "trong trang viên", Layer.BASE_MULTI),
            ("云岭", "Vân Lĩnh", Layer.BASE_MULTI, 20.0),
            ("内", "nội", Layer.BASE_SINGLE),
        ],
        [("{n}内", "trong {n}")],
    )
    t = vp_plan(dic, "云岭庄园内").text.lower()
    assert "trong vân lĩnh trang viên" in t
    assert t.index("trong") < t.index("vân")


def test_cao_swear_in_quote():
    dic = mini(
        [
            ("草", "cỏ", Layer.BASE_SINGLE),
            ("邵哥", "Thiệu ca", Layer.BASE_MULTI, 20.0),
        ]
    )
    t = vp_plan(dic, "“草！”").text.lower()
    assert "đm" in t
    assert "cỏ" not in t


def test_nazhi_hand_not_con_kia():
    dic = mini(
        [
            ("那只", "con kia", Layer.BASE_MULTI),
            ("将自己", "đem chính mình", Layer.BASE_MULTI),
            ("丢出来的", "ném ra tới", Layer.BASE_MULTI),
            ("手", "tay", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "那只将自己丢出来的手").text.lower()
    assert "con kia" not in t
    assert "tay" in t


def test_kaichu_road_not_mo_ra():
    dic = mini(
        [
            ("开出了", "mở ra", Layer.GLOBAL_MANUAL, 100.0),
            ("梧桐路", "Ngô Đồng Lộ", Layer.BASE_MULTI, 20.0),
            ("一条大道", "một đại đạo", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "开出了梧桐路").text.lower()
    assert "lái ra khỏi" in t
    assert "mở ra" not in t
    t2 = vp_plan(dic, "开出了一条大道").text.lower()
    assert "mở ra" in t2
    assert "lái ra khỏi" not in t2


def test_dui_name_ke_khach():
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("对", "đối", Layer.BASE_SINGLE),
            ("各种", "các loại", Layer.BASE_MULTI),
            ("客气", "khách khí", Layer.BASE_MULTI),
        ],
        [("对{n}各种客气", "rất khách khí với {n}")],
    )
    t = vp_plan(dic, "对凌天各种客气").text.lower()
    assert "khách khí với lăng thiên" in t
    assert "đối lăng thiên" not in t


def test_jiang_diu_shou_relative():
    dic = mini(
        [
            ("那只", "con kia", Layer.BASE_MULTI),
            ("将自己", "đem chính mình", Layer.BASE_MULTI),
            ("丢出来的", "ném ra tới", Layer.BASE_MULTI),
            ("手", "tay", Layer.BASE_SINGLE),
            ("自己", "chính mình", Layer.BASE_MULTI),
        ],
        [("将{p}丢出来的手", "tay đã ném {p} ra")],
    )
    t = vp_plan(dic, "那只将自己丢出来的手").text.lower()
    assert "tay đã ném" in t
    assert "con kia" not in t
    assert "ném ra tới" not in t


def test_youhuo_not_oh_yeah():
    dic = mini(
        [
            ("哟嚯", "oh yeah", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "哟嚯").text.lower()
    assert "ối" in t
    assert "yeah" not in t


def test_bazhang_yinji_not_nho():
    dic = mini(
        [
            ("巴掌印记", "dấu tát", Layer.GLOBAL_MANUAL, 100.0),
            ("巴掌印", "dấu bàn tay", Layer.BASE_MULTI),
            ("印记", "dấu", Layer.GLOBAL_MANUAL, 100.0),
            ("记", "nhớ", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "巴掌印记").text.lower()
    assert "dấu tát" in t
    assert "nhớ" not in t


def test_yuanrun_not_split_nayuan():
    dic = mini(
        [
            ("圆润", "mượt mà", Layer.BASE_MULTI),
            ("那圆", "viên kia", Layer.BASE_MULTI),
            ("屁股", "cái mông", Layer.BASE_MULTI),
            ("那", "kia", Layer.BASE_SINGLE),
        ],
        [("{p}的屁股", "cái mông {p}")],
    )
    t = vp_plan(dic, "那圆润的屁股").text.lower()
    assert "mượt mà" in t
    assert "viên kia" not in t


def test_nu_pengyou_not_split():
    dic = mini(
        [
            ("女朋友", "bạn gái", Layer.BASE_MULTI),
            ("小女朋友", "bạn gái nhỏ", Layer.GLOBAL_MANUAL, 100.0),
            ("那小女", "vậy tiểu nữ", Layer.BASE_MULTI),
            ("朋友", "bằng hữu", Layer.BASE_MULTI),
            ("你", "ngươi", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "你那小女朋友").text.lower()
    assert "bạn gái" in t
    assert "bằng hữu" not in t


def test_liangge_keneng_is_kha_nang():
    dic = mini(
        [
            ("可能", "có thể", Layer.GLOBAL_MANUAL, 25.0),
            ("两个", "hai cái", Layer.BASE_MULTI),
            ("可能会", "có thể sẽ", Layer.BASE_MULTI),
            ("来", "đến", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "两个可能").text.lower()
    assert "khả năng" in t
    t2 = vp_plan(dic, "可能会来").text.lower()
    assert "có thể" in t2


def test_pinle_ge_zhuozi_is_ghep():
    dic = mini(
        [
            ("拼了", "liều mạng", Layer.BASE_MULTI),
            ("桌子", "cái bàn", Layer.BASE_MULTI),
            ("个", "cái", Layer.BASE_SINGLE),
            ("给", "cho", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "给拼了个桌子").text.lower()
    assert "ghép" in t
    assert "liều mạng" not in t


def test_yidun_pili_is_mot_tran():
    dic = mini(
        [
            ("一顿", "dừng lại", Layer.BASE_MULTI),
            ("噼里啪啦", "lốp bốp", Layer.BASE_MULTI),
            ("一顿饭", "một bữa cơm", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "一顿噼里啪啦").text.lower()
    assert "một trận" in t
    assert "dừng lại" not in t
    t2 = vp_plan(dic, "一顿饭").text.lower()
    assert "bữa" in t2


def test_cheting_le_xialai_not_di():
    dic = mini(
        [
            ("车停", "đậu xe", Layer.BASE_MULTI),
            ("停了下来", "ngừng lại", Layer.BASE_MULTI),
            ("了下来", "đi", Layer.BASE_MULTI),
            ("一群人", "một đám người", Layer.BASE_MULTI),
            ("坐了下来", "ngồi xuống", Layer.BASE_MULTI),
            ("车", "xe", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "车停了下来").text.lower()
    assert "ngừng lại" in t
    assert "đi" not in t
    t2 = vp_plan(dic, "一群人停了下来").text.lower()
    assert "ngừng lại" in t2
    t3 = vp_plan(dic, "坐了下来").text.lower()
    assert "ngồi xuống" in t3


def test_qibao_not_khi_bao():
    dic = mini(
        [
            ("气爆了", "khí bạo", Layer.BASE_MULTI),
            ("气爆", "khí bạo", Layer.BASE_MULTI),
            ("让", "để", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "让他气爆了").text.lower()
    assert "nổi giận" in t
    assert "khí bạo" not in t


def test_haiyihou_is_con_co():
    dic = mini(
        [
            ("还以后", "còn có", Layer.GLOBAL_MANUAL, 100.0),
            ("还以", "còn lấy", Layer.BASE_MULTI),
            ("炒菜", "xào rau", Layer.BASE_MULTI),
            ("后", "sau", Layer.BASE_SINGLE),
            ("还有", "còn có", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "还以后炒菜").text.lower()
    assert "còn có" in t
    assert "còn lấy" not in t
    t2 = vp_plan(dic, "还有炒菜").text.lower()
    assert "còn có" in t2


def test_daxiao_de_is_co():
    dic = mini(
        [
            ("一个成年人", "một người trưởng thành", Layer.BASE_MULTI),
            ("大小的", "lớn nhỏ", Layer.BASE_MULTI),
            ("巴掌印记", "dấu tát", Layer.GLOBAL_MANUAL, 100.0),
            ("成年人", "người trưởng thành", Layer.BASE_MULTI),
        ],
        [("一个{p}大小的{p}", "một {2} cỡ {1}")],
    )
    t = vp_plan(dic, "一个成年人大小的巴掌印记").text.lower()
    assert "dấu tát cỡ người trưởng thành" in t
    assert "lớn nhỏ" not in t


def test_buteng_is_khong_dau():
    dic = mini(
        [
            ("不疼", "không thương", Layer.BASE_MULTI),
            ("疼", "đau", Layer.BASE_SINGLE),
            ("我保证", "ta bảo đảm", Layer.BASE_MULTI),
            ("你", "ngươi", Layer.BASE_SINGLE),
            ("还疼", "còn đau", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "我保证你不疼").text.lower()
    assert "không đau" in t
    assert "thương" not in t
    t2 = vp_plan(dic, "还疼").text.lower()
    assert "đau" in t2


def test_zuncong_is_tuan_theo():
    dic = mini(
        [
            ("尊从", "tuân theo", Layer.GLOBAL_MANUAL, 100.0),
            ("尊", "tôn", Layer.BASE_SINGLE),
            ("从", "từ", Layer.BASE_SINGLE),
            ("必须要", "nhất định phải", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "必须要尊从").text.lower()
    assert "tuân theo" in t
    assert "tôn từ" not in t


def test_dinglexialai_is_chot_lai():
    dic = mini(
        [
            ("定了下来", "chốt lại", Layer.GLOBAL_MANUAL, 100.0),
            ("定了", "định rồi", Layer.BASE_MULTI),
            ("下来", "xuống tới", Layer.BASE_MULTI),
            ("事情", "chuyện", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "事情定了下来").text.lower()
    assert "chốt lại" in t
    assert "xuống tới" not in t


def test_lulexialai_is_lot_xuong():
    dic = mini(
        [
            ("撸了下来", "lột xuống", Layer.GLOBAL_MANUAL, 100.0),
            ("撸了", "lột", Layer.BASE_MULTI),
            ("下来", "xuống tới", Layer.BASE_MULTI),
            ("烤串", "xâu nướng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "烤串撸了下来").text.lower()
    assert "lột xuống" in t
    assert "xuống tới" not in t
    dic2 = mini(
        [
            ("停了下来", "ngừng lại", Layer.BASE_MULTI),
            ("车停", "đậu xe", Layer.BASE_MULTI),
            ("了下来", "đi", Layer.BASE_MULTI),
            ("车", "xe", Layer.BASE_SINGLE),
        ]
    )
    t2 = vp_plan(dic2, "车停了下来").text.lower()
    assert "ngừng lại" in t2


def test_xialai_drops_toi():
    dic = mini(
        [
            ("下来", "xuống tới", Layer.BASE_MULTI),
            ("打电话", "gọi điện thoại", Layer.BASE_MULTI),
            ("定了", "định rồi", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "打电话下来").text.lower()
    assert "xuống" in t
    assert "tới" not in t


def test_rangren_ding_is_bao_nguoi():
    dic = mini(
        [
            ("让人", "làm cho người ta", Layer.BASE_MULTI),
            ("盯着点", "để ý", Layer.GLOBAL_MANUAL, 100.0),
            ("盯着", "nhìn chằm chằm", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "你让人盯着点").text.lower()
    assert "bảo người" in t
    assert "làm cho người ta" not in t


def test_pengyou_is_ban():
    dic = mini(
        [
            ("朋友", "bạn", Layer.GLOBAL_MANUAL, 100.0),
            ("朋友", "bằng hữu", Layer.BASE_MULTI),
            ("说一声", "nói một tiếng", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "朋友说一声").text.lower()
    assert "bạn" in t
    assert "bằng hữu" not in t


def test_de_pengyou_strips_bang_huu():
    dic = mini(
        [
            ("的朋友", "bằng hữu của", Layer.BASE_MULTI),
            ("我的朋友", "bạn của ta", Layer.BASE_MULTI),
            ("朋友", "bạn", Layer.GLOBAL_MANUAL, 100.0),
            ("打了", "đánh cho", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "打了我的朋友").text.lower()
    assert "bằng hữu" not in t
    assert "bạn" in t


def test_linglong_quan_tou_not_vien_linh_lung():
    dic = mini(
        [
            ("一颗", "một viên", Layer.BASE_MULTI),
            ("玲珑", "linh lung", Layer.BASE_MULTI),
            ("拳头", "nắm đấm", Layer.BASE_MULTI),
            ("玲珑拳头", "nắm đấm nhỏ", Layer.GLOBAL_MANUAL, 100.0),
        ]
    )
    t = vp_plan(dic, "一颗玲珑拳头").text.lower()
    assert "viên" not in t
    assert "nắm đấm" in t
    assert "linh lung" not in t


def test_xiaoniangmen_tamadang():
    dic = mini(
        [
            ("小娘们", "con nhỏ", Layer.GLOBAL_MANUAL, 100.0),
            ("还他妈", "còn đm", Layer.GLOBAL_MANUAL, 100.0),
            ("他妈的", "đm", Layer.GLOBAL_MANUAL, 100.0),
            ("敢", "dám", Layer.BASE_SINGLE),
            ("仙女", "tiên nữ", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "小娘们还他妈敢").text.lower()
    assert "con nhỏ" in t
    assert "còn đm" in t
    assert "nương môn" not in t
    assert "mẹ hắn" not in t
    t2 = vp_plan(dic, "他妈的仙女").text.lower()
    assert "đm" in t2
    assert "mẹ nhà hắn" not in t2


def test_duizhe_lian_da_guolai():
    dic = mini(
        [
            ("对着自己", "chính đối với", Layer.BASE_MULTI),
            ("的脸", "mặt của", Layer.BASE_MULTI),
            ("打了过来", "đánh tới", Layer.BASE_MULTI),
            ("自己", "mình", Layer.BASE_MULTI),
            ("拳头", "nắm đấm", Layer.BASE_MULTI),
        ],
        [("对着{p}的脸打了过来", "đánh vào mặt {p}")],
    )
    t = vp_plan(dic, "拳头对着自己的脸打了过来").text.lower()
    assert "đánh vào mặt mình" in t
    assert "đối với mặt của" not in t


def test_ni_na_xiaonvpengyou_order():
    dic = mini(
        [
            ("小女朋友", "bạn gái nhỏ", Layer.GLOBAL_MANUAL, 100.0),
            ("你", "ngươi", Layer.BASE_SINGLE),
            ("那", "kia", Layer.BASE_SINGLE),
            ("被人欺负了", "bị người khi dễ", Layer.BASE_MULTI),
        ],
        [("你那{p}", "{p} kia của ngươi")],
    )
    t = vp_plan(dic, "你那小女朋友被人欺负了").text.lower()
    assert "bạn gái nhỏ kia của ngươi" in t
    assert t.index("bạn gái") < t.index("kia")


def test_weixie_qi_wo_laile_not_toi_da():
    dic = mini(
        [
            ("威胁起", "uy hiếp", Layer.BASE_MULTI),
            ("我来", "ta tới", Layer.BASE_MULTI),
            ("来了", "đã đến", Layer.BASE_MULTI),
            ("我", "ta", Layer.BASE_SINGLE),
            ("了", "đã", Layer.BASE_SINGLE),
            ("他", "hắn", Layer.BASE_SINGLE),
            ("记起来了", "nhớ ra rồi", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "威胁起我来了").text.lower()
    assert "uy hiếp ta" in t
    assert "tới" not in t
    t2 = vp_plan(dic, "他来了").text.lower()
    assert "đã đến" in t2
    t3 = vp_plan(dic, "记起来了").text.lower()
    assert "nhớ ra rồi" in t3


def test_nadaoguo_is_tung_gianh():
    dic = mini(
        [
            ("拿到", "cầm tới", Layer.BASE_MULTI),
            ("过", "rồi", Layer.BASE_SINGLE),
            ("第一名", "hạng nhất", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "拿到过第一名").text.lower()
    assert "từng giành" in t
    assert "cầm tới" not in t
    assert "rồi" not in t


def test_chuchulai_is_ra():
    dic = mini(
        [
            ("出出来", "ra", Layer.GLOBAL_MANUAL, 100.0),
            ("出出来的", "ra", Layer.GLOBAL_MANUAL, 100.0),
            ("出出", "xuất một chút", Layer.BASE_MULTI),
            ("来的", "tới", Layer.BASE_MULTI),
            ("小学题目", "đề bài tiểu học", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "出出来的小学题目").text.lower()
    assert "ra" in t
    assert "tới" not in t
    assert "xuất một chút" not in t


def test_kaotimu_not_mat():
    dic = mini(
        [
            ("考题目", "đề thi", Layer.GLOBAL_MANUAL, 100.0),
            ("题目", "đề bài", Layer.GLOBAL_MANUAL, 100.0),
            ("考题", "khảo đề", Layer.BASE_MULTI),
            ("目", "mắt", Layer.BASE_SINGLE),
            ("所谓", "cái gọi là", Layer.BASE_MULTI),
            ("这个", "cái này", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "所谓考题目这个").text.lower()
    assert "mắt" not in t
    assert "đề" in t


def test_hexini_de_fangshi_inverts():
    dic = mini(
        [
            ("和稀泥", "ba phải", Layer.BASE_MULTI),
            ("的方式", "phương thức", Layer.BASE_MULTI),
            ("方式", "phương thức", Layer.BASE_MULTI),
            ("以", "lấy", Layer.BASE_SINGLE),
            ("这样", "dạng này", Layer.BASE_MULTI),
            ("解决", "giải quyết", Layer.BASE_MULTI),
            ("事情", "chuyện", Layer.BASE_MULTI),
            ("和稀泥的方式", "cách ba phải", Layer.GLOBAL_MANUAL, 100.0),
            ("以这样和稀泥的方式", "theo cách ba phải", Layer.GLOBAL_MANUAL, 100.0),
        ],
        [
            ("{p}的方式", "cách {p}"),
            ("以这样{p}的方式", "theo cách {p}"),
        ],
    )
    t = vp_plan(dic, "以这样和稀泥的方式解决事情").text.lower()
    assert "theo cách ba phải" in t or "cách ba phải" in t
    assert "ba phải phương thức" not in t


def test_jiejie_de_zhuren_inverts():
    dic = mini(
        [
            ("是她姐姐", "là tỷ tỷ của nàng", Layer.BASE_MULTI),
            ("是她", "là nàng", Layer.BASE_MULTI),
            ("她姐姐", "tỷ tỷ nàng", Layer.BASE_MULTI),
            ("她姐姐的主人", "chủ nhân của tỷ tỷ nàng", Layer.GLOBAL_MANUAL, 100.0),
            ("姐姐", "tỷ tỷ", Layer.BASE_MULTI),
            ("主人", "chủ nhân", Layer.BASE_MULTI),
            ("是", "là", Layer.BASE_SINGLE),
            ("她", "nàng", Layer.BASE_SINGLE),
        ],
        [("{p}的主人", "chủ nhân của {p}")],
    )
    t = vp_plan(dic, "是她姐姐的主人").text.lower()
    assert "chủ nhân của tỷ tỷ" in t
    assert "nàng chủ nhân" not in t
    assert t.index("chủ nhân") < t.index("tỷ")
    t2 = vp_plan(dic, "她的主人").text.lower()
    assert "chủ nhân của nàng" in t2
    assert "nàng chủ nhân" not in t2


def test_baohu_lingtian_de_ren():
    dic = mini(
        [
            ("保护", "bảo hộ", Layer.BASE_MULTI),
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("凌天的人", "người của Lăng Thiên", Layer.BASE_MULTI),
        ],
        [("保护{n}的人", "người bảo vệ {n}")],
    )
    t = vp_plan(dic, "保护凌天的人").text.lower()
    assert "người bảo vệ lăng thiên" in t
    assert "người của lăng thiên" not in t


def test_zhuoshang_de_ren():
    dic = mini(
        [
            ("几个桌子", "mấy cái bàn", Layer.BASE_MULTI),
            ("上的人", "người trên", Layer.BASE_MULTI),
            ("桌子", "bàn", Layer.BASE_MULTI),
        ],
        [("几个{p}上的人", "người trên mấy cái {p}")],
    )
    t = vp_plan(dic, "几个桌子上的人").text.lower()
    assert "người trên mấy cái bàn" in t
    assert "bàn người trên" not in t


def test_gei_ta_de_zhuren_dadianhua():
    dic = mini(
        [
            ("给她的", "cho nàng", Layer.BASE_MULTI),
            ("给她", "cho nàng", Layer.BASE_MULTI),
            ("她的", "nàng", Layer.BASE_MULTI),
            ("主人", "chủ nhân", Layer.BASE_MULTI),
            ("打电话", "gọi điện thoại", Layer.BASE_MULTI),
            ("给", "cho", Layer.BASE_SINGLE),
            ("她", "nàng", Layer.BASE_SINGLE),
        ],
        [
            ("{p}的主人", "chủ nhân của {p}"),
            ("给{p}的主人打电话", "gọi điện cho chủ nhân của {p}"),
        ],
    )
    t = vp_plan(dic, "给她的主人打电话").text.lower()
    assert "chủ nhân của nàng" in t
    assert "nàng chủ nhân" not in t


def test_ziji_de_banlian_inverts():
    dic = mini(
        [
            ("捂住", "che", Layer.BASE_MULTI),
            ("自己的", "mình", Layer.BASE_MULTI),
            ("半边脸", "nửa bên mặt", Layer.BASE_MULTI),
            ("自己", "mình", Layer.BASE_MULTI),
        ]
    )
    t = vp_plan(dic, "捂住自己的半边脸").text.lower()
    assert "nửa bên mặt của mình" in t
    assert "mình nửa" not in t


def test_jiejie_huawayin_inverts():
    dic = mini(
        [
            ("自己姐姐", "tỷ tỷ mình", Layer.BASE_MULTI),
            ("画外音", "hàm ý", Layer.GLOBAL_MANUAL, 100.0),
            ("听出了", "nghe được", Layer.BASE_MULTI),
            ("她", "nàng", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "她听出了自己姐姐的画外音").text.lower()
    assert "hàm ý của tỷ tỷ" in t
    assert "tỷ tỷ mình lời" not in t
    assert "thuyết minh" not in t


def test_dianhua_jiu_da_guolai_is_goi():
    dic = mini(
        [
            ("凌天", "Lăng Thiên", Layer.BASE_MULTI, 20.0),
            ("就打", "đánh liền", Layer.BASE_MULTI),
            ("打过来了", "đánh tới", Layer.BASE_MULTI),
            ("过来了", "đã tới", Layer.BASE_MULTI),
            ("就", "liền", Layer.BASE_SINGLE),
            ("打", "đánh", Layer.BASE_SINGLE),
        ],
        [("{n}的电话", "điện thoại của {n}")],
    )
    t = vp_plan(dic, "凌天的电话就打过来了").text.lower()
    assert "gọi tới" in t
    assert "đánh liền" not in t
    assert "đánh tới" not in t


def test_dao_semicolon_quote_is_noi():
    dic = mini(
        [
            ("雅樱", "Nhã Anh", Layer.BASE_MULTI, 20.0),
            ("道", "đạo", Layer.BASE_SINGLE),
        ]
    )
    t = vp_plan(dic, "雅樱道；“你过来吧").text.lower()
    assert "nói" in t
    assert "đạo" not in t


def test_naying_qingkuang_inverts():
    dic = mini(
        [
            ("哪一种", "loại nào", Layer.BASE_MULTI),
            ("情况", "tình huống", Layer.BASE_MULTI),
            ("到底是", "rút cuộc là", Layer.BASE_MULTI),
        ],
        [("哪一种{p}", "{p} nào")],
    )
    t = vp_plan(dic, "到底是哪一种情况").text.lower()
    assert "tình huống nào" in t
    assert "loại nào tình huống" not in t
