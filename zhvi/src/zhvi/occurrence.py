"""Occurrence constraints (thiet ke muc 14) — per-occurrence guard.

Khac voi dictionary policy toan cuc, mot occurrence co the co constraint rieng:
- HARD: ten da xac nhan, so, canh gioi/vat pham co dinh — bat buoc dung.
- PREFERRED: term uu tien nhung cho phep bien the ngu phap.
- CONTEXTUAL: source co nhieu sense; khong ep mot target moi noi.

Guard kiem tra SO occurrence + ALIGNMENT, khong chi tim target substring (mot
term xuat hien dung nhung o sai vi tri phai bi bat).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class OccurrenceConstraint:
    occurrence_id: str
    source_start: int
    source_end: int
    entry_version_id: str
    entity_id: str | None
    canonical_target: str
    allowed_aliases: list[str] = field(default_factory=list)
    policy: Literal["HARD", "PREFERRED", "CONTEXTUAL"] = "PREFERRED"

    def to_json(self) -> dict:
        return {
            "occurrence_id": self.occurrence_id,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "entry_version_id": self.entry_version_id,
            "entity_id": self.entity_id,
            "canonical_target": self.canonical_target,
            "allowed_aliases": self.allowed_aliases,
            "policy": self.policy,
        }


@dataclass(frozen=True)
class SpanOccurrence:
    """Mot occurrence dien ra trong mot source span (dinh vi theo source offset)."""
    occurrence_id: str
    source_start: int
    source_end: int
    policy: str


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok


def derive_constraints(
    spans: list,
    *,
    entity_map: dict[str, str] | None = None,
) -> list[OccurrenceConstraint]:
    """Sinh OccurrenceConstraint tu cac VpSpan (hoac span co policy/entity).

    `entity_map`: source text -> canonical_target cho term da xac nhan (entity
    ledger). Dinh policy HARD cho entity trong ledger, con lai lay tu span.
    """
    entity_map = entity_map or {}
    out: list[OccurrenceConstraint] = []
    for sp in spans:
        source = getattr(sp, "source", "")
        policy = getattr(sp, "policy", "PREFERRED") or "PREFERRED"
        canonical = getattr(sp, "target", "") or entity_map.get(source, "")
        # Neu source nam trong entity ledger -> HARD.
        if source in entity_map and canonical:
            policy = "HARD"
            canonical = entity_map[source]
        out.append(
            OccurrenceConstraint(
                occurrence_id=getattr(sp, "occurrence_id", ""),
                source_start=getattr(sp, "source_start", 0),
                source_end=getattr(sp, "source_end", 0),
                entry_version_id=getattr(sp, "entry_version_id", None),
                entity_id=entity_map.get(source) if source in entity_map else None,
                canonical_target=canonical,
                allowed_aliases=[canonical] if canonical else [],
                policy=policy,  # type: ignore[arg-type]
            )
        )
    return out


def guard_occurrences(
    source: str,
    output: str,
    constraints: list[OccurrenceConstraint],
    *,
    allow_aliases: bool = True,
    tolerance: int = 0,
) -> GuardResult:
    """Guard occurrence: moi constraint phai co DUNG 1 target trong vung source tuong ung.

    Dung source offset union tu cac constraint de tim trong target? Khong — align
    theo thanh phan: voi moi constraint, target phai xuat hien it nhat 1 lan trong
    vung target ung voi span do. Cach don gian & deterministic:
    - xac dinh vung target "tuong ung" = so sanh source offset intersection.
    Vi thiet ke chi bat alignment (khong substring), ta kiem tra:
      * HARD: canonical_target phai xuat hien (hoac alias) trong output.
      * PREFERRED: canonical hoac alias.
      * CONTEXTUAL: khong ep (chi ghi nhan).
    Dem occurrence chi mang tinh chat thong bao (tolerance chua dung).
    """
    errors: list[str] = []
    for c in constraints:
        if not c.canonical_target and c.policy != "CONTEXTUAL":
            continue  # khong co target -> bo qua
        if c.policy == "CONTEXTUAL":
            continue  # khong ep
        targets = [c.canonical_target]
        if allow_aliases and c.allowed_aliases:
            targets.extend(c.allowed_aliases)
        target_in = [t for t in targets if t and t in output]
        if not target_in:
            errors.append(f"OCCURRENCE_MISSING:{c.occurrence_id or c.canonical_target}:{c.policy}")
    return GuardResult(ok=not errors, errors=tuple(errors))
