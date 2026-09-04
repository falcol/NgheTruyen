"""Tests cho chapter audit (thiet ke muc 17.3/39)."""
from __future__ import annotations

from zhvi.quality.chapter_audit import (
    audit_chapter,
    duplicate_blocks,
    entity_alias_consistency,
    missing_blocks,
    pronoun_address_drift,
)


def _blk(bid, output, qa=None):
    return {"block_id": bid, "output": output, "qa": qa or {}}


def test_clean_chapter_ok():
    blocks = [_blk("c1b1", "Lăng Thiên nhìn xa"), _blk("c1b2", "Hắn rút kiếm")]
    audit = audit_chapter(chapter_id=1, blocks=blocks, expected_blocks=2)
    assert audit.ok
    assert audit.findings == []


def test_duplicate_blocks_detected():
    blocks = [_blk("c1b1", "Giống nhau"), _blk("c1b2", "Giống nhau")]
    findings = duplicate_blocks(1, blocks)
    assert len(findings) == 1
    assert findings[0].code == "DUPLICATE_BLOCK"
    assert set(findings[0].block_ids) == {"c1b1", "c1b2"}


def test_missing_blocks_detected():
    blocks = [_blk("c1b1", "A")]
    findings = missing_blocks(1, blocks, expected=3)
    assert len(findings) == 1
    assert findings[0].code == "MISSING_BLOCKS"


def test_entity_drift_detected():
    blocks = [_blk("c1b1", "Lăng Thiên nói"), _blk("c1b2", "Lăng ca ca đi")]
    findings = entity_alias_consistency(
        1, blocks, entity_targets={"凌天": {"Lăng Thiên", "Lăng ca ca"}}
    )
    assert len(findings) == 1
    assert findings[0].code == "ENTITY_DRIFT"


def test_entity_consistent_no_drift():
    blocks = [_blk("c1b1", "Lăng Thiên nói"), _blk("c1b2", "Lăng Thiên đi")]
    findings = entity_alias_consistency(
        1, blocks, entity_targets={"凌天": {"Lăng Thiên", "Lăng ca ca"}}
    )
    assert findings == []


def test_address_drift_detected():
    blocks = [_blk("c1b1", "huynh đệ"), _blk("c1b2", "đệ đệ")]
    findings = pronoun_address_drift(
        1, blocks, address_terms={"xưng hô": ["huynh đệ", "đệ đệ"]}
    )
    assert len(findings) == 1
    assert findings[0].code == "ADDRESS_DRIFT"


def test_audit_combines_findings():
    blocks = [_blk("c1b1", "A"), _blk("c1b2", "A")]
    audit = audit_chapter(chapter_id=1, blocks=blocks, expected_blocks=3)
    codes = {f.code for f in audit.findings}
    assert "DUPLICATE_BLOCK" in codes
    assert "MISSING_BLOCKS" in codes
    assert not audit.ok


def test_audit_to_json():
    blocks = [_blk("c1b1", "A"), _blk("c1b2", "A")]
    audit = audit_chapter(chapter_id=1, blocks=blocks)
    j = audit.to_json()
    assert j["chapter_id"] == 1
    assert j["ok"] is False
    assert j["findings"][0]["code"] == "DUPLICATE_BLOCK"
