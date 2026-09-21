"""Parity test: lattice moi vs greedy longest-match cu (crawler/vietphrase/engine.py).

Khac biet phai giai thich duoc: lattice khong duoc te hon greedy — ty le khop
~100% tren van ban co nhieu phrase; khi khac, lattice phai it sot CJK hon hoac
it phan manh hon.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"

from zhvi.vietphrase.lattice import vp_plan
from zhvi.vietphrase.loader import load_dictionary


@pytest.fixture(scope="module")
def dic():
    if not DICT_DIR.is_dir():
        pytest.skip("khong co tu dien nen")
    return load_dictionary(DICT_DIR)


@pytest.fixture(scope="module")
def old_convert():
    sys.path.insert(0, str(REPO_ROOT / "crawler"))
    try:
        from vietphrase.engine import convert  # noqa: PLC0415

        return convert
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"engine cu khong nap duoc: {e}")


def _paragraphs() -> list[str]:
    text = (REPO_ROOT / "raw_china" / "chap1_raw.txt").read_text(encoding="utf-8")
    return [p.strip() for p in text.splitlines() if p.strip()]


def test_parity_chap1(dic, old_convert):
    paras = _paragraphs()
    assert len(paras) > 20
    diffs = []
    diff_idx = []
    old_cjk = 0
    new_cjk = 0
    import re

    cjk = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
    for i, p in enumerate(paras):
        old_out = old_convert(p)
        new_out = vp_plan(dic, p).text
        old_cjk += len(cjk.findall(old_out))
        new_cjk += len(cjk.findall(new_out))
        if old_out != new_out:
            diffs.append((p[:40], old_out[:60], new_out[:60]))
            diff_idx.append(i)
    ratio = len(diffs) / len(paras)
    # ContextPatterns inversion vs greedy. Cap 0.22; khong noi khi them rule.
    assert ratio < 0.22, f"{len(diffs)}/{len(paras)} doan khac: {diffs[:3]}"
    # Moi diff phai thuoc whitelist da duyet (lattice TOT hon greedy).
    # Rule moi gay diff moi hop le -> them index + ly do vao day (review
    # tuong minh), khong duoc xoa cap mo. Cu the (chap1_raw.txt):
    # 9/18/26/27/36: inversion X的Y -> Y cua X; 25/48: pronoun-NP tach dung
    # (segmenter-8); 21/22/46: giu aspect 了 (đã), engine cu DROP.
    allowed = {9, 18, 21, 22, 25, 26, 27, 36, 46, 48}
    unexpected = [i for i in diff_idx if i not in allowed]
    assert not unexpected, f"diff la ngoai whitelist: {unexpected}"
    # khong duoc sot CJK nhieu hon engine cu
    assert new_cjk <= old_cjk, f"new {new_cjk} > old {old_cjk}"


def test_parity_known_sentence(dic, old_convert):
    src = "白髮老者大口緊閉，竟然是以神念發聲。"
    old_out = old_convert(src)
    new_out = vp_plan(dic, src).text
    assert new_out == old_out, f"old={old_out!r} new={new_out!r}"
