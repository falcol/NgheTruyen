"""Invariant gate (thiet ke muc 17/17.1) — hard-error checks pre-publish.

Gate chi bat Nhung hard loi deterministic & dang tin cay o block level:
output rong/truncated, con chu Han (ngoai allowlist), hong quote/bracket.

Cac check "mat so/tien/don vi/cap bac" va "mat phu dinh/modal" can *alignment*
giua source span va target (OccurrenceConstraint, muc 14/17). Chay khi caller
truyen `guarded_terms` — khong thi khong bat (tranh false positive vi source la
chu Han, output la tieng Viet). Document-level check (duplicate/missing/reorder
block) da nam o export.verify_output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
DIGIT_RE = re.compile(r"[0-9０-９]+")

QUOTE_PAIRS = (("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"), ("（", "）"), ("(", ")"))


@dataclass(frozen=True)
class InvariantResult:
    ok: bool
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok


def run_invariants(
    *,
    source: str,
    output: str,
    block_id: str | None = None,
    cjk_allowlist: set[str] | None = None,
    guarded_terms: dict[str, str] | None = None,
) -> InvariantResult:
    """Chay cac invariant hard check tren mot block.

    `cjk_allowlist`: tap chu Han duoc phep sot lai output (mac dinh rong — mot
    chu Han nao trong output la hard error).

    `guarded_terms`: mapping source-term -> bat buoc target-xuat-hien (vi du
    {"万宝宗": "Vạn Bảo Tông"}). Chi kiem tra khi co mapping; day la mot phan
    cua OccurrenceConstraint (muc 14) duoc truyen vao o 2b.
    """
    errors: list[str] = []

    # 1. output rong khi source co noi dung.
    if source.strip() and not output.strip():
        errors.append("EMPTY_OUTPUT")

    # 2. con chu Han ngoai allowlist.
    allow = cjk_allowlist or set()
    leftover = {ch for ch in CJK_RE.findall(output)} - allow
    if leftover:
        errors.append(f"LEFTOVER_CJK:{len(leftover)}")

    # 3. quote/bracket khong can bang.
    for open_ch, close_ch in QUOTE_PAIRS:
        if output.count(open_ch) != output.count(close_ch):
            errors.append(f"UNBALANCED_QUOTE:{open_ch}{close_ch}")
            break

    # 4. guarded terms bat buoc xuat hien (occurrence constraint, muc 14).
    if guarded_terms:
        for src, target in guarded_terms.items():
            if target not in output:
                errors.append(f"GUARDED_TERM_MISSING:{src}")

    return InvariantResult(ok=not errors, errors=tuple(errors))
