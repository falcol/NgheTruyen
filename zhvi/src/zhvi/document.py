"""Lossless TXT parser (thiet ke muc 7).

Moi node lap day du document bang (char_start, char_end). Export dung lai tu
cac node -> rebuild byte-for-byte duoc source, khong mat paragraph/heading/
blank line. Heading la block rieng; paragraph giu nguyen prefix/suffix whitespace
(e.g. thut le U+3000 U+3000 cua truyen Trung) de rebuild lossless.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

NodeType = Literal["heading", "paragraph", "blank"]

# Chapter presets: 第...章 / 回 / 节 (simple + traditional variants).
CHAPTER_PRESET_RE = re.compile(
    r"^\s*[第][零一二三四五六七八九十百千万两0-9０-９]{1,12}\s*[章节回節]"
)
MAX_HEADING_CHARS = 80
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
QUOTE_PAIRS = (("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"), ("（", "）"), ("(", ")"))


@dataclass(frozen=True)
class Node:
    ordinal: int
    node_type: NodeType
    char_start: int  # vao normalized_text toan document
    char_end: int
    raw_text: str  # slice chinh xac 100% — rebuild dung cai nay
    chapter_id: int  # -1 = preface truoc heading dau tien

    @property
    def is_translatable(self) -> bool:
        return self.node_type in ("heading", "paragraph")

    @property
    def prefix(self) -> str:
        if not self.is_translatable:
            return self.raw_text
        stripped = self.raw_text.lstrip(" \t\u3000")
        return self.raw_text[: len(self.raw_text) - len(stripped)]

    @property
    def suffix(self) -> str:
        if not self.is_translatable:
            return ""
        body = self.raw_text.rstrip("\r\n")
        trailing_nl = self.raw_text[len(body) :]
        stripped = body.rstrip(" \t\u3000")
        return body[len(stripped) :] + trailing_nl

    @property
    def content(self) -> str:
        """Noi dung can dich (da cat whitespace dau/cuoi, giu nguyen newline cuoi)."""
        return self.raw_text.strip(" \t\u3000\r\n")


@dataclass
class Document:
    normalized_text: str
    nodes: list[Node]
    newline_style: str  # "\n" | "\r\n"
    chapter_count: int

    def byte_offsets(self, encoding: str = "utf-8") -> list[tuple[int, int]]:
        """(byte_start, byte_end) moi node theo encoding cua source."""
        out: list[tuple[int, int]] = []
        for n in self.nodes:
            b_start = len(self.normalized_text[: n.char_start].encode(encoding))
            b_end = len(self.normalized_text[: n.char_end].encode(encoding))
            out.append((b_start, b_end))
        return out

    def rebuild(self) -> str:
        """Dung lai toan bo document tu cac node — phai bang normalized_text."""
        return "".join(n.raw_text for n in self.nodes)

    def translatable_nodes(self) -> list[Node]:
        return [n for n in self.nodes if n.is_translatable]


@dataclass
class InspectReport:
    total_chars: int = 0
    total_bytes: int = 0
    node_counts: dict[str, int] = field(default_factory=dict)
    heading_count: int = 0
    suspicious_headings: list[str] = field(default_factory=list)
    long_paragraphs: int = 0  # > 3 * block_max_chars
    unbalanced_quotes: int = 0
    cjk_ratio: float = 0.0
    newline_style: str = "\n"
    chapter_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ambiguous_chapters(self) -> bool:
        return self.chapter_count == 0 and self.heading_count == 0 and self.total_chars > 0


def _detect_chapter(line: str, custom_re: re.Pattern[str] | None) -> bool:
    if len(line.strip()) > MAX_HEADING_CHARS:
        return False
    if custom_re is not None:
        return bool(custom_re.match(line.strip()))
    return bool(CHAPTER_PRESET_RE.match(line.strip()))


def parse_document(
    text: str,
    *,
    chapter_detection: str = "auto",
    chapter_regex: str = "",
) -> Document:
    """Parse lossless. chapter_detection: auto | strict | none.

    auto: preset 第...章/回/节 (+ regex neu co), fallback 1 chuong neu khong thay heading.
    strict: nhu auto nhung bao cao ambiguous trong inspect.
    none: khong tim heading, tat ca 1 chuong.
    """
    custom_re = re.compile(chapter_regex) if chapter_regex else None
    newline_style = "\r\n" if "\r\n" in text else "\n"

    nodes: list[Node] = []
    ordinal = 0
    chapter_id = -1 if chapter_detection != "none" else 0
    pos = 0
    n = len(text)

    def add(node_type: NodeType, start: int, end: int) -> None:
        nonlocal ordinal
        nodes.append(
            Node(
                ordinal=ordinal,
                node_type=node_type,
                char_start=start,
                char_end=end,
                raw_text=text[start:end],
                chapter_id=chapter_id,
            )
        )
        ordinal += 1

    while pos < n:
        line_end = text.find("\n", pos)
        if line_end == -1:
            line_end = n
            include_nl = False
        else:
            include_nl = True
        body_end = line_end - 1 if include_nl and text[line_end - 1 : line_end] == "\r" else line_end
        line = text[pos:body_end]
        nl_end = line_end + 1 if include_nl else n
        if line.strip() == "":
            # gom blank line vao node blank (structural)
            if nodes and nodes[-1].node_type == "blank" and nodes[-1].char_end == pos:
                last = nodes[-1]
                nodes[-1] = Node(
                    ordinal=last.ordinal,
                    node_type="blank",
                    char_start=last.char_start,
                    char_end=nl_end,
                    raw_text=text[last.char_start : nl_end],
                    chapter_id=last.chapter_id,
                )
            else:
                add("blank", pos, nl_end)
        else:
            is_heading = chapter_detection != "none" and _detect_chapter(line, custom_re)
            if is_heading:
                chapter_id += 1
                add("heading", pos, nl_end)
            else:
                add("paragraph", pos, nl_end)
        pos = nl_end

    return Document(
        normalized_text=text,
        nodes=nodes,
        newline_style=newline_style,
        chapter_count=chapter_id + 1 if chapter_id >= 0 else 0,
    )


def inspect_document(doc: Document, *, block_max_chars: int = 2000) -> InspectReport:
    rep = InspectReport(
        total_chars=len(doc.normalized_text),
        total_bytes=len(doc.normalized_text.encode("utf-8")),
        newline_style=doc.newline_style,
        chapter_count=doc.chapter_count,
    )
    counts: dict[str, int] = {}
    cjk = 0
    letters = 0
    for node in doc.nodes:
        counts[node.node_type] = counts.get(node.node_type, 0) + 1
        if node.is_translatable:
            content = node.content
            cjk += len(CJK_RE.findall(content))
            letters += sum(1 for ch in content if not ch.isspace())
            if node.node_type == "heading":
                rep.heading_count += 1
                if len(content) > MAX_HEADING_CHARS // 2:
                    rep.suspicious_headings.append(content[:60])
            if len(content) > 3 * block_max_chars:
                rep.long_paragraphs += 1
            for open_ch, close_ch in QUOTE_PAIRS:
                if content.count(open_ch) != content.count(close_ch):
                    rep.unbalanced_quotes += 1
                    break
    rep.node_counts = counts
    rep.cjk_ratio = cjk / letters if letters else 0.0
    if rep.chapter_count == 0 and rep.heading_count == 0:
        rep.warnings.append("Khong phat hien heading chuong — fallback 1 chuong duyet")
    if rep.suspicious_headings:
        rep.warnings.append(f"{len(rep.suspicious_headings)} heading nghi ngo (dai bat thuong)")
    if rep.unbalanced_quotes:
        rep.warnings.append(f"{rep.unbalanced_quotes} doan ngoac/quote khong can bang")
    return rep
