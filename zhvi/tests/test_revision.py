"""Tests cho revision bundle builder (story 2.1, SPEC CAP-2, AD-15 buoc 1-7).

Builder doc base files + auto entries + manual layers, validate, tao canonical
manifest (hash tung layer + loader/renderer version + precedence policy),
dictionary_revision_id = SHA-256(canonical manifest), materialize bundle
content-addressed: manifest.json / entries.tsv / patterns.jsonl / dictionary.bin.
"""
from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import pytest

from zhvi.project import create_project
from zhvi.revision import REVISION_FORMAT, AutoEntry, BuildError, build_revision
from zhvi.vietphrase.layers import Layer


def _mini_dict_dir(tmp_path: Path, name: str = "mini-dicts") -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n青龙=Thanh Long\n", encoding="utf-8"
    )
    (d / "Custom.txt").write_text("从天而降=rơi từ trời xuống\n", encoding="utf-8")
    (d / "LuatNhan.txt").write_text("小{n}=tiểu {1}\n", encoding="utf-8")
    (d / "trad-simp.txt").write_text("龍龙", encoding="utf-8")
    return d


def test_same_inputs_same_revision_id(tmp_path):
    """Cung tap input (auto entries dao thu tu) -> cung revision id (AD-9 determinism)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    autos = [
        AutoEntry(source="天煞", target="Thiên Sát"),
        AutoEntry(source="玄女", target="Huyền Nữ"),
    ]
    b1 = build_revision(dict_dir, project, autos)
    b2 = build_revision(dict_dir, project, list(reversed(autos)))
    assert b1.revision_id == b2.revision_id
    # id = SHA-256 cua canonical manifest trong bundle
    canonical = (b1.path / "manifest.json").read_bytes()
    assert b1.revision_id == hashlib.sha256(canonical).hexdigest()


def test_bundle_contents(tmp_path):
    """Bundle du 4 file; manifest du thanh phan; dictionary.bin nap duoc va
    auto entry match duoc."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    autos = [AutoEntry(source="天煞", target="Thiên Sát")]
    bundle = build_revision(dict_dir, project, autos)

    out = project.revisions_dir / bundle.revision_id
    assert out.is_dir()
    for name in ("manifest.json", "entries.tsv", "patterns.jsonl", "dictionary.bin"):
        assert (out / name).is_file(), f"thieu {name} trong bundle"

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == REVISION_FORMAT
    layer_names = [lyr["name"] for lyr in manifest["layers"]]
    assert "QualityOverrides.txt" in layer_names
    assert "auto:book" in layer_names
    assert manifest["loader_version"]
    assert manifest["renderer_version"]
    assert manifest["precedence_policy"]["layer_order"]  # Layer order có mặt
    for lyr in manifest["layers"]:
        assert len(lyr["sha256"]) == 64 and lyr["entry_count"] >= 0

    # entries.tsv: co entry base + auto, sorted, format layer/scope/source/target/policy
    rows = (out / "entries.tsv").read_text(encoding="utf-8").splitlines()
    assert any("\t天煞\tThiên Sát\t" in r for r in rows)
    assert rows == sorted(rows)

    # patterns.jsonl: luat nhan {n}
    pat_lines = (out / "patterns.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(pl)["key"] == "小{n}" for pl in pat_lines)

    # dictionary.bin: pickle Dictionary, auto entry co trong trie
    dic = pickle.loads((out / "dictionary.bin").read_bytes())
    node = dic.root
    for ch in "天煞":
        node = node.children[ch]
    assert any(t == "Thiên Sát" for t, _prec, _pol in node.entries)


def test_auto_conflict_same_key_different_target_fails(tmp_path):
    """2 auto entry cung scope/lop, cung key, khac target -> BuildError kem
    conflict report (SPEC story 2.1)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    autos = [
        AutoEntry(source="天煞", target="Thiên Sát"),
        AutoEntry(source="天煞", target="Sát Thiên"),
    ]
    with pytest.raises(BuildError) as exc:
        build_revision(dict_dir, project, autos)
    conflicts = exc.value.conflicts
    assert len(conflicts) == 1
    assert conflicts[0].key == "天煞"
    assert set(conflicts[0].targets) == {"Thiên Sát", "Sát Thiên"}
    # build fail truoc khi materialize — khong co bundle nao duoc tao
    assert not project.revisions_dir.exists() or not any(project.revisions_dir.iterdir())


def test_auto_conflict_different_scope_ok(tmp_path):
    """Khac scope (book vs global) cung key — khong phai conflict."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    autos = [
        AutoEntry(source="天煞", target="Thiên Sát", scope="book"),
        AutoEntry(source="天煞", target="Sát Thiên", scope="global"),
    ]
    bundle = build_revision(dict_dir, project, autos)
    assert bundle.revision_id


def test_auto_entry_format_invalid(tmp_path):
    """Auto entry target rong / chua tab -> BuildError format."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    with pytest.raises(BuildError):
        build_revision(dict_dir, project, [AutoEntry(source="天煞", target="")])
    with pytest.raises(BuildError):
        build_revision(dict_dir, project, [AutoEntry(source="天煞", target="a\tb")])


def test_manual_layer_in_manifest_and_tsv(tmp_path):
    """Book manual glossary la layer trong manifest + entries.tsv."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    project.manual_glossary.write_text("玄女=Huyền Nữ Book\n", encoding="utf-8")
    bundle = build_revision(dict_dir, project, [])
    manifest = json.loads((bundle.path / "manifest.json").read_text(encoding="utf-8"))
    assert "manual:book" in [lyr["name"] for lyr in manifest["layers"]]
    rows = (bundle.path / "entries.tsv").read_text(encoding="utf-8").splitlines()
    assert any("\t玄女\tHuyền Nữ Book\tPREFERRED" in r for r in rows)


def test_base_file_reorder_same_revision_id(tmp_path):
    """Reorder dong trong file nen khong doi layer hash -> cung id (CAP-11)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    b1 = build_revision(dict_dir, project, [])
    (dict_dir / "QualityOverrides.txt").write_text(
        "青龙=Thanh Long\n凌天=Lăng Thiên\n", encoding="utf-8"
    )  # dao 2 dong
    b2 = build_revision(dict_dir, project, [])
    assert b1.revision_id == b2.revision_id


# ---- review findings (story 2.1 code review) ----


def test_different_trad_simp_different_id(tmp_path):
    """trad-simp.txt anh huong trie (simp keys) — phai tham gia manifest hash:
    noi dung khac nhau phai ra id khac nhau (content-addressed)."""
    project = create_project(tmp_path / "proj")
    b1 = build_revision(_mini_dict_dir(tmp_path, "d1"), project, [])
    dict_dir2 = _mini_dict_dir(tmp_path, "d2")
    (dict_dir2 / "trad-simp.txt").write_text("龍聾", encoding="utf-8")
    b2 = build_revision(dict_dir2, project, [])
    assert b1.revision_id != b2.revision_id


def test_auto_book_beats_auto_global(tmp_path):
    """AD-5: auto book > auto global — layer phai khac nhau va BOOK_AUTO cao hon."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    autos = [
        AutoEntry(source="天煞", target="Thiên Sát", scope="book"),
        AutoEntry(source="天煞", target="Sát Thiên", scope="global"),
    ]
    bundle = build_revision(dict_dir, project, autos)
    dic = pickle.loads((bundle.path / "dictionary.bin").read_bytes())
    node = dic.root
    for ch in "天煞":
        node = node.children[ch]
    by_target = {t: prec for t, prec, _pol in node.entries}
    assert by_target["Thiên Sát"][0] > by_target["Sát Thiên"][0]


def test_auto_insert_keeps_base_precedence(tmp_path):
    """Auto entry cung target voi base entry phai KHONG downgrade base
    (AD-5: base layer cao hon auto)."""
    dict_dir = _mini_dict_dir(tmp_path)
    (dict_dir / "Names.txt").write_text("天煞=Thiên Sát\n", encoding="utf-8")
    project = create_project(tmp_path / "proj")
    autos = [AutoEntry(source="天煞", target="Thiên Sát")]
    bundle = build_revision(dict_dir, project, autos)
    dic = pickle.loads((bundle.path / "dictionary.bin").read_bytes())
    node = dic.root
    for ch in "天煞":
        node = node.children[ch]
    (target, prec, _pol) = node.entries[0]
    assert target == "Thiên Sát"
    assert prec[0] == int(Layer.BASE_MULTI)  # base giu nguyen, khong bi ha layer


def test_duplicate_auto_entries_deduped(tmp_path):
    """Auto entry trung lap (giu het cac truong) — dedupe, khong double-count."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    dup = AutoEntry(source="天煞", target="Thiên Sát")
    bundle = build_revision(dict_dir, project, [dup, dup])
    manifest = json.loads((bundle.path / "manifest.json").read_text(encoding="utf-8"))
    auto_layer = next(lyr for lyr in manifest["layers"] if lyr["name"] == "auto:book")
    assert auto_layer["entry_count"] == 1
    assert bundle.entry_count == manifest["entry_count"]


def test_manual_global_glossary_layer(tmp_path):
    """Global glossary (zhvi/glossary.manual.tsv) la layer manual:global."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    global_gloss = tmp_path / "glossary.global.tsv"
    global_gloss.write_text("玄女=Huyền Nữ Global\n", encoding="utf-8")
    bundle = build_revision(dict_dir, project, [], global_glossary=global_gloss)
    manifest = json.loads((bundle.path / "manifest.json").read_text(encoding="utf-8"))
    assert "manual:global" in [lyr["name"] for lyr in manifest["layers"]]
    rows = (bundle.path / "entries.tsv").read_text(encoding="utf-8").splitlines()
    assert any("\t玄女\tHuyền Nữ Global\tPREFERRED" in r for r in rows)


def test_partial_bundle_rebuilt(tmp_path):
    """Dir <id> ton tai nhung chi co manifest.json rac (crash giua chang) —
    build lai phai materialize du 4 file hop le."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    b1 = build_revision(dict_dir, project, [])
    out = project.revisions_dir / b1.revision_id
    # gia lap crash: chi con manifest.json
    for name in ("entries.tsv", "patterns.jsonl", "dictionary.bin"):
        (out / name).unlink()
    b2 = build_revision(dict_dir, project, [])
    assert b2.revision_id == b1.revision_id
    for name in ("manifest.json", "entries.tsv", "patterns.jsonl", "dictionary.bin"):
        assert (out / name).is_file()
    dic = pickle.loads((out / "dictionary.bin").read_bytes())
    assert dic.entry_count > 0


def test_dictionary_bin_canonical_bytes(tmp_path):
    """Cung id -> dictionary.bin bytes giong het (canonical rebuild truoc pickle)."""
    project = create_project(tmp_path / "proj")
    b1 = build_revision(_mini_dict_dir(tmp_path, "d1"), project, [])
    dict_dir2 = _mini_dict_dir(tmp_path, "d2")
    (dict_dir2 / "QualityOverrides.txt").write_text(
        "青龙=Thanh Long\n凌天=Lăng Thiên\n", encoding="utf-8"
    )  # dao dong — cung layer hash, cung id
    b2 = build_revision(dict_dir2, project, [])
    assert b1.revision_id == b2.revision_id
    bin1 = (b1.path / "dictionary.bin").read_bytes()
    bin2 = (b2.path / "dictionary.bin").read_bytes()
    assert bin1 == bin2
