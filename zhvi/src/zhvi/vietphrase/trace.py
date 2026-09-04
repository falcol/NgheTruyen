"""VpSpan / VpDraft — trace cua mot ban dich VietPhrase (thiet ke muc 11.3)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceSpan:
    source_start: int
    source_end: int
    source: str


@dataclass(frozen=True)
class VpSpan:
    occurrence_id: str
    source_start: int
    source_end: int
    source: str
    target: str
    alternatives: tuple[str, ...]
    entry_version_id: str | None
    policy: str  # HARD | PREFERRED | CONTEXTUAL
    path_score: float


@dataclass(frozen=True)
class VpDraft:
    text: str
    spans: tuple[VpSpan, ...]
    unknown_spans: tuple[SourceSpan, ...]
    single_char_ratio: float
    lattice_margin: float
    lattice_entropy: float
    warnings: tuple[str, ...] = field(default_factory=tuple)
    # AD-18 (story 2.6): offsets (start, end) cac span bi repetition collapse
    collapsed_spans: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    @property
    def coverage(self) -> float:
        """Ty le ky tu CJK duoc map boi entry co thuc (khong phai unknown)."""
        total = sum(s.source_end - s.source_start for s in self.spans)
        unknown = sum(s.source_end - s.source_start for s in self.unknown_spans)
        denom = total + unknown
        return total / denom if denom else 1.0
