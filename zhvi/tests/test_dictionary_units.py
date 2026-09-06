"""Dictionary unit tests (story 5.3, SPEC CAP-11).

Sau nhom: parse dong, auto khong duplicate/conflict, precedence, alias
phon/gian, pattern khong nuot literal dai hon, deterministic.
Fixture tu chua — khong goi network/model.
"""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import pytest

from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.revision import AutoEntry, BuildError, build_revision
from zhvi.vietphrase.lattice import vp_plan
from zhvi.vietphrase.layers import Layer
from zhvi.vietphrase.loader import load_dictionary, load_trad_simp, parse_dict_line, to_simplified

SRC = "第一章\n\n凌天看着前方。\n\n青龙从天而降。\n"


def _mini_dict_dir(tmp_path: Path, name: str = "mini-dicts") -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n青龙=Thanh Long\n看着=nhìn về phía\n前方=phía trước\n"
        "从天而降=rơi từ trời xuống\n第一章=Chương 1\n",
        encoding="utf-8",
    )
    return d


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parse_dict_line_valid_and_skip_junk():
    """Nhom 1: parse moi dong — hop le giu, junk/comment/{0} bo qua."""
    assert parse_dict_line("凌天=Lăng Thiên") == ("凌天", "Lăng Thiên")
    assert parse_dict_line("  青龙 = Thanh Long  ") == ("青龙", "Thanh Long")
    assert parse_dict_line("a=b/c") == ("a", "b")
    assert parse_dict_line("a=b|c") == ("a", "b")
    assert parse_dict_line("a=b*") == ("a", "b")
    assert parse_dict_line("a=b//ghi chu") == ("a", "b")
    assert parse_dict_line("a=b\t3") == ("a", "b")
    assert parse_dict_line("小{n}=tiểu {1}") == ("小{n}", "tiểu {1}")

    assert parse_dict_line("") is None
    assert parse_dict_line("   ") is None
    assert parse_dict_line("# comment") is None
    assert parse_dict_line("; comment") is None
    assert parse_dict_line("// comment") is None
    assert parse_dict_line("=thieu-zh") is None
    assert parse_dict_line("khong-dau-bang") is None
    assert parse_dict_line("foo=") is None
    assert parse_dict_line("在{0}之上=trên {0}") is None


def test_auto_no_duplicate_conflict(tmp_path):
    """Nhom 2: auto cung scope+key khac target -> BuildError; trung target
    duoc dedupe; khac scope khong phai conflict."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    with pytest.raises(BuildError) as exc:
        build_revision(
            dict_dir,
            project,
            [
                AutoEntry(source="天煞", target="Thiên Sát"),
                AutoEntry(source="天煞", target="Sát Thiên"),
            ],
        )
    assert len(exc.value.conflicts) == 1
    assert exc.value.conflicts[0].key == "天煞"
    assert set(exc.value.conflicts[0].targets) == {"Thiên Sát", "Sát Thiên"}

    dup = AutoEntry(source="天煞", target="Thiên Sát")
    bundle = build_revision(dict_dir, create_project(tmp_path / "proj-dup"), [dup, dup])
    auto_layer = next(
        lyr for lyr in bundle.manifest["layers"] if lyr["name"] == "auto:book"
    )
    assert auto_layer["entry_count"] == 1

    mixed = build_revision(
        dict_dir,
        create_project(tmp_path / "proj-scope"),
        [
            AutoEntry(source="天煞", target="Thiên Sát", scope="book"),
            AutoEntry(source="天煞", target="Sát Thiên", scope="global"),
        ],
    )
    assert mixed.revision_id


def test_precedence_manual_over_auto_over_base(tmp_path):
    """Nhom 3: Layer enum manual > auto > base (BASE_SINGLE); BOOK_MANUAL thang
    ca BOOK_AUTO va BASE_MULTI khi cung key."""
    assert Layer.BOOK_MANUAL > Layer.BOOK_AUTO > Layer.BASE_SINGLE
    assert Layer.BOOK_MANUAL > Layer.BASE_MULTI
    assert Layer.BOOK_AUTO > Layer.AUTO_GLOBAL
    # fill-only: phrase nen (BASE_MULTI) thang BOOK_AUTO
    assert Layer.BASE_MULTI > Layer.BOOK_AUTO

    d = tmp_path / "prec"
    d.mkdir()
    (d / "ChinesePhienAmWords.txt").write_text("龙=long-hv\n", encoding="utf-8")
    (d / "Names.txt").write_text("青龙=Thanh Long Base\n", encoding="utf-8")
    project = create_project(tmp_path / "proj-prec")
    project.manual_glossary.write_text("青龙=Thanh Long Manual\n", encoding="utf-8")
    bundle = build_revision(
        d,
        project,
        [
            AutoEntry(source="龙", target="long-auto"),
            AutoEntry(source="青龙", target="Thanh Long Auto"),
        ],
    )
    dic = pickle.loads((bundle.path / "dictionary.bin").read_bytes())
    assert "Manual" in vp_plan(dic, "青龙").text
    assert "Auto" not in vp_plan(dic, "青龙").text
    assert "Base" not in vp_plan(dic, "青龙").text
    # single-char: auto (BOOK_AUTO) thang Han-Viet (BASE_SINGLE)
    assert "auto" in vp_plan(dic, "龙").text


def test_alias_trad_simp(tmp_path):
    """Nhom 4: alias phon/gian — mapping + input simplify chon cung entry."""
    d = tmp_path / "alias"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text("青龙=Thanh Long\n龙=Long\n", encoding="utf-8")
    (d / "trad-simp.txt").write_text("龍龙", encoding="utf-8")
    mapping = load_trad_simp(d)
    assert mapping.get("龍") == "龙"
    assert to_simplified("青龍", mapping) == "青龙"
    assert to_simplified("么", {"么": "x"}) == "么"  # ky tu dac biet khong map

    dic = load_dictionary(d)
    assert vp_plan(dic, "龍").text == vp_plan(dic, "龙").text
    assert vp_plan(dic, "青龍").text == vp_plan(dic, "青龙").text
    assert "Thanh Long" in vp_plan(dic, "青龍").text

    # Custom.txt nap them key simplified tu key phon the.
    d2 = tmp_path / "alias-custom"
    d2.mkdir()
    (d2 / "Custom.txt").write_text("青龍=Thanh Long Custom\n", encoding="utf-8")
    (d2 / "trad-simp.txt").write_text("龍龙", encoding="utf-8")
    dic2 = load_dictionary(d2)
    assert "Custom" in vp_plan(dic2, "青龙").text
    assert vp_plan(dic2, "青龍").text == vp_plan(dic2, "青龙").text


def test_pattern_does_not_swallow_longer_literal(tmp_path):
    """Nhom 5: luat nhan {n} khong duoc nuot literal dai hon (longest match)."""
    d = tmp_path / "pat"
    d.mkdir()
    (d / "VietPhrase_1.txt").write_text(
        "小天才=Tiểu Thiên Tài Literal\n", encoding="utf-8"
    )
    (d / "LuatNhan.txt").write_text("小{n}=tiểu {1}\n", encoding="utf-8")
    (d / "QualityOverrides.txt").write_text("天=Thiên\n", encoding="utf-8")
    dic = load_dictionary(d)
    draft = vp_plan(dic, "小天才")
    assert "Literal" in draft.text

    # Khong co literal dai: pattern khop prefix 小天, de chung minh pattern
    # se nuot neu khong bi literal dai hon chan.
    d2 = tmp_path / "pat-only"
    d2.mkdir()
    (d2 / "LuatNhan.txt").write_text("小{n}=tiểu {1}\n", encoding="utf-8")
    (d2 / "QualityOverrides.txt").write_text("天=Thiên\n", encoding="utf-8")
    only = vp_plan(load_dictionary(d2), "小天才")
    assert "Literal" not in only.text
    assert "Thiên" in only.text


def test_deterministic_same_input_same_sha(tmp_path):
    """Nhom 6: cung source + dict + config -> cung output SHA-256."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    out_a = tmp_path / "a.vi.txt"
    out_b = tmp_path / "b.vi.txt"
    pa = create_project(tmp_path / "proj-a")
    pb = create_project(tmp_path / "proj-b")
    res_a = translate_project(
        pa, TranslateRequest(source=src, output=out_a, dict_dir=str(dict_dir))
    )
    res_b = translate_project(
        pb, TranslateRequest(source=src, output=out_b, dict_dir=str(dict_dir))
    )
    assert res_a.exit_code == 0 and res_b.exit_code == 0
    assert res_a.report["sha256"] == res_b.report["sha256"] == _sha(out_a) == _sha(out_b)

    b1 = build_revision(dict_dir, pa, [])
    b2 = build_revision(dict_dir, pb, [])
    assert b1.revision_id == b2.revision_id
