"""Tests cho luat nhan pattern {s}/{n} (thiet ke muc 11.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from zhvi.vietphrase.loader import load_dictionary
from zhvi.vietphrase.patterns import compile_rule, fill_target
from zhvi.vietphrase.layers import Layer

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"


@pytest.fixture(scope="module")
def dic():
    if not DICT_DIR.is_dir():
        pytest.skip("khong co thu muc tu dien nen")
    return load_dictionary(DICT_DIR)


def test_compile_basic():
    rule = compile_rule("方圆近{s}里", "bán kính {s} dặm", (int(Layer.BASE_MULTI), 15.0, 1), "CONTEXTUAL")
    assert rule is not None
    assert rule.slots == ("s",)
    m = rule.regex.match("方圆近三十里")
    assert m and m.group(1) == "三十"


def test_compile_skips_plain_and_zero():
    assert compile_rule("凌天", "Lăng Thiên", (2, 1.0, 0), "CONTEXTUAL") is None
    assert compile_rule("在{0}之上", "trên {0}", (2, 1.0, 0), "CONTEXTUAL") is None


def test_compile_p_greedy_unanchored():
    rule = compile_rule("桌上的{p}", "{p} trên bàn", (4, 100.0, 0), "PREFERRED")
    assert rule is not None
    assert rule.slots == ("p",)
    m = rule.regex.match("桌上的幼儿书籍就看")
    assert m and m.group(1) == "幼儿书籍"
    m2 = rule.regex.match("桌上的地图就看")
    assert m2 and m2.group(1) == "地图"
    m3 = rule.regex.match("桌上的书籍看完")
    assert m3 and m3.group(1) == "书籍"


def test_compile_v_slot():
    rule = compile_rule("一把{v}", "một cái {v}", (4, 25.0, 0), "PREFERRED")
    assert rule is not None
    m = rule.regex.match("一把拽住凌天")
    assert m and m.group(1) == "拽住"
    m2 = rule.regex.match("一把扔掉")
    assert m2 and m2.group(1) == "扔掉"
    assert rule.regex.match("一把剑") is None


def test_compile_regex_group_alternation():
    rule = compile_rule("(上午|下午)?{s}点", "{1} giờ", (2, 15.0, 0), "CONTEXTUAL")
    assert rule is not None
    m = rule.regex.match("下午3点")
    assert m and m.group(2) == "3"


def test_fill_target_named_and_positional():
    rule = compile_rule("{s}年{s}月{s}号", "ngày {3} tháng {2} năm {1}", (2, 15.0, 0), "CONTEXTUAL")
    m = rule.regex.match("2023年5月12号")
    out = fill_target(rule, m, lambda s: s)
    assert out == "ngày 12 tháng 5 năm 2023"


def test_noun_slot_translated_recursively(dic):
    from zhvi.vietphrase.lattice import vp_plan

    draft = vp_plan(dic, "远远不是凌天的对手")
    assert "đối thủ của Lăng Thiên" in draft.text


def test_number_slot_date(dic):
    from zhvi.vietphrase.lattice import vp_plan

    draft = vp_plan(dic, "他在2023年5月12号到达")
    assert "ngày 12 tháng 5 năm 2023" in draft.text


def test_patterns_off_restores_literal(dic):
    from zhvi.vietphrase.lattice import greedy_path

    if not DICT_DIR.is_dir():
        pytest.skip()
    dic_off = load_dictionary(DICT_DIR, patterns=False)
    assert not dic_off.patterns
    # voi patterns=False, '三百年后' dich bang trie thong thuong (van co ket qua)
    on = greedy_path(dic, "三百年后")
    off = greedy_path(dic_off, "三百年后")
    assert "".join(e.target for e in on)  # ca hai deu dich duoc
    assert "".join(e.target for e in off)


def test_no_brace_leak_in_output(dic):
    """Khong duoc con soc '{s}'/'{n}' trong output khi pattern match."""
    from zhvi.vietphrase.lattice import vp_plan

    for t in ["方圆近三十里的范围内", "他在三点四十五分左右到达"]:
        assert "{s}" not in vp_plan(dic, t).text
        assert "{n}" not in vp_plan(dic, t).text
        assert "{p}" not in vp_plan(dic, t).text
        assert "{v}" not in vp_plan(dic, t).text
