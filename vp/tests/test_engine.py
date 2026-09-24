from vp.engine import Engine, parse_dict_lines, parse_quality_overrides


def _engine(rows, *, luat_nhan=2, simplified=True, trad=None, custom=None):
    return Engine.build(
        rows,
        trad or {},
        simplified=simplified,
        luat_nhan=luat_nhan,
        custom=custom,
    )


def test_longest_match_beats_shorter_piece():
    engine = _engine(
        [
            ("你", "ngươi", 10, "VietPhrase_1.txt"),
            ("好", "tốt", 10, "VietPhrase_1.txt"),
            ("你好", "xin chào", 10, "VietPhrase_1.txt"),
        ]
    )
    assert engine.translate("你好。") == "Xin chào."


def test_priority_then_later_entry():
    engine = _engine(
        [
            ("人", "nhân", 10, "VietPhrase_1.txt"),
            ("人", "người", 10, "VietPhrase_2.txt"),
            ("人", "kẻ", 5, "ChinesePhienAmWords.txt"),
        ]
    )
    assert engine.translate("人") == "Người"


def test_first_vietphrase_variant_wins():
    rows = parse_dict_lines("你好=xin chào/hello\n", 10, "VietPhrase_1.txt")
    assert rows[0][1] == "xin chào"
    other = parse_dict_lines("你好=một/hai\n", 10, "Names.txt")
    assert other[0][1] == "một"


def test_english_vietphrase_gloss_is_skipped():
    skipped = parse_dict_lines("杀了我=Kill Me\n", 10, "VietPhrase_4.txt")
    assert skipped == []
    later = parse_dict_lines("秒杀=one hit one kill/miểu sát\n", 10, "VietPhrase_4.txt")
    assert later[0][1] == "miểu sát"
    kept = parse_dict_lines("杀了我=Kill Me\n", 20, "Names.txt")
    assert kept[0][1] == "Kill Me"
    plain = parse_dict_lines("出来=ra\n融灵=Dung Linh\n", 10, "VietPhrase_2.txt")
    assert [row[1] for row in plain] == ["ra", "Dung Linh"]


def test_kill_me_falls_through_to_shorter_match():
    rows = []
    rows += parse_dict_lines("你=ngươi\n", 10, "VietPhrase_1.txt")
    rows += parse_dict_lines("杀了=giết\n", 10, "VietPhrase_3.txt")
    rows += parse_dict_lines("我=ta\n", 10, "VietPhrase_2.txt")
    rows += parse_dict_lines("杀了我=Kill Me\n", 10, "VietPhrase_4.txt")
    assert _engine(rows).translate("你杀了我。") == "Ngươi giết ta."


def test_data_wrangling_falls_through_to_shorter_match():
    skipped = parse_dict_lines("数据整理=Data Wrangling\n", 10, "VietPhrase_4.txt")
    assert skipped == []
    kept = parse_dict_lines("数据整理=Data Wrangling\n", 20, "Names.txt")
    assert kept[0][1] == "Data Wrangling"
    rows = []
    rows += parse_dict_lines("把=đem\n", 10, "VietPhrase_2.txt")
    rows += parse_dict_lines("数据=số liệu\n", 10, "VietPhrase_2.txt")
    rows += parse_dict_lines("整理=chỉnh lý/sửa sang lại\n", 10, "VietPhrase_2.txt")
    rows += parse_dict_lines("数据整理=Data Wrangling\n", 10, "VietPhrase_4.txt")
    assert _engine(rows).translate("把数据整理。") == "Đem số liệu chỉnh lý."


def test_grammar_overlay_does_not_replace_function_phrase():
    engine = _engine(
        [
            ("这个时候", "lúc này", 10, "VietPhrase_2.txt"),
            ("这个", "cái này", 10, "VietPhrase_2.txt"),
            ("时候", "thời điểm", 10, "VietPhrase_2.txt"),
            ("千万别", "tuyệt đối đừng", 10, "VietPhrase_2.txt"),
            ("武者", "võ giả", 10, "VietPhrase_2.txt"),
        ]
    )
    overlay = [
        ("时候", "Thời Gian", 30),
        ("千万别", "Thiên Vạn Biệt", 30),
        ("武者", "Vũ Giả", 30),
    ]
    assert engine.translate("这个时候。", overlay) == "Lúc này."
    assert engine.translate("时候。", overlay) == "Thời điểm."
    assert engine.translate("千万别。", overlay) == "Tuyệt đối đừng."
    assert engine.translate("武者。", overlay) == "Vũ Giả."


def test_particle_dropped_and_suffix_pattern():
    rows = [
        ("他", "hắn", 10, "VietPhrase_1.txt"),
        ("好", "tốt", 10, "VietPhrase_1.txt"),
        ("人", "người", 10, "VietPhrase_1.txt"),
        ("{0}的人", "người của {0}", 15, "LuatNhan.txt"),
    ]
    assert _engine(rows, luat_nhan=0).translate("好的人") == "Tốt người"
    assert _engine(rows, luat_nhan=1).translate("他的人") == "Người của hắn"


def test_name_capture_needs_level_two():
    rows = [
        ("张三", "Trương Tam", 20, "Names.txt"),
        ("剑", "kiếm", 10, "VietPhrase_1.txt"),
        ("之", "chi", 10, "VietPhrase_1.txt"),
        ("{0}之剑", "kiếm của {0}", 15, "LuatNhan.txt"),
    ]
    assert _engine(rows, luat_nhan=1).translate("张三之剑") == "Trương Tam chi kiếm"
    assert _engine(rows, luat_nhan=2).translate("张三之剑") == "Kiếm của Trương Tam"


def test_longer_exact_phrase_blocks_suffix_pattern():
    rows = [
        ("他", "hắn", 10, "VietPhrase_1.txt"),
        ("人", "người", 10, "VietPhrase_1.txt"),
        ("他的人", "cụm sẵn", 10, "VietPhrase_1.txt"),
        ("{0}的人", "người của {0}", 15, "LuatNhan.txt"),
    ]
    assert _engine(rows).translate("他的人") == "Cụm sẵn"


def test_chapter_pattern_and_equal_length_trie():
    rows = [
        ("一", "nhất", 5, "ChinesePhienAmWords.txt"),
        ("第{0}章", "chương thứ {0}", 15, "LuatNhan.txt"),
    ]
    assert _engine(rows).translate("第一章") == "Chương thứ nhất"
    rows.append(("第一章", "đã khóa", 10, "VietPhrase_1.txt"))
    assert _engine(rows).translate("第一章") == "Đã khóa"


def test_prefix_pattern_does_not_split_longer_tail():
    rows = [
        ("章好", "chương tốt", 10, "VietPhrase_1.txt"),
        ("第{0}章", "chương {0}", 15, "LuatNhan.txt"),
        ("1", "1", 5, "ChinesePhienAmWords.txt"),
    ]
    assert "chương tốt" in _engine(rows).translate("第1章好").lower()


def test_hanviet_uses_priority_zero_map():
    rows = [
        ("他", "tha", 0, "dict-default.json"),
        ("他", "hắn", 5, "ChinesePhienAmWords.txt"),
        ("是", "thị", 0, "dict-default.json"),
        ("人", "nhân", 0, "dict-default.json"),
    ]
    engine = _engine(rows)
    assert engine.translate("他") == "Hắn"
    assert engine.hanviet("他是人。") == "Tha thị nhân."


def test_simplified_and_custom():
    trad = {"門": "门"}
    engine = _engine(
        [("门", "cửa", 10, "VietPhrase_1.txt")],
        trad=trad,
        custom=[("门", "cửa riêng")],
    )
    assert engine.translate("門") == "Cửa riêng"
    plain = _engine([("門", "môn", 10, "VietPhrase_1.txt")], trad=trad, simplified=False)
    assert plain.translate("門") == "Môn"


def test_overlay_not_swallowed():
    engine = _engine(
        [
            ("这", "này", 10, "VietPhrase_1.txt"),
            ("周", "chu", 10, "VietPhrase_1.txt"),
            ("这周", "tuần này", 10, "VietPhrase_1.txt"),
        ]
    )
    assert engine.translate("这周明瑞", [("周明瑞", "Chu Minh Thụy", 30)]) == "Này Chu Minh Thụy"


def test_station_noun_after_latin():
    engine = _engine([("站", "đứng", 10, "VietPhrase_1.txt")])
    assert engine.translate("A站。") == "A trạm."
    assert engine.translate("站。") == "Đứng."


def test_quality_override_priority():
    rows = parse_dict_lines("女士=bà\n", 10, "VietPhrase_1.txt")
    rows.extend(parse_quality_overrides("女士=nữ sĩ\t20\n"))
    assert _engine(rows).translate("女士") == "Nữ sĩ"


def test_generic_phrase_does_not_swallow_name_tail():
    engine = _engine(
        [
            ("七彩琉璃", "lưu ly bảy màu", 10, "VietPhrase_1.txt"),
            ("七彩", "thất thải", 10, "VietPhrase_2.txt"),
            ("琉璃宫", "Lưu Ly Cung", 20, "Names.txt"),
            ("宫", "cung", 5, "ChinesePhienAmWords.txt"),
        ]
    )
    assert engine.translate("七彩琉璃宫") == "Thất thải Lưu Ly Cung"
    assert engine.translate("七彩琉璃") == "Lưu ly bảy màu"


def test_protected_name_does_not_eat_yi_measure_word():
    engine = _engine(
        [
            ("和", "cùng", 10, "VietPhrase_2.txt"),
            ("和一", "Kazuichi", 20, "Names_2.txt"),
            ("一枚", "một viên", 10, "VietPhrase_2.txt"),
            ("一些", "một chút", 10, "VietPhrase_2.txt"),
            ("丹药", "đan dược", 10, "VietPhrase_1.txt"),
        ]
    )
    assert engine.translate("和一枚丹药") == "Cùng một viên đan dược"
    assert engine.translate("和一些") == "Cùng một chút"


def test_custom_overrides_junk_corpus_glosses():
    engine = _engine(
        [
            ("在云端", "trên đám mây - Up In The Air", 10, "VietPhrase_4.txt"),
            ("草他妈", "xxx mẹ nó", 10, "VietPhrase_2.txt"),
            ("嘎吱", "cọt kẹt..t..tttt", 20, "Names_2.txt"),
            ("云", "mây", 10, "VietPhrase_1.txt"),
        ],
        custom=[
            ("在云端", "trên đám mây"),
            ("草他妈", "con mẹ nó"),
            ("嘎吱", "cọt kẹt"),
        ],
    )
    assert engine.translate("在云端") == "Trên đám mây"
    assert engine.translate("草他妈") == "Con mẹ nó"
    assert engine.translate("嘎吱") == "Cọt kẹt"


def test_kinship_title_alias():
    engine = _engine([("张", "trương", 0, "dict-default.json")])
    assert engine.hanviet("师兄") == "Sư huynh"
    assert engine.hanviet("张师兄") == "Trương sư huynh"
