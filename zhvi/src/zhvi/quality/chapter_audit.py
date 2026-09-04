"""Chapter audit (thiet ke muc 17.3) — consistency dalam mot chapter.

Kiem tra: entity/canonical-target consistency, alias/xưng hô drift, speaker/
pronoun anomalies, duplicated/missing blocks. Doc nhieu block cung chapter
roi do lenh (khong require model).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class AuditFinding:
    code: str
    block_ids: tuple[str, ...]
    detail: str = ""

    def to_json(self) -> dict:
        return {"code": self.code, "block_ids": list(self.block_ids), "detail": self.detail}


@dataclass
class ChapterAudit:
    chapter_id: int
    findings: list[AuditFinding] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.findings is None:
            self.findings = []

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_json(self) -> dict:
        return {
            "chapter_id": self.chapter_id,
            "ok": self.ok,
            "findings": [f.to_json() for f in self.findings],
        }


def entity_alias_consistency(
    chapter_id: int,
    blocks: list[dict],
    *,
    entity_targets: dict[str, set[str]],
) -> list[AuditFinding]:
    """Doi voi moi entity, cac block phai dung 1 canonical (hoac alias cho phep)."""
    findings: list[AuditFinding] = []
    for entity, allowed in entity_targets.items():
        used: list[str] = []
        for blk in blocks:
            text = blk.get("output", "")
            for target in allowed:
                if target and target in text:
                    used.append(target)
                    break
        if used and len(set(used)) > 1:
            findings.append(
                AuditFinding("ENTITY_DRIFT", tuple(blk["block_id"] for blk in blocks),
                             f"entity={entity} targets={sorted(set(used))}")
            )
    return findings


def pronoun_address_drift(
    chapter_id: int,
    blocks: list[dict],
    *,
    address_terms: dict[str, str],
) -> list[AuditFinding]:
    """Xưng hô/title thay doi bat thuong giua cac block cung chuong."""
    counter: Counter[str] = Counter()
    for blk in blocks:
        text = blk.get("output", "")
        for key, terms in address_terms.items():
            for t in terms:
                if t in text:
                    counter[key] += 1
                    break
    findings: list[AuditFinding] = []
    for key, total in counter.items():
        # Chi bat khi xuat hien nhieu block va co bien the — day la drift.
        if total > 1:
            findings.append(AuditFinding("ADDRESS_DRIFT", tuple(b["block_id"] for b in blocks),
                                         f"address={key} count={total}"))
    return findings


def duplicate_blocks(
    chapter_id: int,
    blocks: list[dict],
) -> list[AuditFinding]:
    """Phat hien block bi duplicate (cung output) — thuong do parser error."""
    seen: dict[str, list[str]] = defaultdict(list)
    for blk in blocks:
        key = blk.get("output", "").strip()
        if key:
            seen[key].append(blk["block_id"])
    findings = [AuditFinding("DUPLICATE_BLOCK", tuple(ids), f"len={len(ids)}")
                for key, ids in seen.items() if len(ids) > 1]
    return findings


def missing_blocks(chapter_id: int, blocks: list[dict], expected: int) -> list[AuditFinding]:
    """So block thuc te < expected (mat block)."""
    if len(blocks) < expected:
        return [AuditFinding("MISSING_BLOCKS", tuple(b["block_id"] for b in blocks),
                             f"got={len(blocks)} expected={expected}")]
    return []


def join_entities_from_blocks(blocks: list[dict]) -> dict[str, set[str]]:
    """Gop entity -> tap alias tu qa entity (neu co) cua cac block."""
    ents: dict[str, set[str]] = defaultdict(set)
    for blk in blocks:
        qa = blk.get("qa", {})
        for ent, targets in qa.get("entities", {}).items():
            ents[ent].update(targets)
    return ents


def audit_chapter(
    *,
    chapter_id: int,
    blocks: list[dict],
    entity_targets: dict[str, set[str]] | None = None,
    address_terms: dict[str, str] | None = None,
    expected_blocks: int | None = None,
) -> ChapterAudit:
    """Chay cac kiem tra co ban cho mot chuong."""
    findings: list[AuditFinding] = []
    if entity_targets:
        findings.extend(entity_alias_consistency(chapter_id, blocks, entity_targets=entity_targets))
    if address_terms:
        findings.extend(pronoun_address_drift(chapter_id, blocks, address_terms=address_terms))
    findings.extend(duplicate_blocks(chapter_id, blocks))
    if expected_blocks is not None:
        findings.extend(missing_blocks(chapter_id, blocks, expected_blocks))
    return ChapterAudit(chapter_id=chapter_id, findings=findings)
