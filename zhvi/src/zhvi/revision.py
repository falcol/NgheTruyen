"""Revision bundle builder + canonical manifest (story 2.1, SPEC CAP-2, AD-15 buoc 1-7).

Doc base files (dict_dir) + auto entries (state store truyen vao) + manual
layers, validate format/duplicate/conflict, tao canonical manifest (hash tung
layer + loader/renderer version + precedence policy),
dictionary_revision_id = SHA-256(canonical manifest), materialize bundle
content-addressed: manifest.json / entries.tsv / patterns.jsonl / dictionary.bin.

Bundle duoc ghi vao dir tam roi atomic rename thanh revisions/<id>/ — crash
giua chang de lai dir tam (orphan, GC duoc o story 2.2), khong bao gio hong
dir <id> chinh thuc. dictionary.bin la pickle TU SINH content-addressed
(nhu cache loader): chi nap lai khi manifest hash khop — khong bao gio nap
file tu nguon khong tin cay. Fsync + DB CAS active pointer thuoc story 2.2.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import LOADER_VERSION, RENDERER_VERSION
from .project import Project
from .vietphrase.layers import Layer, default_policy
from .vietphrase.loader import (
    LOAD_ORDER,
    MANUAL_TRUST,
    TRAD_SIMP_FILE,
    TRUST_BY_FILE,
    Dictionary,
    TrieNode,
    _insert,
    load_dictionary,
    load_trad_simp,
    normalize_nfc,
    parse_dict_line,
    to_simplified,
)

REVISION_FORMAT = "zhvi-revision-1"
AUTO_TRUST = 30.0  # auto tren base, duoi manual (QO 25, Custom 100)
BUNDLE_FILES = ("manifest.json", "entries.tsv", "patterns.jsonl", "dictionary.bin")

# scope auto -> layer (AD-5: auto book > auto global)
AUTO_LAYER_BY_SCOPE = {"book": Layer.BOOK_AUTO, "global": Layer.AUTO_GLOBAL}


@dataclass(frozen=True)
class AutoEntry:
    """Entry auto da promote doc tu state store (book/global learner)."""

    source: str
    target: str
    scope: str = "book"  # "book" | "global"

    @property
    def layer(self) -> Layer:
        return AUTO_LAYER_BY_SCOPE[self.scope]


@dataclass(frozen=True)
class Conflict:
    """Hai auto entry cung scope (cung lop), cung key, khac target."""

    key: str
    layer: int
    scope: str
    targets: list[str]


class BuildError(RuntimeError):
    """Build revision fail: format invalid hoac auto conflict."""

    def __init__(self, message: str, conflicts: list[Conflict] | None = None) -> None:
        super().__init__(message)
        self.conflicts = conflicts or []


@dataclass(frozen=True)
class RevisionBundle:
    revision_id: str
    path: Path
    manifest: dict
    entry_count: int


def _parse_file_entries(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parsed = parse_dict_line(line)
        if parsed is not None:
            entries.append(parsed)
    return entries


def _layer_hash(entries: list[tuple[str, str]]) -> tuple[str, int]:
    """Hash canonical cua mot layer: sort (source, target) — reorder dong trong
    file / thu tu nap khong doi hash (CAP-11: reorder khong doi output)."""
    lines = sorted(f"{s}\x1f{t}" for s, t in entries)
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return digest, len(lines)


def _validate_auto(autos: list[AutoEntry]) -> None:
    """Buoc 4: validate format, duplicate, conflict. Cung scope + cung key +
    khac target -> BuildError kem conflict report (SPEC story 2.1)."""
    errors: list[str] = []
    for a in autos:
        if not a.source or not a.target:
            errors.append(f"auto entry rong source/target: {a.source!r}={a.target!r}")
        if "\t" in a.source or "\n" in a.source or "\t" in a.target or "\n" in a.target:
            errors.append(f"auto entry chua tab/newline: {a.source!r}")
    if errors:
        raise BuildError("auto entry format invalid: " + "; ".join(errors))

    by_key: dict[str, dict[str, None]] = {}
    for a in autos:
        by_key.setdefault(a.scope + "\x1f" + normalize_nfc(a.source), {})[a.target] = None
    conflicts = [
        Conflict(
            key=key.split("\x1f", 1)[1],
            layer=int(AUTO_LAYER_BY_SCOPE[key.split("\x1f", 1)[0]]),
            scope=key.split("\x1f", 1)[0],
            targets=sorted(targets),
        )
        for key, targets in by_key.items()
        if len(targets) > 1
    ]
    if conflicts:
        report = "; ".join(f"{c.key}: {' vs '.join(c.targets)}" for c in conflicts)
        raise BuildError(f"auto conflict cung scope/lop, khac target — {report}", conflicts)


def _trie_rows(root: TrieNode) -> list[tuple[str, tuple, str, str]]:
    """Duyet trie lay moi (source, target, precedence, policy) — sorted de
    entries.tsv va canonical rebuild deu deterministic."""
    rows: list[tuple[str, tuple, str, str]] = []
    stack: list[tuple[str, TrieNode]] = [("", root)]
    while stack:
        prefix, node = stack.pop()
        for target, prec, policy in node.entries:
            rows.append((prefix, target, prec, policy))
        for ch, child in sorted(node.children.items()):
            stack.append((prefix + ch, child))
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    return rows


def _scope_of(layer_int: int) -> str:
    if layer_int in (int(Layer.AUTO_GLOBAL),):
        return "global"
    if layer_int in (int(Layer.BOOK_AUTO), int(Layer.BOOK_MANUAL)):
        return "book"
    return "global"


def _rebuild_canonical(dic: Dictionary, revision_id: str) -> Dictionary:
    """Rebuild trie + patterns + trad_simp theo thu tu sorted — pickle bytes
    chi phu thuoc noi dung, khong phu thuoc thu tu dong file."""
    root = TrieNode()
    count = 0
    for source, target, prec, policy in _trie_rows(dic.root):
        _insert(root, source, target, prec, policy)
        count += 1
    patterns = {bucket: sorted(rules, key=lambda r: (r.key, r.target))
                for bucket, rules in sorted(dic.patterns.items())}
    return Dictionary(
        root=root,
        trad_simp=dict(sorted(dic.trad_simp.items())),
        entry_count=count,
        fingerprint=revision_id,  # bundle dictionary dinh danh boi revision, khong phai file bytes
        patterns=patterns,
    )


def build_revision(
    dict_dir: Path,
    project: Project,
    auto_entries: list[AutoEntry] | None = None,
    *,
    global_glossary: Path | None = None,
    patterns: bool = True,
) -> RevisionBundle:
    """Build revision bundle buoc 1-7 cua publish protocol (data-model.md).

    Buoc 8-10 (smoke + fsync + DB CAS active pointer) thuoc story 2.2.
    """
    # buoc 4 (validate) + dedupe auto trung lap truoc khi hash/insert
    autos = sorted(
        {AutoEntry(source=normalize_nfc(a.source), target=a.target, scope=a.scope)
         for a in (auto_entries or [])},
        key=lambda a: (a.scope, a.source, a.target),
    )
    _validate_auto(autos)

    layers: list[dict] = []

    def _add_layer(name: str, scope: str, entries: list[tuple[str, str]], layer: Layer | None = None) -> None:
        digest, count = _layer_hash(entries)
        record = {"name": name, "scope": scope, "sha256": digest, "entry_count": count}
        if layer is not None:
            record["layer"] = layer.name
        layers.append(record)

    # buoc 1: base files (layer gan per-entry boi loader — file record khong
    # claim layer de tranh mâu thuan voi entries trong trie)
    for name in LOAD_ORDER:
        path = dict_dir / name
        if path.is_file():
            _add_layer(name, "global", _parse_file_entries(path))
    trad_simp = load_trad_simp(dict_dir)
    if trad_simp:
        _add_layer(TRAD_SIMP_FILE, "global", sorted(trad_simp.items()))

    # buoc 2: auto entries theo scope (scope xac dinh layer — AD-5)
    auto_groups: dict[str, list[tuple[str, str]]] = {}
    for a in autos:
        auto_groups.setdefault(a.scope, []).append((a.source, a.target))
    for scope, entries in sorted(auto_groups.items()):
        _add_layer(f"auto:{scope}", scope, entries, layer=AUTO_LAYER_BY_SCOPE[scope])

    # buoc 3: manual layers
    if global_glossary is not None and global_glossary.is_file():
        _add_layer("manual:global", "global", _parse_file_entries(global_glossary), layer=Layer.SERIES_MANUAL)
    if project.manual_glossary.is_file():
        _add_layer("manual:book", "book", _parse_file_entries(project.manual_glossary), layer=Layer.BOOK_MANUAL)

    # buoc 5: canonical manifest
    manifest = {
        "format": REVISION_FORMAT,
        "layers": layers,
        "entry_count": sum(layer["entry_count"] for layer in layers),
        "loader_version": LOADER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "patterns_enabled": patterns,
        "precedence_policy": {
            "layer_order": [m.name for m in Layer],
            "tie_break": "longest_match,layer,literal_over_pattern,entry_id",
            "trust_by_file": TRUST_BY_FILE,
            "auto_trust": AUTO_TRUST,
            "manual_trust": MANUAL_TRUST,
        },
    }
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    # buoc 6: dictionary_revision_id = SHA-256(canonical manifest)
    revision_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    out = project.revisions_dir / revision_id

    # content-addressed: dir <id> day du -> reuse, khong ghi lai
    if out.is_dir() and all((out / n).is_file() for n in BUNDLE_FILES):
        return RevisionBundle(revision_id, out, manifest, entry_count=manifest["entry_count"])

    # buoc 7: materialize vao dir TAM roi atomic rename thanh <id>/
    dic = load_dictionary(
        dict_dir,
        manual_glossary=project.manual_glossary,
        global_glossary=global_glossary,
        patterns=patterns,
    )
    for i, a in enumerate(autos):
        prec = (int(a.layer), AUTO_TRUST, i)
        _insert(dic.root, a.source, a.target, prec, default_policy(a.layer))
        simp = to_simplified(a.source, dic.trad_simp)
        if simp != a.source:
            _insert(dic.root, simp, a.target, prec, default_policy(a.layer))
    dic = _rebuild_canonical(dic, revision_id)

    tmp = project.revisions_dir / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "manifest.json").write_bytes(canonical.encode("utf-8"))
    rows = sorted(
        f"{prec[0]}\t{_scope_of(prec[0])}\t{source}\t{target}\t{policy}"
        for source, target, prec, policy in _trie_rows(dic.root)
    )
    (tmp / "entries.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (tmp / "patterns.jsonl").write_text(_patterns_jsonl(dic), encoding="utf-8")
    # Pickle self-generated content-addressed — chi nap lai khi manifest hash khop.
    (tmp / "dictionary.bin").write_bytes(pickle.dumps(dic, protocol=pickle.HIGHEST_PROTOCOL))

    if out.exists():
        shutil.rmtree(out)  # bundle rac tu crash giua chang — thay the
    os.replace(tmp, out)
    return RevisionBundle(revision_id, out, manifest, entry_count=manifest["entry_count"])


def _patterns_jsonl(dic: Dictionary) -> str:
    lines = []
    for rules in dic.patterns.values():
        for rule in rules:
            lines.append(
                json.dumps(
                    {
                        "key": rule.key,
                        "target": rule.target,
                        "precedence": list(rule.precedence),
                        "policy": rule.policy,
                        "starts": list(rule.starts),
                        "slots": list(rule.slots),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    return "\n".join(sorted(lines)) + "\n"
