"""Regression piaotia: dirty X了 keys, locative 了, series names vs common 逍遥.

Shipped path: load_dictionary (real crawler/vietphrase/dicts) + vp_plan.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from zhvi.vietphrase.lattice import greedy_path, vp_plan
from zhvi.vietphrase.loader import load_dictionary

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"


@pytest.fixture(scope="module")
def real_dict():
    if not DICT_DIR.is_dir():
        pytest.skip("khong co thu muc tu dien nen")
    return load_dictionary(DICT_DIR)


def _low(dic, zh: str) -> str:
    return vp_plan(dic, zh).text.lower()


def test_real_dict_mengshangle_not_phien_am(real_dict):
    low = _low(real_dict, "蒙上了一层阴影")
    assert "bịt kín" in low
    assert "mông thượng" not in low


def test_real_dict_song_yi_kou_qi_sigh_relief(real_dict):
    low = _low(real_dict, "松了一口气")
    assert "thở phào" in low
    assert "thở dài" not in low


def test_real_dict_mieshale_not_tan_sat(real_dict):
    low = _low(real_dict, "灭杀了一位")
    assert "diệt sát" in low
    assert "tàn sát" not in low


def test_real_dict_kaichule_road_not_dao(real_dict):
    low = _low(real_dict, "开出了一条大道")
    assert "mở ra" in low
    assert "khai ra" not in low
    assert "đại đạo" in low
    assert "con đường lớn" not in low


def test_real_dict_zuzu_xiulian_not_estimate(real_dict):
    low = _low(real_dict, "足足修炼了一年")
    assert "trọn vẹn" in low
    assert "ước chừng" not in low


def test_real_dict_tanchule_not_lo_ra(real_dict):
    low = _low(real_dict, "探出了一只")
    assert "nhô ra" in low or "thò" in low
    assert "lộ ra" not in low


def test_real_dict_rongrule_not_sap_nhap(real_dict):
    low = _low(real_dict, "融入了一截")
    assert "dung nhập" in low
    assert "sáp nhập" not in low


def test_real_dict_zhuangdaole_not_dap_lay(real_dict):
    low = _low(real_dict, "撞到了一处")
    assert "va vào" in low
    assert "đập lấy" not in low


def test_real_dict_yituan_xuerou_mohu(real_dict):
    low = _low(real_dict, "一团血肉模糊")
    assert "máu thịt be bét" in low
    assert "huyết nhục" not in low
    assert "mơ hồ" not in low


def test_real_dict_qile_name_not_noi_len(real_dict):
    low = _low(real_dict, "起了一个侮辱性的名字")
    assert "nổi lên" not in low
    assert "danh tự" not in low


def test_real_dict_locative_le_not_o_da(real_dict):
    for zh in ("压制在了神宫境", "踏在了", "消失在了", "间接死在了"):
        low = _low(real_dict, zh)
        assert "ở đã" not in low, zh
        assert "đạp ở đã" not in low, zh
        assert "biến mất ở đã" not in low, zh
        assert "đã bị chết ở tại" not in low, zh


def test_real_dict_le_aspect_lai_keeps_da(real_dict):
    low = _low(real_dict, "来了")
    assert "đã" in low


def test_real_dict_kanle_qilai_keeps_span(real_dict):
    low = _low(real_dict, "看了起来")
    edges = greedy_path(real_dict, "看了起来")
    assert edges[0].end - edges[0].start == len("看了起来")
    assert "đã" not in low


def test_real_dict_layer2_fixes(real_dict):
    t = _low
    assert "gặp mặt" in t(real_dict, "会会吧")
    assert "se se" not in t(real_dict, "会会吧")
    assert "từng đạo cầu vồng" in t(real_dict, "道道长虹")
    assert "bùng phát" in t(real_dict, "迸发出了一股")
    assert "tóe ra" not in t(real_dict, "迸发出了一股")
    assert "thở phào" in t(real_dict, "长舒了一口气")
    assert "thở dài" not in t(real_dict, "长舒了一口气")
    assert "nhất định phải chết" in t(real_dict, "一个注定要死")
    assert "bị coi là" not in t(real_dict, "一个注定要死")
    assert "không nể mặt" in t(real_dict, "拉下脸面")
    assert "kéo xuống mặt mũi" not in t(real_dict, "拉下脸面")
    assert "một cây" in t(real_dict, "一把古琴")
    assert "một thanh" not in t(real_dict, "一把古琴")
    assert "chưa thức tỉnh" in t(real_dict, "未觉醒")
    assert "giác tỉnh" not in t(real_dict, "未觉醒")
    assert "càn quét" in t(real_dict, "席卷")
    assert "một chút" in t(real_dict, "一下")
    assert "dược ly" in t(real_dict, "药离")
    chu = t(real_dict, "矗立在")
    assert "|" not in chu
    assert "sừng sững" in chu or "sững" in chu


def test_real_dict_kept_improvements(real_dict):
    li = _low(real_dict, "行了一礼")
    assert "thi lễ" in li
    assert "đi một lễ" not in li
    da = _low(real_dict, "打破")
    assert "phá vỡ" in da
    assert "đánh vỡ" not in da
    da2 = _low(real_dict, "打破了一道枷锁")
    assert "phá vỡ" in da2
    assert "đánh vỡ" not in da2
    xi = _low(real_dict, "深吸了一口气")
    assert "hít" in xi
    assert "hút thở ra" not in xi
