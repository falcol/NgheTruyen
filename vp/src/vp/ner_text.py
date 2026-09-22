"""BERT WordPiece and BIO decode for the vietphrase.app NER-B model."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

LABELS = ("O", "B-Nh", "I-Nh", "B-Ns", "I-Ns", "B-Ni", "I-Ni")
THRESHOLD = 0.85
MAX_TOKENS = 192
OVERLAP_CODEPOINTS = 16
BREAK_WINDOW = 96

_SEGMENT_BREAK = re.compile(r"[\s,，。！？；：、…．.!?;:）)】》”\"'』」]")
_SENTENCE_END = frozenset("。！？…!?")
_SENTENCE_CLOSE = frozenset("”』」）")


def _is_cjk(cp: int) -> bool:
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0xF900 <= cp <= 0xFAFF
        or 0x2F800 <= cp <= 0x2FA1F
    )


def _is_ascii_punct(cp: int) -> bool:
    return 33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126


def _is_punct(ch: str) -> bool:
    cp = ord(ch)
    return _is_ascii_punct(cp) or unicodedata.category(ch).startswith("P")


def _is_mark(ch: str) -> bool:
    return unicodedata.category(ch) == "Mn"


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch) in {"Cc", "Cf", "Cn", "Co", "Cs"}


class Tokenizer:
    def __init__(self, vocab_text: str) -> None:
        self.vocab: dict[str, int] = {}
        lines = vocab_text.split("\n")
        for i, line in enumerate(lines):
            tok = line[:-1] if line.endswith("\r") else line
            if tok or i < len(lines) - 1:
                self.vocab[tok] = i
        self.unk = self.vocab["[UNK]"]
        self.cls = self.vocab["[CLS]"]
        self.sep = self.vocab["[SEP]"]

    def tokenize(self, text: str) -> tuple[list[int], list[tuple[int, int]]]:
        points = list(text)
        words: list[list[tuple[str, int]]] = []
        cur: list[tuple[str, int]] | None = None

        def flush() -> None:
            nonlocal cur
            if cur:
                words.append(cur)
            cur = None

        for i, ch in enumerate(points):
            norm = _normalize_char(ch)
            if norm is None:
                continue
            if norm == " ":
                flush()
                continue
            if _is_cjk(ord(ch)):
                flush()
                words.append([(norm, i)])
                continue
            for piece in norm:
                if _is_punct(piece):
                    flush()
                    words.append([(piece, i)])
                else:
                    if cur is None:
                        cur = []
                    cur.append((piece, i))
        flush()
        ids = [self.cls]
        offsets = [(0, 0)]
        for word in words:
            start0 = word[0][1]
            end0 = word[-1][1] + 1
            if len(word) > 100:
                ids.append(self.unk)
                offsets.append((start0, end0))
                continue
            pieces: list[tuple[int, int, int]] = []
            start = 0
            bad = False
            while start < len(word):
                end = len(word)
                found = -1
                while end > start:
                    cand = "".join(word[k][0] for k in range(start, end))
                    if start > 0:
                        cand = "##" + cand
                    found = self.vocab.get(cand, -1)
                    if found >= 0:
                        break
                    end -= 1
                if found < 0:
                    bad = True
                    break
                pieces.append((found, start, end))
                start = end
            if bad:
                ids.append(self.unk)
                offsets.append((start0, end0))
            else:
                for token_id, start, end in pieces:
                    ids.append(token_id)
                    offsets.append((word[start][1], word[end - 1][1] + 1))
        ids.append(self.sep)
        offsets.append((0, 0))
        return ids, offsets


def _normalize_char(ch: str) -> str | None:
    cp = ord(ch)
    if cp in (0, 0xFFFD):
        return None
    if ch in "\t\n\r":
        return " "
    if _is_control(ch):
        return None
    if ch.isspace():
        return " "
    out = "".join(c for c in unicodedata.normalize("NFD", ch) if not _is_mark(c))
    return out.lower()


@dataclass(slots=True)
class Segment:
    text: str
    input_ids: list[int]
    offsets: list[tuple[int, int]]
    start: int
    end: int
    owned_start: int
    owned_end: int
    artificial_left: bool
    artificial_right: bool


def _sentence_ranges(points: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    cursor = 0
    n = len(points)
    while cursor < n:
        boundary = False
        if points[cursor] in _SENTENCE_END:
            cursor += 1
            while cursor < n and points[cursor] in _SENTENCE_END:
                cursor += 1
            while cursor < n and points[cursor] in _SENTENCE_CLOSE:
                cursor += 1
            boundary = True
        elif points[cursor] in "\r\n":
            if points[cursor] == "\r" and cursor + 1 < n and points[cursor + 1] == "\n":
                cursor += 2
            else:
                cursor += 1
            boundary = True
        else:
            cursor += 1
        if not boundary:
            continue
        while cursor < n and points[cursor].isspace():
            cursor += 1
        if any(not points[i].isspace() for i in range(start, cursor)):
            ranges.append((start, cursor))
        start = cursor
    if start < n:
        ranges.append((start, n))
    return ranges


def _stable_end(points: list[str], start: int, target: int) -> int:
    end = min(len(points), max(start + 1, target))
    while end < len(points) and not _stable(points[end - 1]) and not _stable(points[end]):
        end += 1
    return end


def _stable(ch: str) -> bool:
    return ch.isspace() or _is_punct(ch) or _is_cjk(ord(ch))


def segment_text(tokenizer: Tokenizer, text: str, max_tokens: int = MAX_TOKENS) -> list[Segment]:
    points = list(text)
    if not points:
        return []
    segments: list[Segment] = []
    for range_start, range_end in _sentence_ranges(points):
        local = points[range_start:range_end]
        for seg in _segment_range(tokenizer, local, max_tokens):
            segments.append(
                Segment(
                    text=seg.text,
                    input_ids=seg.input_ids,
                    offsets=seg.offsets,
                    start=range_start + seg.start,
                    end=range_start + seg.end,
                    owned_start=range_start + seg.owned_start,
                    owned_end=range_start + seg.owned_end,
                    artificial_left=seg.artificial_left,
                    artificial_right=seg.artificial_right,
                )
            )
    return segments


def _tokenize_span(tokenizer: Tokenizer, points: list[str], start: int, end: int) -> tuple[str, list[int], list[tuple[int, int]]]:
    text = "".join(points[start:end])
    ids, offsets = tokenizer.tokenize(text)
    return text, ids, offsets


def _segment_range(tokenizer: Tokenizer, points: list[str], max_tokens: int) -> list[Segment]:
    segments: list[Segment] = []
    start = 0
    owned = 0
    n = len(points)
    while start < n:
        window_end, ids, offsets, window_text = _bounded_prefix(tokenizer, points, start, max_tokens)
        if window_end == n and len(ids) <= max_tokens:
            segments.append(
                Segment(window_text, ids, offsets, start, n, owned, n, start < owned, False)
            )
            break
        token_cut = offsets[max_tokens - 2][1]
        candidate = min(n, start + token_cut)
        safe = False
        floor = max(start + 1, candidate - BREAK_WINDOW)
        for cursor in range(candidate, floor, -1):
            if _SEGMENT_BREAK.match(points[cursor - 1]):
                candidate = cursor
                safe = True
                break
        fitted_end, fitted_ids, fitted_offsets, fitted_text = _fit(tokenizer, points, start, candidate, max_tokens)
        if fitted_end != candidate:
            safe = False
        segments.append(
            Segment(
                fitted_text,
                fitted_ids,
                fitted_offsets,
                start,
                fitted_end,
                owned,
                fitted_end,
                start < owned,
                not safe,
            )
        )
        owned = fitted_end
        start = fitted_end if safe else max(start + 1, fitted_end - OVERLAP_CODEPOINTS)
    return segments


def _bounded_prefix(
    tokenizer: Tokenizer, points: list[str], start: int, max_tokens: int
) -> tuple[int, list[int], list[tuple[int, int]], str]:
    span = max_tokens * 2
    while True:
        end = _stable_end(points, start, start + span)
        text, ids, offsets = _tokenize_span(tokenizer, points, start, end)
        if len(ids) > max_tokens or end == len(points):
            return end, ids, offsets, text
        span = max(span * 2, (end - start) * 2)


def _fit(
    tokenizer: Tokenizer, points: list[str], start: int, candidate: int, max_tokens: int
) -> tuple[int, list[int], list[tuple[int, int]], str]:
    end = candidate
    text, ids, offsets = _tokenize_span(tokenizer, points, start, end)
    while len(ids) > max_tokens:
        token_end = offsets[max_tokens - 2][1]
        end = min(end - 1, start + token_end)
        text, ids, offsets = _tokenize_span(tokenizer, points, start, end)
    return end, ids, offsets, text


@dataclass(slots=True)
class Entity:
    text: str
    tag: str
    start: int
    end: int
    confidence: float


def decode_bio(
    label_ids: list[int],
    probabilities: list[float],
    offsets: list[tuple[int, int]],
    text: str,
    *,
    threshold: float = THRESHOLD,
) -> list[Entity]:
    points = list(text)
    entities: list[Entity] = []
    index = 0
    while index < len(label_ids):
        start, end = offsets[index]
        label = LABELS[label_ids[index]] if 0 <= label_ids[index] < len(LABELS) else "O"
        if start == end or label == "O":
            index += 1
            continue
        kind = label.split("-", 1)[1]
        tokens = [index]
        char_end = end
        cursor = index + 1
        while cursor < len(label_ids):
            next_start, next_end = offsets[cursor]
            next_label = LABELS[label_ids[cursor]] if 0 <= label_ids[cursor] < len(LABELS) else "O"
            if next_start == next_end or next_label != f"I-{kind}" or next_start > char_end:
                break
            tokens.append(cursor)
            char_end = next_end
            cursor += 1
        confidence = min(probabilities[token] for token in tokens)
        if confidence >= threshold and 0 <= start <= char_end <= len(points):
            entities.append(Entity("".join(points[start:char_end]), kind, start, char_end, confidence))
        index = cursor if cursor > index + 1 else index + 1
    return entities


def keep_entity(entity: Entity, segment: Segment) -> bool:
    length = len(list(segment.text))
    if segment.artificial_left and entity.start == 0:
        return False
    if segment.artificial_right and entity.end == length:
        return False
    if segment.start + entity.end <= segment.owned_start:
        return False
    return True


def dedupe_entities(entities: list[Entity]) -> list[Entity]:
    best: dict[tuple[str, int, int], Entity] = {}
    for entity in entities:
        key = (entity.tag, entity.start, entity.end)
        prev = best.get(key)
        if prev is None or entity.confidence > prev.confidence:
            best[key] = entity
    return sorted(best.values(), key=lambda item: (item.start, item.end, item.tag))
