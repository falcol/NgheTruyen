"""Tests cho glossary toan cuc (SERIES_MANUAL) va thu tu precedence."""
from __future__ import annotations

from pathlib import Path

from zhvi.vietphrase.lattice import greedy_path
from zhvi.vietphrase.loader import load_dictionary

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"


def test_global_glossary_applies_without_book(tmp_path):
    """Term khong co trong dict nen -> chi xuat hien khi nap global glossary."""
    g = tmp_path / "global.tsv"
    g.write_text("全局測試詞=thuật ngữ toàn cục\n", encoding="utf-8")
    dic_off = load_dictionary(DICT_DIR)
    dic_on = load_dictionary(DICT_DIR, global_glossary=g)
    assert greedy_path(dic_off, "全局測試詞")[0].target != "thuật ngữ toàn cục"
    assert greedy_path(dic_on, "全局測試詞")[0].target == "thuật ngữ toàn cục"


def test_book_manual_overrides_global(tmp_path):
    g = tmp_path / "global.tsv"
    g.write_text("小胖=Tiểu Bàn\n", encoding="utf-8")
    b = tmp_path / "book.tsv"
    b.write_text("小胖=Thằng Mập\n", encoding="utf-8")
    dic = load_dictionary(DICT_DIR, manual_glossary=b, global_glossary=g)
    edges = greedy_path(dic, "小胖")
    assert edges[0].target == "Thằng Mập"


def test_global_changes_fingerprint(tmp_path):
    g = tmp_path / "global.tsv"
    g.write_text("小胖=Tiểu Bàn\n", encoding="utf-8")
    from zhvi.vietphrase.loader import dict_files_fingerprint

    fp0 = dict_files_fingerprint(DICT_DIR, None)
    fp1 = dict_files_fingerprint(DICT_DIR, None, g)
    assert fp0 != fp1


def test_missing_global_file_is_noop(tmp_path):
    """File global khong ton tai -> hanh vi giong het khong truyen global."""
    dic_none = load_dictionary(DICT_DIR)
    dic_missing = load_dictionary(DICT_DIR, global_glossary=tmp_path / "khong-ton-tai.tsv")
    a = greedy_path(dic_none, "小胖")[0].target
    b = greedy_path(dic_missing, "小胖")[0].target
    assert a == b
