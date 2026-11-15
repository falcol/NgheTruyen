"""Verify split epubs preserve content: book-level text diff + structural checks."""
import glob
import hashlib
import os
import posixpath
import sys

from lxml import etree

SPEC = os.path.join(os.path.dirname(__file__), "split-merged-epubs.py")


def load_splitter():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp", SPEC)
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    return sp


sp = load_splitter()


def xhtml_items(z, opf_name, base):
    """Spine-ordered list of (zipname, text) for xhtml spine items."""
    opf = etree.fromstring(z.read(opf_name))
    mani = {i.get("id"): i.get("href") for i in opf.findall(".//{*}manifest/{*}item")}
    spine = [mani[r.get("idref")] for r in opf.findall(".//{*}spine/{*}itemref")]
    out = []
    for href in spine:
        zn = sp.href_to_zipname(href, base)
        if not zn.endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            doc = etree.HTML(z.read(zn))
        except Exception:
            out.append((zn, ""))
            continue
        body = doc.find("body")
        out.append((zn, "".join(body.itertext()) if body is not None else ""))
    return out


def stream_lines(texts):
    lines = []
    for t in texts:
        lines.extend(ln.strip() for ln in t.splitlines() if ln.strip())
    return lines


def hashes(lines):
    return [hashlib.md5(ln.encode()).digest()[:8] for ln in lines]


def diff_summary(orig_lines, new_lines, label):
    """Early-exit diff: match prefix/suffix, SequenceMatcher on the window only."""
    ho, hn = hashes(orig_lines), hashes(new_lines)
    if ho == hn:
        return {"label": label, "equal": True}
    # find first / last mismatch
    lo = min(len(ho), len(hn))
    i = 0
    while i < lo and ho[i] == hn[i]:
        i += 1
    j = 0
    while j < lo - i and ho[len(ho) - 1 - j] == hn[len(hn) - 1 - j]:
        j += 1
    w1o, w2o = i, len(ho) - j
    w1n, w2n = i, len(hn) - j
    win_o = orig_lines[w1o:w2o]
    win_n = new_lines[w1n:w2n]
    sm = __import__("difflib").SequenceMatcher(None, win_o, win_n, autojunk=False)
    deleted, inserted = [], []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            deleted.extend(win_o[a1:a2])
        if op in ("insert", "replace"):
            inserted.extend(win_n[b1:b2])
    return {
        "label": label,
        "equal": False,
        "window": (w1o, w2o, w1n, w2n),
        "orig_lines": len(orig_lines),
        "new_lines": len(new_lines),
        "deleted": len(deleted),
        "inserted": len(inserted),
        "del_samples": deleted[:6],
        "ins_samples": inserted[:6],
    }


def structural_checks(path):
    name = os.path.basename(path)
    z = zipfile.ZipFile(path)
    issues = []
    if z.testzip() is not None:
        issues.append("zip corrupt")
    opf_name = sp.read_container(z)
    opf_root, base, manifest_el, spine_el, items, item_order, spine_ids = sp.load_opf(z, opf_name)
    # strict-parse every xhtml manifest item
    for it in manifest_el:
        if local(it) != "item":
            continue
        media = it.get("media-type") or ""
        if media != "application/xhtml+xml":
            continue
        zn = sp.href_to_zipname(it.get("href"), base)
        try:
            etree.fromstring(z.read(zn))
        except Exception as e:
            issues.append(f"XML fail {zn}: {e}")
    # ncx / nav
    titled = {}
    ncx_item = sp.find_ncx_item(items, spine_el)
    nav_item = sp.find_nav_item(items)
    if ncx_item is not None:
        sp.load_ncx_titles(z, sp.href_to_zipname(ncx_item.get("href"), base), titled)
    if nav_item is not None:
        sp.load_nav_titles(z, sp.href_to_zipname(nav_item.get("href"), base), titled)
    for zn, title in titled.items():
        if not title.strip():
            issues.append(f"empty title for {zn}")
        if zn not in z.namelist():
            issues.append(f"ncx src missing: {zn}")
    # empty chapters
    empty = []
    for sid in spine_ids:
        it = items.get(sid)
        if it is None:
            continue
        zn = sp.href_to_zipname(it.get("href") or "", base)
        if posixpath.basename(zn) not in titled:
            continue
        try:
            doc = etree.HTML(z.read(zn))
        except Exception:
            continue
        t = "".join(doc.itertext()).strip()
        if len(t) < 50:
            empty.append((zn, len(t)))
    if empty:
        issues.append(f"tiny/empty chapters: {empty[:8]}")
    z.close()
    return name, titled, issues


def local(it):
    return it.tag.rsplit("}", 1)[-1]


import zipfile  # noqa: E402  (needed before use above)

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    books = sorted(glob.glob(os.path.join(sp.BACKUP_DIR, "*.epub")))
    for backup in books:
        name = os.path.basename(backup)
        if only and only not in name:
            continue
        new_path = os.path.join(sp.EPUB_DIR, name)
        if not os.path.exists(new_path):
            print(f"{name[:50]}: MISSING new epub")
            continue
        z1 = zipfile.ZipFile(backup)
        z2 = zipfile.ZipFile(new_path)
        opf1 = sp.read_container(z1)
        opf2 = sp.read_container(z2)
        base1 = sp.opf_dir_of(opf1)
        base2 = sp.opf_dir_of(opf2)
        t1 = [t for _, t in xhtml_items(z1, opf1, base1)]
        t2 = [t for _, t in xhtml_items(z2, opf2, base2)]
        res = diff_summary(stream_lines(t1), stream_lines(t2), name)
        z1.close()
        z2.close()
        cname, titled, issues = structural_checks(new_path)
        if res.get("equal"):
            print(f"{name[:52]:52s} TEXT-EQUAL titled={len(titled):5d} issues={issues or 'none'}")
        else:
            print(f"{name[:52]:52s} DIFF del={res['deleted']:5d} ins={res['inserted']:5d} "
                  f"(lines {res['orig_lines']}->{res['new_lines']}) titled={len(titled)} issues={issues or 'none'}")
            for s in res["del_samples"]:
                print(f"    DEL: {s[:100]!r}")
            for s in res["ins_samples"]:
                print(f"    INS: {s[:100]!r}")


if __name__ == "__main__":
    main()
