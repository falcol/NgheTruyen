"""Tests cho occurrence constraints (thiet ke muc 14/39)."""
from __future__ import annotations

from zhvi.occurrence import OccurrenceConstraint, derive_constraints, guard_occurrences
from zhvi.vietphrase.trace import VpSpan


def _span(oid="o1", start=0, end=2, source="凌天", target="Lăng Thiên", policy="HARD"):
    return VpSpan(
        occurrence_id=oid, source_start=start, source_end=end, source=source,
        target=target, alternatives=(), entry_version_id="e1", policy=policy, path_score=1.0,
    )


def test_hard_constraint_present():
    c = OccurrenceConstraint("o1", 0, 2, "e1", None, "Lăng Thiên", ["Lăng Thiên"], "HARD")
    r = guard_occurrences("凌天来了", "Lăng Thiên đã tới", [c])
    assert r.ok


def test_hard_constraint_missing():
    c = OccurrenceConstraint("o1", 0, 2, "e1", None, "Lăng Thiên", [], "HARD")
    r = guard_occurrences("凌天来了", "Hắn đã tới", [c])
    assert not r.ok
    assert any(e.startswith("OCCURRENCE_MISSING") for e in r.errors)


def test_alias_allowed():
    c = OccurrenceConstraint("o1", 0, 2, "e1", None, "Lăng Thiên", ["Lăng Thiên ca ca"], "HARD")
    r = guard_occurrences("凌天来了", "Lăng Thiên ca ca đã tới", [c])
    assert r.ok


def test_contextual_not_enforced():
    c = OccurrenceConstraint("o1", 0, 2, "e1", None, "Bất kỳ", [], "CONTEXTUAL")
    r = guard_occurrences("任意", "tùy ý", [c])
    assert r.ok  # CONTEXTUAL khong ep


def test_derive_from_spans():
    spans = [_span(), _span(oid="o2", start=3, end=5, source="剑宗", target="Kiếm Tông", policy="PREFERRED")]
    cons = derive_constraints(spans)
    assert len(cons) == 2
    assert cons[0].policy == "HARD"
    assert cons[1].canonical_target == "Kiếm Tông"


def test_derive_entity_map_promotes_hard():
    spans = [_span(oid="o1", source="万宝宗", target="Van Bao Tong", policy="PREFERRED")]
    cons = derive_constraints(spans, entity_map={"万宝宗": "Vạn Bảo Tông"})
    assert cons[0].policy == "HARD"
    assert cons[0].canonical_target == "Vạn Bảo Tông"
    assert cons[0].entity_id == "Vạn Bảo Tông"


def test_guard_multiple_constraints():
    c1 = OccurrenceConstraint("o1", 0, 2, "e1", None, "Lăng Thiên", [], "HARD")
    c2 = OccurrenceConstraint("o2", 3, 5, "e2", None, "Kiếm Tông", [], "HARD")
    r = guard_occurrences("凌天 剑宗", "Lăng Thiên rút kiếm", [c1, c2])
    assert not r.ok
    assert len(r.errors) == 1  # chi thieu Kiếm Tông
