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
