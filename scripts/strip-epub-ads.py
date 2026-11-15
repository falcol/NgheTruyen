"""Strip known advertising / source-link lines from EPUBs (whole-line patterns only).

Usage: python3 -I scripts/strip-epub-ads.py --out /tmp/stripped [--src epub] [--only SUBSTR]
Never overwrites --src; writes cleaned copies into --out and prints per-pattern counts.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
import zipfile
from collections import Counter

from lxml import etree

BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "center", "section"}

# Whole-line patterns (matched against whitespace-normalised full text of a block).
LINE_PATTERNS = [
    ("dtv-readmore", r"Đọc thêm truyện hay tại:?\s*DTV-EBOOK(\.COM(\.VN)?)?"),
    ("dtv-name", r"DTV-EBOOK(\.COM(\.VN)?)?"),
    ("dtv-site", r"(www\.)?dtv-ebook\.com"),
    ("dtv-download", r"Tải ebook:\s*dtv-ebook\.com"),
    ("thichcode-edit", r"Chỉnh sửa\s*:\s*truyen\.thichcode\.net"),
    ("thichcode-dl", r"(download (PRC|ebook) mới nhất|xem online|xem) tại truyen\.thichcode\.net"),
    ("contact-bitly", r"Liên hệ: bit\.ly/LHHACD.*"),
    ("zalo-sell", r"Zalo:[\d ]+,\s*bán sách truyện giá rẻ"),
    ("zalo-maker", r"Người làm ebook: zalo[\d ]+"),
    ("thienloi", r"⚡ Thiên-Lôi-Trúc \.com ⚡ Dịch truyện bằng AI"),
    ("facebook", r"https?://www\.facebook\.com/hahienquan"),
    ("truyencuatui", r"https?://truyencuatui\.net/?"),
    ("tang-them-nhac-nho", r"Tăng thêm đổi mới nhắc nhở,.*hòm thư\."),
    ("xem-song-lai", r"Xem sống lại (Thần Cấp|cấp thần) phá gia chi tử chương mới nhất đến cơn gió mạnh văn học \(\)"),
    ("url-scheme-fragment", r"https?:/{1,2}"),
    ("thienloi-promo", r"Bạn tưởng là truyện thường\? Nhưng có dấu ấn ✧ Thiên‧Lôi‧Trúc ✧"),
    ("69sach", r"Truyện mới nhất được đăng tại 69sach\.com!"),
]
LINE_RES = [(n, re.compile(r"^(?:%s)$" % p, re.I | re.U)) for n, p in LINE_PATTERNS]

# Obfuscated thichcode lines ("d.o w n l oad e,bo.o,k ..."): compared after dropping spaces/.,-: and lowercasing.
SKEL_RE = re.compile(
    r"^(?:(?:downloadebook|downloadprc)mớinhất|xemonline|xem)tạitruyenthichcodenet$"
    r"|^chỉnhsửabởitruyenthichcodenet$|^nguồntruyenthichcodenet$|^truyệnđượccopytạitruyenthichcodenet$"
    r"|^truyencuatuinet$"
)
SKEL_DROP = re.compile(r"[\s\u00a0,.\-:]")
STRAY_BEFORE = re.compile(r"\[\d+\]\s*$")
STRAY_AFTER = re.compile(r"^\s*\[\d+\]")

# Tail-only patterns cut from the end of a text node (keeps the rest of the line).
TAIL_RES = [("truyenfull-source", re.compile(r"\s*Nguồn:\s*https?://truyenfull\.vn\s*$", re.I))]

# Inline ads glued inside a text node; matched on an NFKC view (full-width obfuscation), cut by span.
_PRE = r"(?:(?:ghé thăm|(?:❊\s*)?đọc truyện (?:tại|ở|với)|truy cập|đăng nhập)\s*)?"
_CUA = r"(?:\[\s*truyen cua tui\s*\.\s*net\s*\]\s*)?(?:https?://)?truyencuatui\s*\.\s*net/?"
_POST = r"(?:\s*để đọc truyện(?:\s*-\s*mobile)?)?"
INLINE_RES = [
    ("inline-truyencuatui", re.compile(_PRE + _CUA + _POST, re.I)),
    ("inline-thichcode", re.compile(
        r"(?:chỉnh sửa(?: bởi)?|xem online tại|xem tại|download (?:ebook|prc) mới nhất tại|truyện được copy tại|nguồn)\s*:?\s*truyen\.thichcode\.net",
        re.I)),
    ("inline-zalo", re.compile(r"(?:người làm ebook:\s*)?zalo:?\s*0\d[\d ]{7,10}", re.I)),
    ("inline-truyencuatui-bracket", re.compile(
        r"\[[^\[\]]{0,40}?truyen[^\[\]]{0,15}?cua[^\[\]]{0,15}?tui[^\[\]]{0,20}?net\s*[\]≫】]?", re.I)),
    ("inline-tang-them", re.compile(r"Tăng thêm đổi mới nhắc nhở,[^.]*?hòm thư\.\s*", re.I)),
    ("inline-xem-song-lai", re.compile(
        r"Xem sống lại (?:Thần Cấp|cấp thần) phá gia chi tử chương mới nhất đến(?: cơn gió mạnh văn học)? \(\)\s*", re.I)),
    ("inline-thienloi-mark", re.compile(r"✧\s*Thiên‧Lôi‧Trúc\s*✧")),
    ("inline-dtv-ebook", re.compile(r"ebook:\s*https?://www\.dtv-ebook\.com", re.I)),
]
LINK_AD_RE = re.compile(r"^(?:https?://)?(?:www\.)?(truyen\.thichcode\.net|dtv-ebook\.com|truyencuatui\.net)/?$", re.I)
LABEL_RE = re.compile(r"(?:chỉnh sửa|ebook)\s*:\s*$", re.I)
# Obfuscated inline thichcode phrases: matched on a skeleton (no spaces/.,-:), mapped back to text spans.
SKEL_INLINE = re.compile(
    r"(?:chỉnhsửabởi|chỉnhsửa|nguồn|truyệnđượccopytại|xemonlinetại|xemtại|downloadebookmớinhấttại|downloadprcmớinhấttại)"
    r"truyenthichcodenet",
    re.I,
)
LOG = []  # texts removed from the book being processed (for verification)

WS = re.compile(r"[\s\u00a0\u200b\u034f]+")


def norm(s):
    return WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


def match_line(text):
    for name, rx in LINE_RES:
        if rx.match(text):
            return name
    nk = "".join(unicodedata.normalize("NFKC", ch) for ch in text)
    if SKEL_RE.match(SKEL_DROP.sub("", nk).lower()):
        return "thichcode-obfuscated"
    return None


def cut_inline(text, counts):
    """Remove inline ad spans from one text node; returns new text."""
    nk = "".join(unicodedata.normalize("NFKC", ch) for ch in text)
    if len(nk) != len(text):
        return text
    spans = []
    for name, rx in INLINE_RES:
        for m in rx.finditer(nk):
            spans.append((m.start(), m.end(), name))
    keep = [i for i, ch in enumerate(nk) if not SKEL_DROP.match(ch)]
    skel = "".join(nk[i] for i in keep)
    for m in SKEL_INLINE.finditer(skel):
        spans.append((keep[m.start()], keep[m.end() - 1] + 1, "inline-thichcode-obf"))
    if not spans:
        return text
    spans.sort(key=lambda sp: (sp[0], -sp[1]))  # longest span first at the same start
    out, pos = [], 0
    for a, b, name in spans:
        if a < pos:
            continue
        out.append(text[pos:a])
        LOG.append(text[a:b])
        counts[name] += 1
        pos = b
    out.append(text[pos:])
    return "".join(out)


def cut_cross_block(root, counts):
    """Ad URL split over two adjacent text-only blocks (e.g. '...truyencua' | 'Tui.net/ ...')."""
    for a in list(root.iter()):
        if not isinstance(a.tag, str) or etree.QName(a).localname not in BLOCK or len(a):
            continue
        b = a.getnext()
        if b is None or not isinstance(b.tag, str) or etree.QName(b).localname not in BLOCK or len(b):
            continue
        ta, tb = a.text or "", b.text or ""
        comb = ta + tb
        nk = "".join(unicodedata.normalize("NFKC", ch) for ch in comb)
        if len(nk) != len(comb):
            continue
        for m in INLINE_RES[0][1].finditer(nk):
            if m.start() < len(ta) < m.end():
                LOG.append(ta[m.start():])
                LOG.append(tb[: m.end() - len(ta)])
                a.text, b.text = ta[: m.start()], tb[m.end() - len(ta):]
                counts["cross-block-truyencuatui"] += 1
                # A block left with no text at all only held the ad fragment: drop it.
                for blk in (a, b):
                    if not (blk.text or "").strip() and not len(blk):
                        remove_keep_tail(blk)
                break


def strip_page_markers(el):
    """Drop the stray '[n]' page markers that wrap the dtv-ebook download block."""
    prev = el.getprevious()
    if prev is not None:
        if prev.tail and STRAY_BEFORE.search(prev.tail):
            LOG.append(STRAY_BEFORE.search(prev.tail).group(0))
            prev.tail = STRAY_BEFORE.sub("", prev.tail)
    else:
        parent = el.getparent()
        if parent.text and STRAY_BEFORE.search(parent.text):
            LOG.append(STRAY_BEFORE.search(parent.text).group(0))
            parent.text = STRAY_BEFORE.sub("", parent.text)
    if el.tail and STRAY_AFTER.search(el.tail):
        LOG.append(STRAY_AFTER.search(el.tail).group(0))
        el.tail = STRAY_AFTER.sub("", el.tail)


def remove_keep_tail(el):
    parent = el.getparent()
    tail = el.tail
    if tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(el)


def strip_tree(root, counts):
    # 1) whole-block lines (leaf-most first so nested blocks are handled once)
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or etree.QName(el).localname not in BLOCK:
            continue
        if el.getparent() is None or any(
            isinstance(c.tag, str) and etree.QName(c).localname in BLOCK for c in el
        ):
            continue
        text = norm("".join(el.itertext()))
        if not text:
            continue
        name = match_line(text)
        if name:
            counts[name] += 1
            LOG.append(text)
            if name == "dtv-download":
                strip_page_markers(el)
            remove_keep_tail(el)
    # 2) tail cuts inside a text node
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for name, rx in TAIL_RES:
            if el.text and rx.search(el.text):
                LOG.append(rx.search(el.text).group(0))
                el.text = rx.sub("", el.text)
                counts[name] += 1
            if el.tail and rx.search(el.tail):
                LOG.append(rx.search(el.tail).group(0))
                el.tail = rx.sub("", el.tail)
                counts[name] += 1
    # 3) inline ads glued into text nodes
    emptied = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.text:
            new = cut_inline(el.text, counts)
            if new != el.text and not new.strip() and not len(el) \
                    and etree.QName(el).localname in BLOCK:
                emptied.append(el)
            el.text = new
        if el.tail:
            el.tail = cut_inline(el.tail, counts)
    # A block that held only an inline ad would be left as an empty element: drop it.
    for el in emptied:
        if el.getparent() is not None:
            remove_keep_tail(el)
    cut_cross_block(root, counts)
    # 4) link ads: <a> whose text is an ad domain, plus its "Chỉnh sửa :" / "Ebook:" label
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or etree.QName(el).localname != "a":
            continue
        if not LINK_AD_RE.match(norm("".join(el.itertext()))):
            continue
        LOG.append("".join(el.itertext()))
        prev = el.getprevious()
        holder_text = (prev.tail if prev is not None else el.getparent().text) or ""
        lm = LABEL_RE.search(holder_text)
        if lm:
            LOG.append(lm.group(0))
            holder_text = holder_text[: lm.start()]
            if prev is not None:
                prev.tail = holder_text
            else:
                el.getparent().text = holder_text
        counts["link-ad"] += 1
        remove_keep_tail(el)


RAW_BLOCK_RE = re.compile(r"<(p|div)\b[^>]*>([^<]*)</\1>", re.I)


RAW_EBOOK_LINK_RE = re.compile(
    r'<b><span[^>]*>Ebook:(?:&nbsp;|\s)*</span></b><span[^>]*><b><a href="https?://www\.dtv-ebook\.com/?">'
    r'https?://www\.dtv-ebook\.com</a></b></span>'
)


def strip_raw(data, counts):
    text = data.decode("utf-8")

    def repl_link(m):
        counts["raw-ebook-link"] += 1
        LOG.append("Ebook: http://www.dtv-ebook.com")
        return ""

    text = RAW_EBOOK_LINK_RE.sub(repl_link, text)

    def repl(m):
        inner = norm(m.group(2).replace("&nbsp;", " ").replace("&#160;", " "))
        name = match_line(inner)
        if name:
            counts[name] += 1
            LOG.append(inner)
            return ""
        return m.group(0)

    return RAW_BLOCK_RE.sub(repl, text).encode("utf-8")


def process(src, dst):
    counts = Counter()
    LOG.clear()
    zin = zipfile.ZipFile(src)
    with zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith((".xhtml", ".html", ".htm")):
                try:
                    root = etree.fromstring(data, etree.XMLParser(resolve_entities=False))
                except etree.XMLSyntaxError:
                    # Some books use HTML-only &nbsp;; retry with the numeric entity.
                    raw_data = data
                    try:
                        data = data.replace(b"&nbsp;", b"&#160;")
                        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False))
                    except etree.XMLSyntaxError:
                        # Ill-formed source: remove only leaf blocks that hold exactly an ad line.
                        data = strip_raw(raw_data, counts)
                        root = None
                if root is not None:
                    before = sum(counts.values())
                    strip_tree(root, counts)
                    if sum(counts.values()) != before:
                        data = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
            comp = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zout.writestr(info.filename, data, compress_type=comp)
    return counts, list(LOG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "epub"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    if os.path.abspath(a.out) == os.path.abspath(a.src):
        sys.exit("--out must differ from --src")
    os.makedirs(a.out, exist_ok=True)
    for f in sorted(os.listdir(a.src)):
        if not f.endswith(".epub") or (a.only and a.only not in unicodedata.normalize("NFC", f)):
            continue
        c, removed = process(os.path.join(a.src, f), os.path.join(a.out, f))
        with open(os.path.join(a.out, f + ".removed.json"), "w", encoding="utf-8") as fh:
            json.dump(removed, fh, ensure_ascii=False)
        print(f"{unicodedata.normalize('NFC', f)[:48]:48s} removed={sum(c.values()):6d} {dict(c)}")


if __name__ == "__main__":
    main()
