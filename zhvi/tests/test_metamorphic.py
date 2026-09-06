"""Metamorphic invariants (story 5.3, SPEC CAP-11).

Sau bien doi khong doi nghia (them auto khong dung, reorder, cat chuong,
resume, rollback, alias phon/gian), output SHA-256 phai giong nhau.
Fixture tu chua — khong goi network/model.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import zhvi.pipeline as pl
from zhvi.correction import rollback_revision
from zhvi.document import parse_document
from zhvi.pipeline import PipelineResult, TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.revision import AutoEntry, build_revision, publish_revision
from zhvi.state import State

# Hai chuong de cat lossless; khong chua 玄女 (auto khong dung).
SRC = "第一章\n\n凌天看着前方。\n\n第二章\n\n青龙从天而降。\n"
SRC_SIMP = "青龙从天而降。\n"
SRC_TRAD = "青龍从天而降。\n"


def _mini_dict_dir(tmp_path: Path, name: str = "mini-dicts") -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n青龙=Thanh Long\n看着=nhìn về phía\n前方=phía trước\n"
        "从天而降=rơi từ trời xuống\n第一章=Chương 1\n第二章=Chương 2\n",
        encoding="utf-8",
    )
    (d / "trad-simp.txt").write_text("龍龙", encoding="utf-8")
    return d


def _translate(project_dir: Path, src_file: Path, out_file: Path, dict_dir: Path,
               *, refresh: bool = False) -> PipelineResult:
    p = create_project(project_dir)
    return translate_project(
        p,
        TranslateRequest(
            source=src_file,
            output=out_file,
            dict_dir=str(dict_dir),
            refresh_revision=refresh,
        ),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _active_id(project) -> str | None:
    st = State(project.db_path)
    try:
        return st.active_revision_id("book", project.book_id)
    finally:
        st.close()


def _split_by_chapter(text: str) -> list[str]:
    """Cat source theo chapter_id — noi lai bang van ban goc."""
    doc = parse_document(text)
    ids = sorted({n.chapter_id for n in doc.nodes})
    return ["".join(n.raw_text for n in doc.nodes if n.chapter_id == cid) for cid in ids]


def test_metamorphic_unused_auto_entry_does_not_change_sha(tmp_path):
    """Them auto entry ma key KHONG co trong source — output SHA-256 khong doi."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    assert "玄女" not in SRC

    proj = tmp_path / "proj-unused"
    out = tmp_path / "unused.vi.txt"
    res1 = _translate(proj, src, out, dict_dir)
    assert res1.exit_code == 0
    sha1 = _sha(out)
    project = create_project(proj)
    r1 = _active_id(project)
    assert r1

    unused = AutoEntry(source="玄女", target="Huyền Nữ")
    r2 = publish_revision(
        dict_dir, project, [unused], expected_active=r1
    )
    assert r2.revision_id != r1
    rows = (project.revisions_dir / r2.revision_id / "entries.tsv").read_text(
        encoding="utf-8"
    )
    assert "玄女" in rows

    res2 = _translate(proj, src, out, dict_dir)
    assert res2.exit_code == 0
    assert _sha(out) == sha1


def test_metamorphic_reorder_dict_lines_same_sha(tmp_path):
    """Reorder dong file nen / danh sach auto — khong doi output SHA-256
    (layer hash canonical, test_revision.test_base_file_reorder_same_revision_id)."""
    lines = [
        "凌天=Lăng Thiên",
        "青龙=Thanh Long",
        "看着=nhìn về phía",
        "前方=phía trước",
        "从天而降=rơi từ trời xuống",
        "第一章=Chương 1",
        "第二章=Chương 2",
    ]
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")

    d1 = tmp_path / "d1"
    d1.mkdir()
    (d1 / "QualityOverrides.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    d2 = tmp_path / "d2"
    d2.mkdir()
    (d2 / "QualityOverrides.txt").write_text(
        "\n".join(reversed(lines)) + "\n", encoding="utf-8"
    )

    out_a = tmp_path / "a.vi.txt"
    out_b = tmp_path / "b.vi.txt"
    res_a = _translate(tmp_path / "proj-a", src, out_a, d1)
    res_b = _translate(tmp_path / "proj-b", src, out_b, d2)
    assert res_a.exit_code == 0 and res_b.exit_code == 0
    assert _sha(out_a) == _sha(out_b)

    p1 = create_project(tmp_path / "rev-a")
    p2 = create_project(tmp_path / "rev-b")
    assert build_revision(d1, p1, []).revision_id == build_revision(d2, p2, []).revision_id

    # Auto key KHONG trung QO (manual thang auto) — hash layer canonical.
    d_auto = tmp_path / "d-auto"
    d_auto.mkdir()
    (d_auto / "QualityOverrides.txt").write_text(
        "看着=nhìn về phía\n前方=phía trước\n从天而降=rơi từ trời xuống\n"
        "第一章=Chương 1\n第二章=Chương 2\n",
        encoding="utf-8",
    )
    autos = [
        AutoEntry(source="凌天", target="Lăng Thiên"),
        AutoEntry(source="青龙", target="Thanh Long"),
    ]
    pa = create_project(tmp_path / "proj-auto-a")
    pb = create_project(tmp_path / "proj-auto-b")
    ra = publish_revision(d_auto, pa, autos)
    rb = publish_revision(d_auto, pb, list(reversed(autos)))
    assert ra.revision_id == rb.revision_id
    out_c = tmp_path / "c.vi.txt"
    out_d = tmp_path / "d.vi.txt"
    res_c = translate_project(
        pa, TranslateRequest(source=src, output=out_c, dict_dir=str(d_auto))
    )
    res_d = translate_project(
        pb, TranslateRequest(source=src, output=out_d, dict_dir=str(d_auto))
    )
    assert res_c.exit_code == 0 and res_d.exit_code == 0
    assert _sha(out_c) == _sha(out_d)


def test_metamorphic_whole_book_equals_per_chapter(tmp_path):
    """Dich ca truyen mot lan == noi cac ban dich tung chuong (cat cung source)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    chapters = _split_by_chapter(SRC)
    assert len(chapters) >= 2
    assert "".join(chapters) == SRC

    out_whole = tmp_path / "whole.vi.txt"
    res_w = _translate(tmp_path / "proj-whole", src, out_whole, dict_dir)
    assert res_w.exit_code == 0
    whole = out_whole.read_text(encoding="utf-8")

    parts: list[str] = []
    for i, chap in enumerate(chapters):
        chap_src = tmp_path / f"ch{i}.txt"
        chap_src.write_text(chap, encoding="utf-8")
        chap_out = tmp_path / f"ch{i}.vi.txt"
        res = _translate(tmp_path / f"proj-ch{i}", chap_src, chap_out, dict_dir)
        assert res.exit_code == 0
        parts.append(chap_out.read_text(encoding="utf-8"))
    concat = "".join(parts)
    assert hashlib.sha256(concat.encode("utf-8")).hexdigest() == _sha(out_whole)
    assert concat == whole


def test_metamorphic_resume_equals_clean(tmp_path, monkeypatch):
    """Resume sau gian doan == clean run (cung helper test_baseline.test_resume_parity)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")

    out_clean = tmp_path / "clean.vi.txt"
    assert _translate(tmp_path / "proj-clean", src, out_clean, dict_dir).exit_code == 0

    real_vp_plan = pl.vp_plan
    calls = {"n": 0}

    def flaky_vp_plan(dic, text, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt
        return real_vp_plan(dic, text, **kw)

    monkeypatch.setattr(pl, "vp_plan", flaky_vp_plan)
    proj_i = tmp_path / "proj-interrupted"
    res_i = _translate(proj_i, src, tmp_path / "i.vi.txt", dict_dir)
    assert res_i.exit_code == 130
    assert res_i.report["paused"] is True
    assert res_i.report["blocks"] >= 1

    monkeypatch.setattr(pl, "vp_plan", real_vp_plan)
    out_i = tmp_path / "i.vi.txt"
    res_r = _translate(proj_i, src, out_i, dict_dir)
    assert res_r.exit_code == 0
    assert _sha(out_i) == _sha(out_clean)


def test_metamorphic_rollback_restores_output_sha(tmp_path):
    """Rollback + chay lai khoi phuc output SHA-256 (correction/publish rollback)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    proj_dir = tmp_path / "proj-rb"
    project = create_project(proj_dir)
    out1 = tmp_path / "v1.vi.txt"
    res1 = translate_project(
        project, TranslateRequest(source=src, output=out1, dict_dir=str(dict_dir))
    )
    assert res1.exit_code == 0
    sha1 = _sha(out1)
    r1 = _active_id(project)
    assert r1

    project.manual_glossary.write_text("凌天=Lăng Thiên Sửa\n", encoding="utf-8")
    out2 = tmp_path / "v2.vi.txt"
    res2 = translate_project(
        project,
        TranslateRequest(
            source=src, output=out2, dict_dir=str(dict_dir), refresh_revision=True
        ),
    )
    assert res2.exit_code == 0
    sha2 = _sha(out2)
    assert sha2 != sha1
    r2 = _active_id(project)
    assert r2 and r2 != r1

    rollback_revision(project, r1, expected_active=r2)
    assert _active_id(project) == r1

    # Output moi (chua ton tai) de tranh nhanh noop giu file cu.
    out3 = tmp_path / "v3.vi.txt"
    res3 = translate_project(
        project, TranslateRequest(source=src, output=out3, dict_dir=str(dict_dir))
    )
    assert res3.exit_code == 0
    assert _sha(out3) == sha1


def test_metamorphic_trad_simp_alias_same_entry(tmp_path):
    """Phon the / gian the alias chon cung entry (test_lattice trad/simp)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src_s = tmp_path / "simp.txt"
    src_t = tmp_path / "trad.txt"
    src_s.write_text(SRC_SIMP, encoding="utf-8")
    src_t.write_text(SRC_TRAD, encoding="utf-8")

    out_s = tmp_path / "simp.vi.txt"
    out_t = tmp_path / "trad.vi.txt"
    res_s = _translate(tmp_path / "proj-simp", src_s, out_s, dict_dir)
    res_t = _translate(tmp_path / "proj-trad", src_t, out_t, dict_dir)
    assert res_s.exit_code == 0 and res_t.exit_code == 0
    assert _sha(out_s) == _sha(out_t)
    assert out_s.read_text(encoding="utf-8") == out_t.read_text(encoding="utf-8")
    assert "Thanh Long" in out_s.read_text(encoding="utf-8")
