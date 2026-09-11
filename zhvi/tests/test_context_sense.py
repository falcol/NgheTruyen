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
    for i, (zh, vi, layer) in enumerate(entries):
        _insert(root, zh, vi, (int(layer), float(layer) * 10, i), "CONTEXTUAL")
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
