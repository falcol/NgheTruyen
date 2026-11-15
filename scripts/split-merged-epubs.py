#!/usr/bin/env python3
"""Split merged-chapter EPUBs.

Some EPUBs pack many original chapters ("Chương N: ...") into one spine item
(~100K chars/page). This tool cuts those spine items at chapter headings,
writes one XHTML file per original chapter, and rebuilds manifest / spine /
NCX / NAV so readers see one chapter per file.

Originals are backed up to epub/original/ before rewriting. Books already
backed up are skipped, so re-runs are no-ops. Books without any splittable
spine item are left untouched.

Usage:
  python3 scripts/split-merged-epubs.py            # process all books
  python3 scripts/split-merged-epubs.py --dry-run  # report only
  python3 scripts/split-merged-epubs.py --only "Luc Tich"
"""
import argparse
import os
import posixpath
import re
import shutil
import sys
import unicodedata
import zipfile
from copy import deepcopy
from urllib.parse import unquote

from lxml import etree

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPUB_DIR = os.path.join(REPO, "epub")
BACKUP_DIR = os.path.join(EPUB_DIR, "original")

XH = "{http://www.w3.org/1999/xhtml}"
EPUB_OPS = "{http://www.idpf.org/2007/ops}"
NCX_NS = "{http://www.daisy.org/z3986/2005/ncx/}"
OPF_NS = "{http://www.idpf.org/2007/opf}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"

BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "dl",
    "dt", "dd", "blockquote", "td", "th", "tr", "table", "center", "section",
    "article", "aside", "header", "footer", "figure", "figcaption", "pre",
}
HEADING_RE = re.compile(
    r"(?<!\S)(?:Q\d+[-–]\s*)?(?:(?:Chương|CHƯƠNG)\s+\d+(?:[\.\-]\d+)?(?:\s*[:\.\-–]|\s+|$)|chương\s+\d+(?:[\.\-]\d+)?\s*[:\.\-–])",
    re.UNICODE,
)
GLUED_RE = re.compile(
    r"(?<=\S)(?:Q\d+[-–]\s*)?(?:(?:Chương|CHƯƠNG)\s+\d+(?:[\.\-]\d+)?(?:\s*[:\.\-–]|\s+|$)|chương\s+\d+(?:[\.\-]\d+)?\s*[:\.\-–])",
    re.UNICODE,
)
HEADING_START_RE = re.compile(
    r"^\s*(?:Q\d+[-–]\s*)?(?:(?:Chương|CHƯƠNG)\s+\d+(?:[\.\-]\d+)?(?:\s*[:\.\-–]|\s+|$)|chương\s+\d+(?:[\.\-]\d+)?\s*[:\.\-–])",
    re.UNICODE,
)
JUNK_CUT_RE = re.compile(r"\s*(?:Chỉnh sửa|truyen\.|https?://)")
DUP_TITLE_RE = re.compile(
    r"^((?:Q\d+[-–]\s*)?(?:Chương|chương|CHƯƠNG)\s+\d+(?:[\.\-]\d+)?\s*[:\.\-–]?\s*)(.{8,}?)(?:\s+\2)(?=\s|$)",
    re.UNICODE,
)
METADATA_RE = re.compile(r"Số chương\s*:|Trạng thái\s*:|Tác giả\s*:|File PRC|Giới thiệu\s*:", re.UNICODE)

MERGED_BOOKS = {
    "Ai Bảo Hắn Tu Tiên - Tối Bạch Đích Ô Nha.epub",
    "Linh Cảnh Hành Giả - Mại Báo Tiểu Lang Quân.epub",
    "Luc Tich Chi Tinh Ha Sang The [C] - Cuong Tieu Ba La Duong.epub",
    "Nương Tử Nhà Ta, Không Thích Hợp - Nhất Thiền Tri Hạ.epub",
    "Ta Trở Thành Phú Nhị Đại Phản Phái - Tam Tam Đắc Cửu.epub",
    "Trùng Nhiên - Áo Nhĩ Lương Khảo Tầm Ngư Bảo.epub",
    "Tuyệt Phẩm Thiên Y - Diệp Thiên Nam.epub",
    "Từ Bệnh Viện Tâm Thần Đi Ra Cường Giả - Tân Phong.epub",
}

MIN_SEGMENT_CHARS = 300
PREFACE_MAX_CHARS = 10000
GLUED_HEADING_JUNK_COUNT = 3
TITLE_MAX_CHARS = 80
TITLE_SCAN_CHARS = 100


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def el_text(el):
    return "".join(el.itertext())


def heading_title(text):
    """Extract a clean chapter title from text that starts at a heading match."""
    raw = re.sub(r"\s+", " ", text[:TITLE_SCAN_CHARS]).strip()
    junk = JUNK_CUT_RE.search(raw)
    if junk and junk.start() > 0:
        raw = raw[: junk.start()].strip()
    dup = DUP_TITLE_RE.match(raw)
    if dup:
        raw = dup.group(1) + dup.group(2)
    if len(raw) > TITLE_MAX_CHARS:
        paren = re.match(r"^(.{0,80}?\)\s)", raw)
        if paren:
            raw = paren.group(1).strip()
        else:
            last_space = raw.rfind(" ", 0, TITLE_MAX_CHARS)
            raw = raw[: last_space if last_space > 40 else TITLE_MAX_CHARS]
    return raw


def norm_title(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s or ""))


def normalize_href(href):
    return unquote(href.split("#")[0]).replace("\\", "/").lstrip("/")


def opf_dir_of(opf_zipname):
    d = posixpath.dirname(opf_zipname)
    return d + "/" if d else ""


def href_to_zipname(href, base_dir):
    path = normalize_href(href)
    if base_dir:
        path = posixpath.join(base_dir, path)
    return posixpath.normpath(path)


# ---------------------------------------------------------------------------
# Body flattening + splitting
# ---------------------------------------------------------------------------

class Unit:
    """A serializable chunk of body content (leaf block or wrapped inline run)."""

    def __init__(self):
        self.items = []  # ("el", element) | ("text", str)
        self.wrapper_attrs = {}
        self.wrapper_tag = "p"

    def text(self):
        out = []
        for kind, val in self.items:
            out.append(val if kind == "text" else el_text(val))
        return "".join(out)


def walk_units(node, units):
    """Flatten `node` (body or container block) into ordered Units."""
    children = list(node)
    block_children = [c for c in children if local(c.tag) in BLOCK_TAGS]

    if not block_children:
        units.extend(make_leaf_unit(node))
        return

    # Mixed container: inline content between block children becomes run units.
    runs = []  # (kind, val) items collected from node.text / inline children
    text = node.text or ""
    if text.strip():
        runs.append(("text", text))
    for child in children:
        if local(child.tag) in BLOCK_TAGS:
            flush_runs(runs, units)
            walk_units(child, units)
            if child.tail:
                runs.append(("text", child.tail))
        else:
            runs.append(("el", child))
            if child.tail:
                runs.append(("text", child.tail))
    flush_runs(runs, units)


def flush_runs(runs, units):
    if not runs:
        return
    if all((kind == "text" and not val.strip()) for kind, val in runs):
        runs.clear()
        return
    unit = Unit()
    unit.items = list(runs)
    units.append(unit)
    runs.clear()


def make_leaf_unit(node):
    """Leaf block: split at heading matches inside its direct text stream.

    Returns a list of Units (single unit when no split point exists).
    """
    items = []
    if node.text:
        items.append(("text", node.text))
    for child in node:
        items.append(("el", child))
        items.append(("text", child.tail or ""))

    pieces, current = [], []
    for kind, val in items:
        if kind == "el":
            current.append((kind, val))
            continue
        pos = 0
        while True:
            m = HEADING_RE.search(val, pos)
            if not m:
                current.append(("text", val[pos:]))
                break
            if m.start() > pos:
                current.append(("text", val[pos : m.start()]))
            if current:
                pieces.append(current)
                current = []
            current.append(("text", val[m.start() :]))
            break

    if not pieces:
        unit = Unit()
        unit.wrapper_tag = local(node.tag)
        unit.wrapper_attrs = dict(node.attrib)
        unit.items = items
        return [unit]

    if current:
        pieces.append(current)

    units_out = []
    for piece in pieces:
        unit = Unit()
        unit.wrapper_tag = local(node.tag)
        unit.wrapper_attrs = dict(node.attrib)
        unit.items = piece
        units_out.append(unit)
    return units_out


def chapter_starts(units):
    return [i for i, u in enumerate(units) if HEADING_START_RE.match(u.text())]


def chapter_title_from(units):
    for u in units:
        t = u.text()
        if HEADING_START_RE.match(t):
            return heading_title(t)
    return ""


def merge_chapters(units, fallback_title, luc_tich=False):
    """Group units into chapters, merging small / TOC-junk chapters forward."""
    starts = chapter_starts(units)
    if not starts:
        return []

    boundaries = list(starts)
    if starts[0] > 0:
        boundaries.insert(0, 0)  # leading preface
    groups = []
    for i, b in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(units)
        groups.append(units[b:end])

    # Merge small or junk groups into the following one.
    merged = []
    pending = None
    for gi, g in enumerate(groups):
        text = "".join(u.text() for u in g)
        is_junk = not luc_tich and len(GLUED_RE.findall(text)) >= GLUED_HEADING_JUNK_COUNT
        if gi == 0 and starts[0] > 0 and METADATA_RE.search(text):
            is_junk = True  # book metadata page
        is_small = (len(text.strip()) < MIN_SEGMENT_CHARS
                    and not luc_tich and not text.rstrip().endswith("Chương VIP"))
        if is_small or is_junk:
            if pending is None:
                pending = list(g)
            else:
                pending.extend(g)
        elif pending is not None:
            pending.extend(g)
            merged.append(pending)
            pending = None
        else:
            merged.append(g)
    if pending is not None:
        merged.append(pending)

    if len(merged) < 2:
        return []

    chapters = []
    for g in merged:
        title = chapter_title_from(g)
        chapters.append({"title": title or fallback_title, "units": g})
    return chapters


# ---------------------------------------------------------------------------
# XHTML item processing
# ---------------------------------------------------------------------------

def serialize_doc(orig_root, pieces):
    """Build a new XHTML doc: original head + body attrs, `pieces` as content."""
    doc = deepcopy(orig_root)
    body = None
    for el in doc.iter():
        if local(el.tag) == "body":
            body = el
            break
    if body is None:
        raise ValueError("no body element")

    for child in list(body):
        body.remove(child)
    body.text = None

    for piece in pieces:
        append_piece(body, piece)
        # Keep a newline between top-level pieces so text-based extraction
        # (epub.js textContent) still sees paragraph boundaries.
        body[-1].tail = "\n"

    doctype = doc.getroottree().docinfo.doctype or ""
    xml_body = etree.tostring(doc, encoding="unicode")
    out = '<?xml version="1.0" encoding="utf-8"?>\n'
    if doctype:
        out += doctype + "\n"
    out += xml_body
    return out.encode("utf-8")


def append_piece(body, piece):
    """piece: ("el", element) | ("unit", Unit)."""
    if piece[0] == "el":
        el = deepcopy(piece[1])
        el.tail = None
        body.append(el)
        return
    unit = piece[1]
    wrapper = etree.SubElement(body, XH + unit.wrapper_tag)
    for k, v in unit.wrapper_attrs.items():
        wrapper.set(k, v)

    text_parts = []
    children = []
    for kind, val in unit.items:
        if kind == "text":
            if children:
                children[-1].tail = (children[-1].tail or "") + val
            else:
                text_parts.append(val)
        else:
            el = deepcopy(val)
            el.tail = None
            children.append(el)
    if text_parts:
        wrapper.text = "".join(text_parts)
    for c in children:
        wrapper.append(c)


def split_item(raw_bytes, fallback_title, luc_tich=False):
    """Return {root, units, starts0, chapters} or None if not parseable/empty."""
    parser = etree.XMLParser(recover=False, resolve_entities=False)
    root = etree.fromstring(raw_bytes, parser=parser)
    body = None
    for el in root.iter():
        if local(el.tag) == "body":
            body = el
            break
    if body is None:
        return None

    units = []
    walk_units(body, units)
    units = [u for u in units if u.text().strip()]
    if not units:
        return None

    front = []
    if luc_tich and METADATA_RE.search("".join(u.text() for u in units[:15])):
        # The linked chapter list precedes the first actual h3 chapter heading.
        first = next(i for i, u in enumerate(units)
                     if u.wrapper_tag == "h3" and HEADING_START_RE.match(u.text()))
        front, units = units[:first], units[first:]
    starts = chapter_starts(units)
    starts0 = starts[0] if starts else len(units)
    chapters = merge_chapters(units, fallback_title, luc_tich)
    if front:
        if not chapters:
            chapters = [{"title": chapter_title_from(units), "units": units}]
        chapters.insert(0, {"title": "Giới thiệu", "units": front, "front": True})
    return {"root": root, "units": units, "starts0": starts0, "chapters": chapters}


# ---------------------------------------------------------------------------
# EPUB assembly
# ---------------------------------------------------------------------------

def read_container(z):
    root = etree.fromstring(z.read("META-INF/container.xml"))
    for rf in root.iter():
        if local(rf.tag) == "rootfile":
            full = rf.get("full-path")
            if full:
                return normalize_href(full)
    raise ValueError("no rootfile in container.xml")


def load_opf(z, opf_name):
    root = etree.fromstring(z.read(opf_name))
    base = opf_dir_of(opf_name)
    manifest_el = spine_el = None
    for el in root.iter():
        if local(el.tag) == "manifest" and manifest_el is None:
            manifest_el = el
        if local(el.tag) == "spine" and spine_el is None:
            spine_el = el
    items = {}
    item_order = []
    for it in manifest_el:
        if local(it.tag) != "item":
            continue
        items[it.get("id")] = it
        item_order.append(it)
    spine_ids = [
        it.get("idref") for it in spine_el if local(it.tag) == "itemref"
    ]
    return root, base, manifest_el, spine_el, items, item_order, spine_ids


def load_ncx_titles(z, ncx_zipname, zipnames_with_titles):
    """normalized zip path -> title (first wins)."""
    try:
        root = etree.fromstring(z.read(ncx_zipname))
    except KeyError:
        return
    base = opf_dir_of(ncx_zipname)
    for np in root.iter():
        if local(np.tag) != "navPoint":
            continue
        label = src = None
        for el in np.iter():
            if local(el.tag) == "text" and label is None and local(el.getparent().tag if el.getparent() is not None else "") == "navLabel":
                label = el.text
            if local(el.tag) == "content":
                src = el.get("src")
        if label and src:
            zipname = href_to_zipname(src, base)
            zipnames_with_titles.setdefault(zipname, label.strip())


def load_nav_titles(z, nav_zipname, zipnames_with_titles):
    try:
        root = etree.fromstring(z.read(nav_zipname))
    except (KeyError, etree.XMLSyntaxError):
        return
    base = opf_dir_of(nav_zipname)
    for a in root.iter():
        href = a.get("href") or ""
        if local(a.tag) == "a" and href and not href.startswith(("http://", "https://", "mailto:")):
            title = re.sub(r"\s+", " ", "".join(a.itertext())).strip()
            if title:
                zipname = href_to_zipname(href, base)
                zipnames_with_titles.setdefault(zipname, title)


def find_nav_item(items):
    for it in items.values():
        props = it.get("properties") or ""
        if "nav" in props.split():
            return it
    return None


def find_ncx_item(items, spine_el):
    toc_id = spine_el.get("toc")
    if toc_id and toc_id in items:
        return items[toc_id]
    for it in items.values():
        if (it.get("media-type") or "") == "application/x-dtbncx+xml":
            return it
    return None


def build_ncx(book_title, toc):
    ncx = etree.Element(NCX_NS + "ncx", nsmap={None: NCX_NS[1:-1]}, version="2005-1")
    head = etree.SubElement(ncx, NCX_NS + "head")
    meta = etree.SubElement(head, NCX_NS + "meta")
    meta.set("name", "dtb:uid")
    meta.set("content", "split-merged-epubs")
    for name, content in (("dtb:depth", "1"), ("dtb:totalPageCount", "0"), ("dtb:maxPageNumber", "0")):
        m = etree.SubElement(head, NCX_NS + "meta")
        m.set("name", name)
        m.set("content", content)
    doc_title = etree.SubElement(ncx, NCX_NS + "docTitle")
    etree.SubElement(doc_title, NCX_NS + "text").text = book_title
    nav_map = etree.SubElement(ncx, NCX_NS + "navMap")
    for i, (title, zipname) in enumerate(toc, 1):
        np = etree.SubElement(nav_map, NCX_NS + "navPoint")
        np.set("id", f"np{i}")
        np.set("playOrder", str(i))
        nav_label = etree.SubElement(np, NCX_NS + "navLabel")
        etree.SubElement(nav_label, NCX_NS + "text").text = title
        content = etree.SubElement(np, NCX_NS + "content")
        content.set("src", zipname)
    return etree.tostring(
        ncx, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )


def build_nav(toc):
    html = etree.Element(
        XH + "html",
        nsmap={None: XH[1:-1], "epub": EPUB_OPS[1:-1]},
    )
    html.set("lang", "vi")
    html.set("{http://www.w3.org/XML/1998/namespace}lang", "vi")
    head = etree.SubElement(html, XH + "head")
    etree.SubElement(head, XH + "title").text = "Mục lục"
    meta = etree.SubElement(head, XH + "meta")
    meta.set("charset", "utf-8")
    body = etree.SubElement(html, XH + "body")
    nav = etree.SubElement(body, XH + "nav")
    nav.set(EPUB_OPS + "type", "toc")
    ol = etree.SubElement(nav, XH + "ol")
    for title, zipname in toc:
        li = etree.SubElement(ol, XH + "li")
        a = etree.SubElement(li, XH + "a")
        a.set("href", zipname)
        a.text = title
    etree.indent(html, space="  ")
    return etree.tostring(html, xml_declaration=True, encoding="UTF-8")


def process_book(path, dry_run=False, force=False):
    name = os.path.basename(path)
    if name not in MERGED_BOOKS:
        return f"  skip (not a merged book): {name}"

    luc_tich = name == "Luc Tich Chi Tinh Ha Sang The [C] - Cuong Tieu Ba La Duong.epub"
    backup_path = os.path.join(BACKUP_DIR, name)
    if os.path.exists(backup_path):
        if not force:
            return f"  skip (backup exists): {name}"
        src_path = backup_path
    else:
        src_path = path

    z = zipfile.ZipFile(src_path)
    try:
        opf_name = read_container(z)
        opf_root, base, manifest_el, spine_el, items, item_order, spine_ids = load_opf(z, opf_name)

        title = ""
        for el in opf_root.iter():
            if local(el.tag) == "title" and el.tag.startswith(DC_NS):
                title = el.text or ""
                break

        ncx_item = find_ncx_item(items, spine_el)
        nav_item = find_nav_item(items)
        toc_titles = {}
        if ncx_item is not None:
            load_ncx_titles(z, href_to_zipname(ncx_item.get("href"), base), toc_titles)
        if nav_item is not None:
            load_nav_titles(z, href_to_zipname(nav_item.get("href"), base), toc_titles)

        rewrites = {}  # zipname -> bytes
        new_files = []  # (zipname, bytes)
        manifest_adds = []  # (id, href, media_type)
        spine_expansion = {}  # orig id -> [id,...]
        final_toc = []  # (title, zipname)
        changed = False

        luc_titles = {}
        if luc_tich:
            front = etree.fromstring(z.read("index_split_000.html"))
            for link in front.xpath("//*[local-name()='a' and @href]"):
                label = el_text(link).strip()
                match = re.match(r"Chương\s+(\d+)\s*:", label)
                if match:
                    luc_titles[int(match.group(1))] = label

        # Phase A: parse + merge per item, in spine order.
        proc = []
        for sid in spine_ids:
            item = items.get(sid)
            if item is None:
                continue
            href = item.get("href") or ""
            media = item.get("media-type") or ""
            zipname = href_to_zipname(href, base)
            if media != "application/xhtml+xml" and not zipname.endswith((".xhtml", ".html", ".htm")):
                continue
            if zipname not in toc_titles and not luc_tich:
                # No TOC entry -> reader never listed this item; leave as-is.
                proc.append({
                    "sid": sid,
                    "zipname": zipname,
                    "media": media,
                    "info": None,
                    "fallback": None,
                    "chapters": None,
                })
                continue

            fallback_title = toc_titles.get(zipname, "")
            raw = z.read(zipname)
            info = None
            try:
                info = split_item(raw, fallback_title, luc_tich)
            except etree.XMLSyntaxError as e:
                print(f"    [warn] unparseable item {zipname}: {e}", file=sys.stderr)
            except ValueError as e:
                print(f"    [warn] item {zipname}: {e}", file=sys.stderr)
            proc.append({
                "sid": sid,
                "zipname": zipname,
                "media": media,
                "info": info,
                "fallback": fallback_title,
                "chapters": info["chapters"] if info else None,
            })

        # Phase B: a leading preface of item k (pure continuation text, no
        # glued heading, no metadata) is the tail of item k-1's last chapter.
        for k in range(1, len(proc)):
            cur, prev = proc[k], proc[k - 1]
            if not cur.get("info"):
                continue
            if prev.get("info") and not prev.get("chapters"):
                title = chapter_title_from(prev["info"]["units"]) or prev["fallback"]
                prev["chapters"] = [{"title": title, "units": prev["info"]["units"]}]
            if not prev.get("chapters"):
                continue
            s0 = cur["info"]["starts0"]
            if s0 <= 0 or s0 >= len(cur["info"]["units"]):
                continue
            pref = cur["info"]["units"][:s0]
            pref_text = "".join(u.text() for u in pref)
            if len(pref_text.strip()) > PREFACE_MAX_CHARS:
                continue
            if GLUED_RE.search(pref_text) or METADATA_RE.search(pref_text):
                continue
            if re.match(r"^\s*Q\d+\s*[-–]?\s*$", pref_text):
                continue
            prev["chapters"][-1]["units"].extend(pref)
            rem = cur["info"]["units"][s0:]
            new_ch = merge_chapters(rem, cur["fallback"], luc_tich)
            if new_ch:
                cur["chapters"] = new_ch
            else:
                title = chapter_title_from(rem) or cur["fallback"]
                cur["chapters"] = [{"title": title, "units": rem}]

        # Move trailing heading-only chapter of item k-1 to the start of item k
        # when item k starts with continuation text.
        for k in range(1, len(proc)):
            cur, prev = proc[k], proc[k - 1]
            if not prev.get("chapters"):
                continue
            last_ch = prev["chapters"][-1]
            last_text = "".join(u.text() for u in last_ch["units"]).strip()
            if len(last_text) < MIN_SEGMENT_CHARS and HEADING_START_RE.match(last_text):
                if not cur.get("info"):
                    try:
                        cur["info"] = split_item(z.read(cur["zipname"]), cur.get("fallback") or "", luc_tich)
                    except Exception:
                        pass
                if not cur.get("info"):
                    continue
                first_units = cur["chapters"][0]["units"] if cur.get("chapters") else cur["info"]["units"]
                if not first_units:
                    continue
                first_text = first_units[0].text()
                if not HEADING_START_RE.match(first_text):
                    if not cur.get("chapters"):
                        cur["chapters"] = [{
                            "title": last_ch["title"],
                            "units": list(last_ch["units"]) + list(cur["info"]["units"]),
                        }]
                    else:
                        cur["chapters"][0]["units"] = list(last_ch["units"]) + cur["chapters"][0]["units"]
                        cur["chapters"][0]["title"] = last_ch["title"]
                    prev["chapters"].pop()
                    if not prev["chapters"]:
                        prev["chapters"] = None

        # Drop exact consecutive duplicate heading lines across item boundaries.
        for it in proc:
            if it.get("info") and not it.get("chapters"):
                title = chapter_title_from(it["info"]["units"]) or it["fallback"]
                it["chapters"] = [{"title": title, "units": it["info"]["units"]}]

        for k in range(1, len(proc)):
            cur, prev = proc[k], proc[k - 1]
            if not cur.get("chapters") or not prev.get("chapters"):
                continue
            first_ch = cur["chapters"][0]
            while prev["chapters"]:
                last_ch = prev["chapters"][-1]
                last_text = "".join(u.text() for u in last_ch["units"]).strip()
                if (
                    last_ch.get("title")
                    and first_ch.get("title")
                    and norm_title(last_ch["title"]) == norm_title(first_ch["title"])
                    and norm_title(last_text) == norm_title(last_ch["title"])
                ):
                    prev["chapters"].pop()
                else:
                    break
            if not prev["chapters"]:
                prev["chapters"] = None

        # Phase C: build rewrites / new files.
        for it in proc:
            if not it["chapters"]:
                if it["fallback"]:
                    final_toc.append((it["fallback"], it["zipname"]))
                continue
            sid = it["sid"]
            zipname = it["zipname"]
            media = it["media"]
            info = it["info"]
            stem, ext = posixpath.splitext(zipname)
            dirn = posixpath.dirname(zipname)
            ids = [sid]
            for k, ch in enumerate(it["chapters"]):
                pieces = [("unit", u) for u in ch["units"]]
                if k == 0:
                    ch_zip = zipname
                    rewrites[zipname] = serialize_doc(info["root"], pieces)
                else:
                    ch_zip = posixpath.join(dirn, f"{posixpath.basename(stem)}_c{k}{ext}")
                    new_files.append((ch_zip, serialize_doc(
                        info["root"], pieces
                    )))
                    nid = f"{sid}-c{k}"
                    manifest_adds.append((nid, posixpath.relpath(ch_zip, base) if base else ch_zip, media))
                    ids.append(nid)
                if not ch.get("front"):
                    match = re.match(r"Chương\s+(\d+)", ch["title"]) if luc_tich else None
                    label = luc_titles.get(int(match.group(1)), ch["title"]) if match else ch["title"]
                    final_toc.append((label, ch_zip))
            spine_expansion[sid] = ids
            changed = True

        if not changed:
            return f"  untouched (no merge found): {name}"

        # Validate every rewritten file parses as XML.
        for zipname, data in list(rewrites.items()) + list(new_files):
            etree.fromstring(data)

        book_title = title or os.path.splitext(name)[0]

        def rel_to(zn, anchor_zip):
            """zip-relative -> path relative to the anchor file's directory."""
            anchor_dir = posixpath.dirname(anchor_zip)
            if not anchor_dir:
                return zn
            return posixpath.relpath(zn, anchor_dir)

        if ncx_item is not None:
            ncx_zip = href_to_zipname(ncx_item.get("href"), base)
            rewrites[ncx_zip] = build_ncx(
                book_title, [(t, rel_to(zn, ncx_zip)) for t, zn in final_toc]
            )
        else:
            ncx_zip = posixpath.join(opf_dir_of(opf_name), "toc.ncx")
            new_files.append((ncx_zip, build_ncx(
                book_title, [(t, rel_to(zn, ncx_zip)) for t, zn in final_toc]
            )))
            ncx_id = "ncx-split"
            manifest_adds.append((ncx_id, "toc.ncx", "application/x-dtbncx+xml"))
            spine_el.set("toc", ncx_id)
        if nav_item is not None:
            nav_zip = href_to_zipname(nav_item.get("href"), base)
            nav_toc = [(t, rel_to(zn, nav_zip)) for t, zn in final_toc]
            try:
                nav_doc = etree.fromstring(z.read(nav_zip))
                ol = nav_doc.find(".//{*}ol")
                if ol is not None:
                    ol.clear()
                    for title, href in nav_toc:
                        li = etree.SubElement(ol, XH + "li")
                        a = etree.SubElement(li, XH + "a")
                        a.set("href", href)
                        a.text = title
                    etree.indent(nav_doc, space="  ")
                    rewrites[nav_zip] = etree.tostring(
                        nav_doc, xml_declaration=True, encoding="UTF-8"
                    )
                else:
                    rewrites[nav_zip] = build_nav(nav_toc)
            except Exception:
                rewrites[nav_zip] = build_nav(nav_toc)

        # Manifest: add new items.
        for nid, nhref, nmedia in manifest_adds:
            it = etree.SubElement(manifest_el, OPF_NS + "item")
            it.set("id", nid)
            it.set("href", nhref)
            it.set("media-type", nmedia)

        # Spine: expand merged items.
        idx = 0
        for child in list(spine_el):
            if local(child.tag) != "itemref":
                continue
            idref = child.get("idref")
            expansion = spine_expansion.get(idref)
            if expansion:
                pos = list(spine_el).index(child)
                spine_el.remove(child)
                for j, nid in enumerate(expansion):
                    ir = etree.Element(OPF_NS + "itemref")
                    ir.set("idref", nid)
                    ir.set("linear", child.get("linear") or "yes")
                    spine_el.insert(pos + j, ir)
            idx += 1

        opf_bytes = etree.tostring(
            opf_root, xml_declaration=True, encoding="UTF-8", pretty_print=True
        )
        rewrites[opf_name] = opf_bytes

        total = len(final_toc)
        if dry_run:
            return f"  [dry-run] {name}: {total} chapters after split"
        return name, total, rewrites, new_files
    finally:
        z.close()


def write_book(path, rewrites, new_files):
    name = os.path.basename(path)
    backup_path = os.path.join(BACKUP_DIR, name)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)

    zin = zipfile.ZipFile(backup_path)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            data = rewrites.get(info.filename)
            if data is None:
                data = zin.read(info.filename)
            comp = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = comp
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
        for zipname, data in new_files:
            zi = zipfile.ZipInfo(zipname, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)
    zin.close()
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-split from backup even if already processed")
    ap.add_argument("--only", default=None, help="substring filter on file name")
    args = ap.parse_args()

    files = sorted(
        f for f in os.listdir(EPUB_DIR)
        if f.endswith(".epub") and (args.only is None or args.only in f)
    )
    print(f"{len(files)} EPUB(s) to inspect")
    for f in files:
        result = process_book(os.path.join(EPUB_DIR, f), dry_run=args.dry_run, force=args.force)
        if result is None:
            continue
        if isinstance(result, str):
            print(result)
        else:
            name, total, rewrites, new_files = result
            print(f"  {name}: {total} chapters after split ({len(new_files)} new files)")
            if not args.dry_run:
                write_book(os.path.join(EPUB_DIR, name), rewrites, new_files)
    print("Done.")


if __name__ == "__main__":
    main()
