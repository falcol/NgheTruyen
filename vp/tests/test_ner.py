from vp.ner_decide import is_noise, select_names
from vp.ner_text import Tokenizer, decode_bio, segment_text


def test_decode_bio_keeps_confident_name():
    labels = [0, 1, 2, 0]
    probs = [0.99, 0.9, 0.9, 0.99]
    offsets = [(0, 0), (0, 1), (1, 2), (0, 0)]
    entities = decode_bio(labels, probs, offsets, "张三")
    assert [(item.text, item.tag) for item in entities] == [("张三", "Nh")]


def test_decode_bio_drops_low_confidence():
    labels = [0, 1, 0]
    probs = [0.99, 0.5, 0.99]
    offsets = [(0, 0), (0, 2), (0, 0)]
    assert decode_bio(labels, probs, offsets, "张三") == []


def test_select_names_approves_repeated_character_and_skips_noise():
    spans = [("周明瑞", "Nh")] * 3 + [("师父", "Nh")] * 4 + [("长乐郡", "Ns")] * 3

    def suggest(zh: str) -> str:
        return "Chu Minh Thụy" if zh == "周明瑞" else ""

    found, stats = select_names(spans, suggest, known={"已知"})
    approved = [item for item in found if item.status == "approved"]
    assert [item.zh for item in approved] == ["周明瑞"]
    assert stats.approved == 1
    assert is_noise("师父")
    assert all(item.zh != "长乐郡" or item.status == "pending" for item in found)


def test_tokenizer_wraps_cls_sep_and_segments_short_text():
    vocab = "\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "张", "三"]) + "\n"
    tokenizer = Tokenizer(vocab)
    ids, offsets = tokenizer.tokenize("张三")
    assert ids == [2, 4, 5, 3]
    assert offsets[1] == (0, 1)
    segments = segment_text(tokenizer, "张三。")
    assert len(segments) == 1
    assert segments[0].input_ids[0] == tokenizer.cls
    assert max(len(row.input_ids) for row in segment_text(tokenizer, "张" * 400)) <= 192
