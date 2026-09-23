from vp.engine import Engine


def _engine(rows, *, luat_nhan=2):
    return Engine.build(rows, {}, simplified=True, luat_nhan=luat_nhan)


def _low(rows, text: str) -> str:
    return _engine(rows).translate(text).lower()


def test_stolen_compound_zaihu_and_xuemai():
    rows = [
        ("他在", "hắn ở đây", 10, "VietPhrase_1.txt"),
        ("在乎", "quan tâm", 10, "VietPhrase_1.txt"),
        ("在乎的", "quan tâm", 10, "VietPhrase_1.txt"),
        ("他", "hắn", 10, "VietPhrase_1.txt"),
        ("在", "tại", 10, "VietPhrase_1.txt"),
        ("乎", "hồ", 10, "VietPhrase_1.txt"),
        ("多少血", "máu nhiêu", 10, "VietPhrase_1.txt"),
        ("这么多", "nhiều như vậy", 10, "VietPhrase_1.txt"),
        ("多少", "bao nhiêu", 10, "VietPhrase_1.txt"),
        ("血脉", "huyết mạch", 10, "VietPhrase_1.txt"),
        ("血", "máu", 10, "VietPhrase_1.txt"),
        ("脉", "mạch", 10, "VietPhrase_1.txt"),
        ("有", "có", 10, "VietPhrase_1.txt"),
    ]
    zai = _low(rows, "他在乎")
    assert "quan tâm" in zai
    assert "ở đây" not in zai
    assert "hồ" not in zai
    xue = _low(rows, "有多少血脉")
    assert "huyết mạch" in xue
    assert "máu nhiêu" not in xue


def test_stolen_compound_keeps_closed_locative_and_real_noun():
    rows = [
        ("一个", "một", 10, "VietPhrase_1.txt"),
        ("个人", "cá nhân", 10, "VietPhrase_1.txt"),
        ("人", "người", 10, "VietPhrase_1.txt"),
        ("一", "một", 5, "ChinesePhienAmWords.txt"),
        ("个", "cái", 5, "ChinesePhienAmWords.txt"),
        ("没有", "không có", 10, "VietPhrase_1.txt"),
        ("有敌意", "có địch ý", 10, "VietPhrase_1.txt"),
        ("敌意", "địch ý", 10, "VietPhrase_1.txt"),
        ("我", "ta", 10, "VietPhrase_1.txt"),
        ("没", "không", 5, "ChinesePhienAmWords.txt"),
        ("有", "có", 10, "VietPhrase_1.txt"),
        ("意", "ý", 5, "ChinesePhienAmWords.txt"),
        ("心中", "trong lòng", 10, "VietPhrase_1.txt"),
        ("中气", "trung khí", 10, "VietPhrase_1.txt"),
        ("心", "tâm", 5, "ChinesePhienAmWords.txt"),
        ("中", "trung", 5, "ChinesePhienAmWords.txt"),
        ("气", "khí", 5, "ChinesePhienAmWords.txt"),
        ("蒙面人", "người bịt mặt", 10, "VietPhrase_1.txt"),
        ("人丹", "nhân đan", 10, "VietPhrase_1.txt"),
        ("丹田", "đan điền", 10, "VietPhrase_1.txt"),
        ("丹", "đan", 5, "ChinesePhienAmWords.txt"),
        ("田", "ruộng", 5, "ChinesePhienAmWords.txt"),
    ]
    assert "cá nhân" not in _low(rows, "一个人")
    assert "người" in _low(rows, "一个人")
    meiyou = _low(rows, "我没有敌意")
    assert "không có" in meiyou
    assert "có có" not in meiyou
    xin = _low(rows, "心中气")
    assert "trong lòng" in xin
    assert "trung khí" not in xin
    dan = _low(rows, "蒙面人丹田")
    assert "người bịt mặt" in dan
    assert "đan điền" in dan
    assert "nhân đan" not in dan


def test_eat_phrase_not_forced_by_custom_overflow():
    rows = [
        ("在吃", "đang ăn", 10, "VietPhrase_2.txt"),
        ("吃着东西", "đang ăn", 999, "Custom.txt"),
        ("东西", "đồ vật", 10, "VietPhrase_1.txt"),
        ("在", "tại", 10, "VietPhrase_1.txt"),
        ("着", "đang", 10, "VietPhrase_1.txt"),
        ("吃", "ăn", 10, "VietPhrase_1.txt"),
    ]
    text = _low(rows, "在吃着东西")
    assert "đồ vật" in text
    assert "tại đang" not in text


def test_protected_overflow_genzhe_and_youdian():
    rows = [
        ("跟着", "đi theo", 10, "VietPhrase_1.txt"),
        ("去跟", "đi cùng", 10, "VietPhrase_1.txt"),
        ("去", "đi", 10, "VietPhrase_1.txt"),
        ("跟", "cùng", 10, "VietPhrase_1.txt"),
        ("着", "đang", 10, "VietPhrase_1.txt"),
        ("晚上有", "buổi tối có", 10, "VietPhrase_1.txt"),
        ("有点", "có chút", 10, "VietPhrase_1.txt"),
        ("晚上", "ban đêm", 10, "VietPhrase_1.txt"),
        ("冷", "lạnh", 10, "VietPhrase_1.txt"),
    ]
    gen = _low(rows, "去跟着")
    assert "đi theo" in gen
    assert "cùng đang" not in gen
    you = _low(rows, "晚上有点冷")
    assert "có chút" in you
    assert "buổi tối có" not in you


def test_stolen_bu_and_closed_bu():
    rows = [
        ("到不", "không đến được", 10, "VietPhrase_1.txt"),
        ("不可思议", "không thể tưởng tượng nổi", 10, "VietPhrase_1.txt"),
        ("不了", "không xong", 10, "VietPhrase_1.txt"),
        ("到", "đến", 10, "VietPhrase_1.txt"),
        ("不", "không", 10, "VietPhrase_1.txt"),
        ("毫不", "không chút nào", 10, "VietPhrase_1.txt"),
        ("不设防", "không đề phòng", 10, "VietPhrase_1.txt"),
        ("毫", "hào", 5, "ChinesePhienAmWords.txt"),
        ("设防", "phòng bị", 10, "VietPhrase_1.txt"),
    ]
    busi = _low(rows, "到不可思议")
    assert "không thể tưởng tượng nổi" in busi
    assert "không đến được" not in busi
    assert "không đến được" in _low(rows, "到不了")
    hao = _low(rows, "毫不设防")
    assert "không chút nào" in hao
    assert "hào" not in hao


def test_stolen_pronoun_np_and_skips():
    rows = [
        ("她信", "thư của nàng", 10, "VietPhrase_1.txt"),
        ("信不过", "không tin được", 10, "VietPhrase_1.txt"),
        ("她", "nàng", 10, "VietPhrase_1.txt"),
        ("信", "tin", 10, "VietPhrase_1.txt"),
        ("我", "ta", 10, "VietPhrase_1.txt"),
        ("它坚持", "sự kiên trì của nó", 10, "VietPhrase_1.txt"),
        ("坚持下来了", "kiên trì nổi", 10, "VietPhrase_1.txt"),
        ("它", "nó", 10, "VietPhrase_1.txt"),
        ("坚持", "kiên trì", 10, "VietPhrase_1.txt"),
        ("我不", "ta không có", 10, "VietPhrase_1.txt"),
        ("不算", "không tính", 10, "VietPhrase_1.txt"),
        ("不", "không", 10, "VietPhrase_1.txt"),
        ("算", "tính", 10, "VietPhrase_1.txt"),
        ("他看", "nhìn hắn", 10, "VietPhrase_1.txt"),
        ("看来", "xem ra", 10, "VietPhrase_1.txt"),
        ("他", "hắn", 10, "VietPhrase_1.txt"),
        ("看", "nhìn", 10, "VietPhrase_1.txt"),
        ("来", "tới", 10, "VietPhrase_1.txt"),
        ("他们", "bọn họ", 10, "VietPhrase_1.txt"),
        ("来处理", "đến xử lý", 10, "VietPhrase_1.txt"),
        ("们", "các", 5, "ChinesePhienAmWords.txt"),
    ]
    xin = _low(rows, "她信不过")
    assert "không tin được" in xin
    assert "thư của nàng" not in xin
    jian = _low(rows, "它坚持下来了")
    assert "kiên trì nổi" in jian
    assert "sự kiên trì" not in jian
    suan = _low(rows, "我不算")
    assert "không tính" in suan
    assert "không có" not in suan
    assert "nhìn hắn" in _low(rows, "他看来")
    assert "xem ra" not in _low(rows, "他看来")
    assert "bọn họ" in _low(rows, "他们来处理")


def test_idiom_overflow_not_compositional():
    rows = [
        ("人望", "nhân vọng", 10, "VietPhrase_1.txt"),
        ("人", "người", 10, "VietPhrase_1.txt"),
        ("望其项背", "nhìn theo bóng lưng", 10, "VietPhrase_1.txt"),
        ("早就", "đã sớm", 10, "VietPhrase_1.txt"),
        ("早", "sớm", 10, "VietPhrase_1.txt"),
        ("就忍不住", "liền không nhịn được", 10, "VietPhrase_1.txt"),
    ]
    idiom = _low(rows, "人望其项背")
    assert "nhìn theo bóng lưng" in idiom
    assert "nhân vọng" not in idiom
    assert "đã sớm" in _low(rows, "早就忍不住")


def test_name_yijing_glue_splits():
    rows = [
        ("凌天已经", "Lăng Thiên đã ở", 10, "VietPhrase_1.txt"),
        ("凌天", "Lăng Thiên", 20, "Names.txt"),
        ("已经", "đã", 10, "VietPhrase_1.txt"),
    ]
    text = _low(rows, "凌天已经")
    assert "lăng thiên" in text
    assert "đã ở" not in text


def test_de_phrase_is_not_split_into_shorter_stem():
    """A longer X的 entry is the good gloss. Do not fall back to the stem."""
    rows = [
        ("铺天盖地的", "ừn ùn kéo đến", 10, "VietPhrase_3.txt"),
        ("铺天盖地", "phô thiên cái địa", 20, "Names.txt"),
        ("没有", "không có", 10, "VietPhrase_1.txt"),
        ("蛊虫", "cổ trùng", 10, "VietPhrase_1.txt"),
        ("开门见山的", "khai môn kiến sơn", 10, "VietPhrase_1.txt"),
        ("开门见山", "đi thẳng vào vấn đề", 10, "VietPhrase_1.txt"),
        ("的话", "nếu", 19, "QualityOverrides.txt"),
        ("话", "lời nói", 10, "VietPhrase_2.txt"),
        ("听到", "nghe thấy", 10, "VietPhrase_1.txt"),
    ]
    sky = _low(rows, "没有铺天盖地的蛊虫")
    assert "ừn ùn kéo đến" in sky
    assert "phô thiên cái địa" not in sky
    speech = _low(rows, "听到开门见山的话")
    assert "khai môn kiến sơn" in speech
    assert "nếu" not in speech


def test_custom_name_beats_short_glue():
    rows = [
        ("左边", "bên trái", 10, "VietPhrase_1.txt"),
        ("是", "là", 10, "VietPhrase_1.txt"),
        ("是小", "là nhỏ", 10, "VietPhrase_1.txt"),
        ("小", "nhỏ", 10, "VietPhrase_1.txt"),
        ("美", "đẹp", 10, "VietPhrase_1.txt"),
        ("小美", "Tiểu Mỹ", 999, "Custom.txt"),
    ]
    text = _low(rows, "左边是小美")
    assert "tiểu mỹ" in text
    assert "nhỏ đẹp" not in text
    assert "là nhỏ" not in text


def test_possessive_de_name_pronoun_time_and_skips():
    rows = [
        ("花少", "Hoa thiếu", 20, "Names.txt"),
        ("耻辱", "sỉ nhục", 10, "VietPhrase_1.txt"),
        ("我", "ta", 10, "VietPhrase_1.txt"),
        ("女人", "người phụ nữ", 10, "VietPhrase_1.txt"),
        ("桐城", "Đồng Thành", 20, "Names.txt"),
        ("晚上", "ban đêm", 10, "VietPhrase_1.txt"),
        ("新", "mới", 10, "VietPhrase_1.txt"),
        ("老师", "thầy", 10, "VietPhrase_1.txt"),
        ("打不晕", "đánh không ngất", 10, "VietPhrase_1.txt"),
        ("凌天", "Lăng Thiên", 20, "Names.txt"),
        ("话", "lời", 10, "VietPhrase_1.txt"),
    ]
    assert "sỉ nhục của hoa thiếu" in _low(rows, "花少的耻辱")
    assert "người phụ nữ của ta" in _low(rows, "我的女人")
    evening = _low(rows, "桐城的晚上")
    assert "ban đêm ở đồng thành" in evening
    assert "của" not in evening
    adj = _low(rows, "新的老师")
    assert "của" not in adj
    assert "thầy" in adj
    relative = _low(rows, "打不晕的凌天")
    assert "của" not in relative
    assert "lăng thiên" in relative
    speech = _low(rows, "花少的话")
    assert "của" not in speech


def test_realm_stage_de_stays_in_source_order():
    rows = [
        ("先天中期", "Tiên Thiên trung kỳ", 20, "Names.txt"),
        ("先天巅峰", "Tiên Thiên đỉnh phong", 20, "Names.txt"),
        ("先天后期", "Tiên Thiên Hậu Kỳ", 10, "VietPhrase_4.txt"),
        ("先天境界", "Tiên Thiên cảnh giới", 20, "Names.txt"),
        ("武者", "võ giả", 10, "VietPhrase_1.txt"),
        ("凌天", "Lăng Thiên", 20, "Names.txt"),
        ("女人", "người phụ nữ", 10, "VietPhrase_1.txt"),
    ]
    mid = _low(rows, "先天中期的武者")
    assert "của" not in mid
    assert mid.index("tiên thiên trung kỳ") < mid.index("võ giả")
    peak = _low(rows, "先天巅峰的武者")
    assert "của" not in peak
    assert peak.index("đỉnh phong") < peak.index("võ giả")
    late = _low(rows, "先天后期的武者")
    assert "của" not in late
    realm = _low(rows, "先天境界的武者")
    assert "của" not in realm
    assert realm.index("cảnh giới") < realm.index("võ giả")
    assert "người phụ nữ của lăng thiên" in _low(rows, "凌天的女人")


def test_strength_comparative_stays_outside_possessive():
    rows = [
        ("等到", "đợi đến", 10, "VietPhrase_1.txt"),
        ("凌天", "Lăng Thiên", 20, "Names.txt"),
        ("实力", "thực lực", 10, "VietPhrase_2.txt"),
        ("的实力", "thực lực", 10, "VietPhrase_4.txt"),
        ("更强", "càng mạnh", 10, "VietPhrase_2.txt"),
    ]
    out = _low(rows, "等到凌天的实力更强")
    assert "thực lực của lăng thiên mạnh hơn" in out
    assert "càng mạnh của" not in out


def test_zhexie_cao_keeps_herb_compound():
    rows = [
        ("这些草", "những cỏ này", 10, "VietPhrase_3.txt"),
        ("草药", "dược liệu", 999, "Custom.txt"),
        ("这些草药", "những dược liệu này", 999, "Custom.txt"),
        ("药", "thuốc", 10, "VietPhrase_1.txt"),
    ]
    out = _low(rows, "这些草药")
    assert out == "những dược liệu này"
    assert "thuốc" not in out


def test_neijin_peak_is_not_a_possessive_name():
    rows = [
        ("内劲", "nội kình", 10, "VietPhrase_2.txt"),
        ("巅峰", "đỉnh phong", 999, "Custom.txt"),
        ("巅峰的", "tột cùng", 10, "VietPhrase_3.txt"),
        ("武者", "võ giả", 10, "VietPhrase_1.txt"),
    ]
    engine = _engine(rows)
    out = engine.translate("内劲巅峰的武者", [("内劲巅峰", "Nội Kình Điên Phong", 25)])
    assert out == "Nội kình đỉnh phong võ giả"
    assert "Điên Phong" not in out
    assert "của" not in out


def test_xianzai_jiuyao_is_not_sap():
    rows = [
        ("您", "ngài", 10, "VietPhrase_1.txt"),
        ("现在", "hiện tại", 10, "VietPhrase_1.txt"),
        ("就要", "sắp", 19, "QualityOverrides.txt"),
        ("现在就要", "muốn ngay bây giờ", 999, "Custom.txt"),
    ]
    out = _low(rows, "您现在就要？")
    assert "muốn ngay bây giờ" in out
    assert "sắp" not in out


def test_qianzhan_before_zhe_is_standing_not_station():
    rows = [
        ("看着", "nhìn xem", 10, "VietPhrase_2.txt"),
        ("别墅门", "cửa biệt thự", 10, "VietPhrase_3.txt"),
        ("别墅", "biệt thự", 10, "VietPhrase_2.txt"),
        ("门前站着", "trước cửa đứng đấy", 10, "VietPhrase_2.txt"),
        ("前站", "tiền trạm", 10, "VietPhrase_2.txt"),
        ("站着", "đứng", 10, "VietPhrase_2.txt"),
        ("前", "trước", 10, "VietPhrase_2.txt"),
        ("保镖", "bảo tiêu", 10, "VietPhrase_2.txt"),
        ("大门前", "trước cổng chính", 10, "VietPhrase_2.txt"),
        ("大门", "cổng lớn", 10, "VietPhrase_2.txt"),
        ("两个", "hai", 10, "VietPhrase_1.txt"),
        ("守卫", "thủ vệ", 10, "VietPhrase_1.txt"),
        ("晶石", "tinh thạch", 10, "VietPhrase_2.txt"),
        ("不少人", "không ít người", 10, "VietPhrase_1.txt"),
        ("先遣队", "đội tiền trạm", 10, "VietPhrase_2.txt"),
        ("面前", "trước mặt", 10, "VietPhrase_2.txt"),
        ("一个人", "một người", 10, "VietPhrase_1.txt"),
    ]
    door = _low(rows, "看着别墅门前站着的保镖")
    assert "trước cửa đứng" in door
    assert "biệt thự" in door
    assert "tiền trạm" not in door
    assert "cửa biệt thự" not in door
    gate = _low(rows, "大门前站着两个守卫")
    assert "trước cổng chính" in gate
    assert "tiền trạm" not in gate
    stone = _low(rows, "晶石前站着不少人")
    assert "tiền trạm" not in stone
    assert "trước" in stone and "đứng" in stone
    assert "đội tiền trạm" in _low(rows, "先遣队")
    front = _low(rows, "面前站着一个人")
    assert "trước mặt" in front
    assert "tiền trạm" not in front


def test_chapter_1089_spans_stay_narrow():
    rows = [
        ("但", "nhưng", 10, "VietPhrase_1.txt"),
        ("他们", "bọn hắn", 10, "VietPhrase_2.txt"),
        ("他", "hắn", 10, "VietPhrase_1.txt"),
        ("再", "lại", 10, "VietPhrase_2.txt"),
        ("在意", "để ý", 10, "VietPhrase_2.txt"),
        ("不再", "không còn", 10, "VietPhrase_2.txt"),
        ("依然", "vẫn", 10, "VietPhrase_2.txt"),
        ("不是", "không phải", 10, "VietPhrase_1.txt"),
        ("送我", "tặng cho ta", 10, "VietPhrase_4.txt"),
        ("送", "đưa", 10, "VietPhrase_2.txt"),
        ("我们", "chúng ta", 10, "VietPhrase_2.txt"),
        ("们", "nhóm", 10, "VietPhrase_2.txt"),
        ("过去", "đi qua", 19, "QualityOverrides.txt"),
        ("味道好", "mùi ngon", 10, "VietPhrase_3.txt"),
        ("太差", "quá kém", 10, "VietPhrase_2.txt"),
        ("地方", "chỗ", 19, "QualityOverrides.txt"),
        ("凌天", "Lăng Thiên", 20, "Names.txt"),
        ("开了", "mở", 10, "VietPhrase_3.txt"),
        ("切开了", "cắt mở", 10, "VietPhrase_2.txt"),
        ("手", "tay", 10, "VietPhrase_1.txt"),
        ("打开", "mở ra", 10, "VietPhrase_2.txt"),
        ("门", "cửa", 10, "VietPhrase_2.txt"),
    ]
    care = _low(rows, "但他们再在意，依然不是")
    assert "dù để ý đến mấy" in care
    assert "lại để ý" not in care
    still = _low(rows, "不再在意")
    assert "không còn" in still
    assert "dù để ý" not in still
    trip = _low(rows, "送我们过去")
    assert "tặng" not in trip
    assert "nhóm" not in trip
    assert "chúng ta" in trip
    assert "đưa" in trip
    place = _low(rows, "味道好的地方")
    assert place.startswith("chỗ ")
    assert "mùi ngon" in place
    assert not place.startswith("mùi")
    assert _low(rows, "太差的地方").startswith("chỗ ")
    owned = _low(rows, "凌天的地方")
    assert "của" in owned
    assert "chỗ của" in owned
    fired = _low(rows, "然后开了他")
    assert "đuổi" in fired
    assert "mở hắn" not in fired
    cut = _low(rows, "切开了他的手")
    assert "đuổi" not in cut
    assert "mở" in _low(rows, "打开门")


def test_simile_yiban_is_not_ordinary():
    rows = [
        ("好像", "hình như", 19, "QualityOverrides.txt"),
        ("韩梅", "Hàn Mai", 20, "Names.txt"),
        ("要", "muốn", 10, "VietPhrase_1.txt"),
        ("找麻烦", "tìm phiền phức", 10, "VietPhrase_2.txt"),
        ("一般", "bình thường", 20, "QualityOverrides.txt"),
        ("很", "rất", 10, "VietPhrase_1.txt"),
        ("他", "hắn", 10, "VietPhrase_1.txt"),
    ]
    like = _low(rows, "好像韩梅要找麻烦一般")
    assert "vậy" in like
    assert "bình thường" not in like
    ordinary = _low(rows, "他很一般")
    assert "bình thường" in ordinary
    assert "vậy" not in ordinary


def test_my_words_keep_speech_and_orders_count():
    rows = [
        ("但", "nhưng", 10, "VietPhrase_1.txt"),
        ("我的话", "ta", 10, "VietPhrase_2.txt"),
        ("要是", "nếu là", 10, "VietPhrase_1.txt"),
        ("听", "nghe", 10, "VietPhrase_1.txt"),
        ("绝对", "tuyệt đối", 10, "VietPhrase_2.txt"),
        ("有效", "hữu hiệu", 10, "VietPhrase_2.txt"),
    ]
    words = _low(rows, "但我的话，绝对有效")
    assert "lời của ta" in words
    assert "tuyệt đối có hiệu lực" in words
    assert "hữu hiệu" not in words
    conditional = _low(rows, "要是我的话")
    assert "lời của ta" not in conditional
    assert "ta" in conditional
    assert "lời của ta" in _low(rows, "听我的话")


def test_shuiyue_is_not_split_by_huishui_or_huishui():
    rows = [
        ("我要", "ta muốn", 10, "VietPhrase_1.txt"),
        ("带你", "mang ngươi", 10, "VietPhrase_2.txt"),
        ("回水", "nước đọng", 10, "VietPhrase_2.txt"),
        ("回", "về", 10, "VietPhrase_2.txt"),
        ("会水", "biết bơi", 10, "VietPhrase_2.txt"),
        ("会", "sẽ", 10, "VietPhrase_2.txt"),
        ("水月", "Thủy Nguyệt", 20, "Names_2.txt"),
        ("月", "nguyệt", 5, "ChinesePhienAmWords.txt"),
        ("水", "nước", 5, "ChinesePhienAmWords.txt"),
    ]
    back = _low(rows, "我要带你回水月")
    assert "thủy nguyệt" in back
    assert "về" in back
    assert "nước đọng" not in back
    assert "nguyệt" not in back.replace("thủy nguyệt", "")
    hui = _low(rows, "我带你会水月")
    assert "thủy nguyệt" in hui
    assert "biết bơi" not in hui
    assert "về" in hui
    # A random 2-char Names hit must not split 开始.
    kept = _low(
        [
            ("开始", "bắt đầu", 10, "VietPhrase_2.txt"),
            ("始炼", "Thủy Luyện", 20, "Names.txt"),
            ("炼丹", "luyện đan", 10, "VietPhrase_2.txt"),
            ("开", "mở", 10, "VietPhrase_2.txt"),
        ],
        "开始炼丹",
    )
    assert "bắt đầu" in kept
    assert "thủy luyện" not in kept


def test_bare_duzi_before_verb_is_alone():
    rows = [
        ("独子", "con trai độc nhất", 10, "VietPhrase_2.txt"),
        ("独自", "một mình", 10, "VietPhrase_2.txt"),
        ("站在了", "đứng ở", 10, "VietPhrase_2.txt"),
        ("门前", "trước cửa", 10, "VietPhrase_2.txt"),
        ("他的独子", "con trai độc nhất của hắn", 10, "VietPhrase_1.txt"),
        ("很好", "rất tốt", 10, "VietPhrase_1.txt"),
        ("去", "đi", 10, "VietPhrase_1.txt"),
    ]
    stood = _low(rows, "凌天说着话，独子站在了门前")
    assert "một mình" in stood
    assert "con trai" not in stood
    assert "một mình" in _low(rows, "独子去")
    assert "con trai độc nhất của hắn" in _low(rows, "他的独子")
    noun = _low(rows, "独子很好")
    assert "con trai độc nhất" in noun
    assert "một mình" not in noun


def test_clan_possessive_skips_huijia():
    rows = [
        ("灭", "diệt", 10, "VietPhrase_1.txt"),
        ("我", "ta", 10, "VietPhrase_1.txt"),
        ("赵家", "Triệu Gia", 999, "Custom.txt"),
        ("回家", "về nhà", 10, "VietPhrase_1.txt"),
        ("送", "tiễn", 10, "VietPhrase_1.txt"),
    ]
    clan = _low(rows, "灭我赵家")
    assert "triệu gia của ta" in clan
    assert "diệt ta" not in clan
    home = _low(rows, "送我回家")
    assert "về nhà" in home
    assert "của" not in home
