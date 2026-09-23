from vp.engine import Engine
from vp.filetrans import build_file_chunks, split_oversized, translate_file, translate_piecewise


def _engine():
    return Engine.build(
        [
            ("一", "nhất", 5, "ChinesePhienAmWords.txt"),
            ("你", "nhân", 0, "dict-default.json"),
            ("好", "hảo", 0, "dict-default.json"),
            ("你好", "xin chào", 10, "VietPhrase_1.txt"),
            ("世界", "thế giới", 10, "VietPhrase_1.txt"),
            ("再见", "tạm biệt", 10, "VietPhrase_1.txt"),
            ("第{0}章", "chương thứ {0}", 15, "LuatNhan.txt"),
        ]
    )


def test_chunks_keep_heading_blank_and_swallowed_spaces():
    engine = _engine()
    text = "第一章\n你好。 世界。\n\n再见\n"
    assert translate_file(text, engine) == "Chương thứ nhất\nXin chào. Thế giới.\n\nTạm biệt\n"


def test_piecewise_keeps_newline():
    engine = _engine()
    out = translate_piecewise("你好。\n世界。", engine.translate)
    assert out == "Xin chào.\nThế giới."


def test_space_after_sentence_and_closing_quote():
    engine = _engine()
    assert translate_piecewise("你好？世界。", engine.translate) == "Xin chào? Thế giới."
    assert translate_piecewise("你好。”世界。", engine.translate) == "Xin chào.” Thế giới."


def test_heading_is_not_split_and_soft_limit_cuts_on_period():
    chunks = build_file_chunks("第一章\n" + ("人" * 30), soft=10, hard=18)
    assert chunks[0]["type"] == "heading"
    assert chunks[0]["text"] == "第一章"
    body = "人" * 12 + "。" + "人" * 20
    parts = split_oversized(body, soft=10, hard=18)
    assert parts[0] == "人" * 12 + "。"
    hard = split_oversized("人" * 30, soft=10, hard=18)
    assert [len(part) for part in hard] == [18, 12]


def test_hanviet_file_mode():
    engine = _engine()
    assert translate_file("你好。", engine, mode="hanviet") == "Nhân hảo."
