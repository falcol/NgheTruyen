"""Doc tu dien nen + manual, nap vao trie giu MOI candidate (khong chi best).

Nguon file cung layout voi crawler/vietphrase/dicts. Khac biet voi engine cu:
moi nut ket thuc luu danh sach entry (nhieu target cho cung source) de lattice
co tinh margin; greedy cu chi giu 1.
"""
from __future__ import annotations

import hashlib
import pickle
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .layers import Layer, default_policy, make_entry
from .patterns import SLOT_RE, PatternRule, build_pattern_index, compile_rule

TRUST_BY_FILE = {
    "ChinesePhienAmWords.txt": 5.0,
    "ChinesePhienAmWords_2.txt": 5.0,
    "VietPhrase_1.txt": 10.0,
    "VietPhrase_2.txt": 10.0,
    "VietPhrase_3.txt": 10.0,
    "VietPhrase_4.txt": 10.0,
    "LuatNhan.txt": 15.0,
    "Names.txt": 20.0,
    "Names_2.txt": 20.0,
    "QualityOverrides.txt": 25.0,
    "ContextPatterns.txt": 25.0,
    "Custom.txt": 100.0,
}
LOAD_ORDER = tuple(TRUST_BY_FILE)
TRAD_SIMP_FILE = "trad-simp.txt"
MANUAL_TRUST = 1000.0  # book manual thang tuyet doi so voi nen


class TrieNode:
    __slots__ = ("children", "entries")

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.entries: list[tuple[str, tuple, str]] = []  # (target, precedence, policy)


def _first_meaning(raw: str) -> str:
    raw = re.sub(r"\t\d+\s*$", "", raw).strip()  # LuatNhan trailing priority
    cut = raw.find("//")
    if cut != -1:
        raw = raw[:cut]
    cuts = [i for i in (raw.find("/"), raw.find("|")) if i != -1]
    if cuts:
        raw = raw[: min(cuts)]
    raw = raw.rstrip("*").strip()
    return raw


def parse_dict_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line[0] in "#;" or line.startswith("//"):
        return None
    eq = line.find("=")
    if eq < 1:
        return None
    zh = line[:eq].strip()
    vi = _first_meaning(line[eq + 1 :])
    if not zh or not vi or "{0}" in zh:
        return None
    return zh, vi


def load_trad_simp(dict_dir: Path) -> dict[str, str]:
    path = dict_dir / TRAD_SIMP_FILE
    if not path.is_file():
        return {}
    raw = "".join(path.read_text(encoding="utf-8-sig").split())
    chars = list(raw)
    if len(chars) % 2:
        chars = chars[:-1]
    return {chars[i]: chars[i + 1] for i in range(0, len(chars), 2)}


def to_simplified(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    return "".join(ch if ch == "么" else mapping.get(ch, ch) for ch in text)


def _insert(root: TrieNode, key: str, target: str, precedence: tuple, policy: str) -> None:
    node = root
    for ch in key:
        node = node.children.setdefault(ch, TrieNode())
    for i, (t, p, _pol) in enumerate(node.entries):
        if t == target:
            if precedence > p:  # cung target: giu precedence cao hon (AD-5)
                node.entries[i] = (target, precedence, policy)
            return
    node.entries.append((target, precedence, policy))


@dataclass
class Dictionary:
    root: TrieNode
    trad_simp: dict[str, str]
    entry_count: int
    fingerprint: str  # SHA-256 cua toan bo nguon dict da nap
    patterns: dict = field(default_factory=dict)  # bucket -> list[PatternRule] (muc 11.1 luat nhan)


def iter_global_glossary_files(global_glossary: Path | None) -> list[Path]:
    """File global chinh + drop-in `{parent}/glossary.d/*.tsv` (sorted).

    Chi nap glossary.d khi da co file global (tranh load ~/.config luc test
    goi load_dictionary ma khong truyen global_glossary).
    """
    files: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        if not path.is_file():
            return
        try:
            key = path.resolve()
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        files.append(path)

    if global_glossary is None:
        return files
    _add(global_glossary)
    dropin = global_glossary.parent / "glossary.d"
    if dropin.is_dir():
        for path in sorted(dropin.glob("*.tsv")):
            _add(path)
    return files


def dict_files_fingerprint(
    dict_dir: Path,
    manual_glossary: Path | None,
    global_glossary: Path | None = None,
    patterns: bool = True,
) -> str:
    h = hashlib.sha256()
    h.update(b"fmt:patterns-v1\x1f" if patterns else b"fmt:literal-only\x1f")  # cache cu tu invalid
    for name in LOAD_ORDER:
        path = dict_dir / name
        if path.is_file():
            h.update(name.encode())
            h.update(f"{path.stat().st_size:x}".encode())
            # hash day du noi dung (file nen ~36MB — doc stream)
            with path.open("rb") as f:
                while chunk := f.read(1 << 20):
                    h.update(chunk)
    for gpath in iter_global_glossary_files(global_glossary):
        h.update(b"global:")
        h.update(gpath.name.encode())
        h.update(gpath.read_bytes())
    if manual_glossary is not None and manual_glossary.is_file():
        h.update(b"manual:")
        h.update(manual_glossary.read_bytes())
    return h.hexdigest()


def load_dictionary(
    dict_dir: Path,
    *,
    manual_glossary: Path | None = None,
    global_glossary: Path | None = None,
    cache_path: Path | None = None,
    patterns: bool = True,
) -> Dictionary:
    """Nap toan bo layer vao trie. Neu cache_path hop le (fingerprint khop) -> pickle.

    Pickle chi dung cho cache tu sinh trong .zhvi/cache/ cua chinh may (self-generated,
    khong bao gio nap file tu nguon khong tin cay); fingerprint kiem tra tinh truc tiep.
    patterns=False: bo qua luat nhan {s}/{n} (chi dung trie literal).

    [Note] Story 2.3: runtime dich da nap qua bundle revision
    (revision.load_revision_dictionary) — caller runtime duy nen con truyen
    cache_path la doctor. Confirm giu hay xoa nhanh pkl cache nay?
    """
    fingerprint = dict_files_fingerprint(dict_dir, manual_glossary, global_glossary, patterns)
    if cache_path is not None and cache_path.is_file():
        try:
            with cache_path.open("rb") as f:
                meta, dic = pickle.load(f)
            if meta == fingerprint:
                return dic
        except Exception:  # noqa: BLE001 — cache hong -> build lai
            cache_path.unlink(missing_ok=True)

    trad_simp = load_trad_simp(dict_dir)
    root = TrieNode()
    pattern_rules: list[PatternRule] = []
    count = 0
    load_index = 0
    for name in LOAD_ORDER:
        path = dict_dir / name
        if not path.is_file():
            continue
        trust = TRUST_BY_FILE[name]
        # nhu engine cu: chi Custom.txt duoc nap ca key simplified (simp_keys);
        # file nen giu key nguyen ban — input da duoc simplify truoc khi match.
        simp_keys = name == "Custom.txt"
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            parsed = parse_dict_line(line)
            if parsed is None:
                continue
            zh, vi = parsed
            load_index += 1
            layer = Layer.BASE_SINGLE if len(zh) == 1 else Layer.BASE_MULTI
            if name.startswith("Names") and len(zh) == 1:
                continue  # Names chi co da tu ( nhu engine cu)
            if name in ("QualityOverrides.txt", "ContextPatterns.txt", "Custom.txt"):
                layer = Layer.GLOBAL_MANUAL
            prec = (int(layer), trust, load_index)
            if SLOT_RE.search(zh):
                # luat nhan {s}/{n}: compile thanh pattern rule (khong nap trie
                # literal — key chua '{' khong bao gio khop van ban that)
                if not patterns:
                    continue
                rule = compile_rule(to_simplified(zh, trad_simp), vi, prec, _policy_for(layer))
                if rule is not None:
                    pattern_rules.append(rule)
                    count += 1
                continue
            _insert(root, zh, vi, prec, _policy_for(layer))
            if simp_keys:
                simp = to_simplified(zh, trad_simp)
                if simp != zh:
                    _insert(root, simp, vi, prec, _policy_for(layer))
            count += 1
    for gpath in iter_global_glossary_files(global_glossary):
        # term chuan toan cuc (Tieu Ban + glossary.d/*.tsv) — SERIES_MANUAL,
        # thang dict nen nhung BOOK_MANUAL cua truyen van override duoc.
        for line in gpath.read_text(encoding="utf-8-sig").splitlines():
            parsed = parse_dict_line(line)
            if parsed is None:
                continue
            zh, vi = parsed
            load_index += 1
            prec = (int(Layer.SERIES_MANUAL), MANUAL_TRUST, load_index)
            _insert(root, zh, vi, prec, "PREFERRED")
            simp = to_simplified(zh, trad_simp)
            if simp != zh:
                _insert(root, simp, vi, prec, "PREFERRED")
            count += 1
    if manual_glossary is not None and manual_glossary.is_file():
        for line in manual_glossary.read_text(encoding="utf-8-sig").splitlines():
            parsed = parse_dict_line(line)
            if parsed is None:
                continue
            zh, vi = parsed
            load_index += 1
            prec = (int(Layer.BOOK_MANUAL), MANUAL_TRUST, load_index)
            _insert(root, zh, vi, prec, "PREFERRED")
            simp = to_simplified(zh, trad_simp)
            if simp != zh:
                _insert(root, simp, vi, prec, "PREFERRED")
            count += 1

    dic = Dictionary(
        root=root,
        trad_simp=trad_simp,
        entry_count=count,
        fingerprint=fingerprint,
        patterns=build_pattern_index(pattern_rules),
    )
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump((fingerprint, dic), f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(cache_path)
    return dic


def _policy_for(layer: Layer) -> str:
    return default_policy(layer)


def normalize_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)
