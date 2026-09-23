"""File-tab chunking: headings, paragraph joins, then sentence pieces."""

from __future__ import annotations

import re
from collections.abc import Callable

from vp.engine import Engine

SENTENCE_BOUNDARIES = frozenset("。！？!?；;")
TRAILING_QUOTES = frozenset("\u201d\u2019\u300d\u300f\u300b\"'")
SOFT_LIMIT = 4000
HARD_LIMIT = 6000
HEADING_RE = re.compile(
    r"^(?:第[0-9零〇一二三四五六七八九十百千万两]+[章节回卷集部篇幕]|序章|楔子|尾声|后记)$"
)


def _trim_line(line: str) -> str:
    return re.sub(r"^\s+|\s+$", "", line or "")


def build_base_chunks(text: str) -> list[dict[str, str]]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    chunks: list[dict[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        chunks.append({"text": "\n".join(buffer), "type": "paragraph"})
        buffer.clear()

    for line in lines:
        trimmed = _trim_line(line)
        if not trimmed:
            flush()
            chunks.append({"text": "", "type": "blank"})
            continue
        if HEADING_RE.match(trimmed):
            flush()
            chunks.append({"text": trimmed, "type": "heading"})
            continue
        buffer.append(trimmed)
    flush()
    return chunks


def _needs_gap(parts: list[str], piece: str) -> bool:
    """Space after a sentence or closing quote before the next piece."""
    if not parts or not piece or piece[0].isspace():
        return False
    prev = parts[-1]
    return bool(prev) and not prev[-1].isspace()


def _boundary_end(source: str, idx: int) -> int:
    end = idx + 1
    while end < len(source) and source[end] in TRAILING_QUOTES:
        end += 1
    return end


def split_oversized(source: str, soft: int = SOFT_LIMIT, hard: int = HARD_LIMIT) -> list[str]:
    if not source or len(source) <= hard:
        return [source]
    pieces: list[str] = []
    start = 0
    last_boundary = -1
    n = len(source)
    idx = 0
    while idx < n:
        if source[idx] in SENTENCE_BOUNDARIES:
            last_boundary = _boundary_end(source, idx)
        current_len = idx + 1 - start
        if current_len >= hard:
            cut = last_boundary if last_boundary > start + (soft // 2) else idx + 1
            if cut > start:
                pieces.append(source[start:cut])
                start = cut
                while start < n and source[start].isspace():
                    start += 1
                last_boundary = -1
            idx = start
            continue
        if last_boundary > start and (last_boundary - start) >= soft:
            pieces.append(source[start:last_boundary])
            start = last_boundary
            while start < n and source[start].isspace():
                start += 1
            last_boundary = -1
            idx = start
            continue
        idx += 1
    if start < n:
        pieces.append(source[start:])
    return pieces or [source]


def build_file_chunks(
    text: str,
    *,
    soft: int = SOFT_LIMIT,
    hard: int = HARD_LIMIT,
) -> list[dict[str, str]]:
    expanded: list[dict[str, str]] = []
    for chunk in build_base_chunks(text):
        if not chunk["text"] or chunk["type"] in ("blank", "heading"):
            chunk["glue"] = "\n" if expanded else ""
            expanded.append(chunk)
            continue
        pieces = split_oversized(chunk["text"], soft, hard)
        for pi, piece in enumerate(pieces):
            glue = ""
            if expanded:
                glue = "\n" if pi == 0 else ""
            expanded.append({"text": piece, "type": chunk["type"] or "paragraph", "glue": glue})
    return expanded


def translate_piecewise(text: str, translate: Callable[[str], str]) -> str:
    source = str(text or "")
    if not source:
        return ""
    translated: list[str] = []
    start = 0
    n = len(source)
    idx = 0
    while idx < n:
        if source[idx] not in SENTENCE_BOUNDARIES:
            idx += 1
            continue
        end = _boundary_end(source, idx)
        if end > start:
            part = source[start:end]
            if part:
                piece = translate(part)
                if _needs_gap(translated, piece):
                    translated.append(" ")
                translated.append(piece)
        sep_start = end
        while end < n and source[end].isspace():
            end += 1
        if end > sep_start:
            sep = source[sep_start:end]
            if "\n" in sep or "\r" in sep:
                sep = sep.replace("\r\n", "\n")
                sep = re.sub(r"[ \t]*\n[ \t]*", "\n", sep)
                sep = re.sub(r"\n{3,}", "\n\n", sep)
                translated.append(sep)
        start = end
        idx = start
    if start < n:
        part = source[start:]
        if part:
            piece = translate(part)
            if _needs_gap(translated, piece):
                translated.append(" ")
            translated.append(piece)
    return "".join(translated)


def translate_chunks(
    chunks: list[dict[str, str]],
    translate: Callable[[str], str],
    on_progress: Callable[[int, int], None] | None = None,
) -> str:
    out: list[str] = []
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        piece = translate_piecewise(chunk.get("text") or "", translate) if chunk.get("text") else ""
        if i > 0:
            glue = chunk.get("glue")
            if not isinstance(glue, str):
                glue = "\n"
            if glue == "" and _needs_gap(out, piece):
                glue = " "
            out.append(glue)
        out.append(piece)
        if on_progress:
            on_progress(i + 1, total)
    return "".join(out)


def translate_file(
    text: str,
    engine: Engine,
    *,
    mode: str = "vietphrase",
    overlay: list[tuple[str, str, int]] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    soft: int = SOFT_LIMIT,
    hard: int = HARD_LIMIT,
) -> str:
    source = engine.convert(text or "")
    chunks = build_file_chunks(source, soft=soft, hard=hard)
    if mode == "hanviet":
        translate = engine.hanviet
    else:
        def translate(part: str) -> str:
            return engine.translate(part, overlay)
    return translate_chunks(chunks, translate, on_progress)
