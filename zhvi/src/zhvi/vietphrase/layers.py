"""Dictionary layers va precedence (thiet ke muc 11.1).

Precedence ma hoa theo (loai layer, trust file, thu tu nap) — khong dung
mot priority integer tuy y de pha policy. Layer rank cao hon thang tuyet doi.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# Thu tu tang dan: cao = thang.
class Layer(IntEnum):
    BASE_SINGLE = 0      # Han-Viet fallback (ChinesePhienAmWords + single-char khac)
    BOOK_AUTO = 1        # entity tu hoc, chi fill-only (trong o M1)
    BASE_MULTI = 2       # phrase/name tu bo nen (VietPhrase, LuatNhan, Names)
    GLOBAL_MANUAL = 3    # Custom.txt, QualityOverrides.txt — da duyet toan cuc
    SERIES_MANUAL = 4    # term dung cho mot series
    BOOK_MANUAL = 5      # glossary.manual.tsv cua truyen
    USER_SEGMENT = 6     # block nguoi dung khoa


@dataclass(frozen=True, order=True)
class Precedence:
    """Thu tu so sanh: (layer, trust_file, load_index) — lon hon = thang."""

    layer: int
    trust: float
    load_index: int


@dataclass(frozen=True)
class DictEntry:
    source: str
    target: str
    precedence: Precedence
    entry_version_id: str
    # policy mac dinh theo loai layer (M2 nang thanh per-occurrence)
    policy: str = "CONTEXTUAL"

    @property
    def is_manual(self) -> bool:
        return self.precedence.layer >= Layer.GLOBAL_MANUAL


def default_policy(layer: Layer) -> str:
    if layer >= Layer.BOOK_MANUAL:
        return "PREFERRED"
    if layer == Layer.GLOBAL_MANUAL:
        return "PREFERRED"
    return "CONTEXTUAL"


def make_entry(
    source: str,
    target: str,
    layer: Layer,
    trust: float,
    load_index: int,
    version_tag: str,
) -> DictEntry:
    return DictEntry(
        source=source,
        target=target,
        precedence=Precedence(int(layer), trust, load_index),
        entry_version_id=f"{version_tag}:{source}",
        policy=default_policy(layer),
    )
