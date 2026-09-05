"""Evidence evaluator — tin hieu kiem chung duoc cho tung candidate (story 3.3).

AC 2 / AD-6: evidence chi tu observation + trang thai tu dien hien tai —
khong doc runs/blocks/output cuoi. Nhom regression la placeholder, story
3.4 populate sau isolation rerun (vi tin hieu do can output).
AD-7: score chi dung xep hang — hard gate la story 3.4.
AD-8: evidence la book SQLite state, replace-not-append theo scope.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass

from zhvi.learning.candidate import entry_layer
from zhvi.state import EvidenceRow, State, cursor_dicts
from zhvi.vietphrase.layers import Layer
from zhvi.vietphrase.loader import Dictionary

# Do sau toi da khi DFS tim entry dai hon chua key lam prefix (NGRAM_MAX).
_EXTEND_MAX_DEPTH = 8


@dataclass(frozen=True)
class EvidenceSummary:
    book_id: str
    dictionary_revision_id: str
    candidates: int
    evidence_rows: int
    benefit_positive: int
    manual_conflicts: int

    def to_json(self) -> dict:
        return {
            "book_id": self.book_id,
            "dictionary_revision": self.dictionary_revision_id,
            "candidates": self.candidates,
            "evidence_rows": self.evidence_rows,
            "benefit_positive": self.benefit_positive,
            "manual_conflicts": self.manual_conflicts,
        }


def _walk(dic: Dictionary, key: str):
    """Node cuoi cua key trong trie — None neu khong ton tai."""
    node = dic.root
    for ch in key:
        node = node.children.get(ch)
        if node is None:
            return None
    return node


def _has_extension(node, depth: int, layer_match: Callable[[int], bool]) -> bool:
    """DFS con: co entry dai hon (chua key lam prefix) khop layer_match?"""
    if node is None or depth == 0:
        return False
    for child in node.children.values():
        if any(layer_match(entry_layer(e)) for e in child.entries):
            return True
        if _has_extension(child, depth - 1, layer_match):
            return True
    return False


def _span_manual_conflict(dic: Dictionary, key: str) -> bool:
    """Key overlap SPAN voi entry manual (khac _manual_conflict cua builder
    3.2 — ben kia chi check key trung dung): manual key la prefix cua key,
    hoac key la prefix cua manual key dai hon."""
    node = dic.root
    for ch in key:
        node = node.children.get(ch)
        if node is None:
            return False
        if any(entry_layer(e) >= Layer.GLOBAL_MANUAL for e in node.entries):
            return True
    return _has_extension(
        node, _EXTEND_MAX_DEPTH, lambda layer: layer >= Layer.GLOBAL_MANUAL
    )


def _overlap_existing(dic: Dictionary, key: str) -> bool:
    """Key la prefix cua entry auto/base dai hon (substring conflict)."""
    node = _walk(dic, key)
    return _has_extension(
        node, _EXTEND_MAX_DEPTH, lambda layer: layer < Layer.GLOBAL_MANUAL
    )


def ev_id(book_id: str, drev: str, candidate_id: str, group: str) -> str:
    """Id evidence content-addressed — public de promotion (3.4) dung chung
    congr thuc cho group regression, tránh nhân đôi formula."""
    return hashlib.sha256(
        (book_id + "\x00" + drev + "\x00" + candidate_id + "\x00" + group).encode(
            "utf-8"
        )
    ).hexdigest()


def _latest_observation_map(state: State, dictionary_revision_id: str) -> dict:
    """Observation cua source revision MOI NHAT (theo created_at cua revision,
    khong phai rowid — review 3.3: insert thu tu khong phai recency)."""
    row = state.conn.execute(
        "SELECT o.source_revision_id FROM observations o "
        "JOIN source_revisions s ON s.id = o.source_revision_id "
        "WHERE o.dictionary_revision_id=? "
        "ORDER BY s.created_at DESC LIMIT 1",
        (dictionary_revision_id,),
    ).fetchone()
    if row is None:
        return {}
    cur = state.conn.execute(
        "SELECT * FROM observations WHERE source_revision_id=? "
        "AND dictionary_revision_id=?",
        (row[0], dictionary_revision_id),
    )
    return {r["ngram"]: r for r in cursor_dicts(cur)}


def _single_target(cand_row: dict) -> int:
    """Resolver tra dung mot target uu tien (khong ambiguous_parts/notes)."""
    try:
        prov = json.loads(cand_row["provenance_json"])
    except (TypeError, ValueError):
        return 0
    if prov.get("resolver") is None:
        return 0
    no_ambiguous_part = all(
        "ambiguous_parts" not in source.get("info", {})
        for source in prov.get("sources", [])
    )
    return int(no_ambiguous_part and "ambiguous_target" not in prov.get("notes", []))


def evaluate_candidates(
    state: State,
    *,
    book_id: str,
    dictionary: Dictionary,
    dictionary_revision_id: str,
) -> EvidenceSummary:
    """Tinh 6 nhom tin hieu cho moi candidate cua (book, dictionary_revision).

    Formula score (CHI xep hang — AD-7):
    - strength = min_pmi + left_entropy + right_entropy + log2(total_count)
    - stability / benefit = tong tin hieu 0/1; risk = -so rui ro
      (gom target_ambiguity — thiet ke buoc 5).
    """
    cur = state.conn.execute(
        "SELECT * FROM term_candidates WHERE book_id=? AND dictionary_revision_id=?",
        (book_id, dictionary_revision_id),
    )
    candidates = cursor_dicts(cur)
    obs_map = _latest_observation_map(state, dictionary_revision_id)

    def _row(cand: dict, group: str, signals: dict, score: float) -> EvidenceRow:
        return EvidenceRow(
            id=ev_id(book_id, dictionary_revision_id, cand["id"], group),
            candidate_id=cand["id"],
            book_id=book_id,
            dictionary_revision_id=dictionary_revision_id,
            group_name=group,
            signals_json=json.dumps(signals, sort_keys=True),
            score=score,
        )

    rows: list[EvidenceRow] = []
    benefit_positive = 0
    manual_conflicts = 0
    for cand in sorted(candidates, key=lambda c: c["source"]):
        key = cand["source"]
        obs = obs_map.get(key, {})
        total = obs.get("total_count", 0)
        min_pmi = obs.get("min_pmi", 0.0) or 0.0
        left_h = obs.get("left_entropy", 0.0) or 0.0
        right_h = obs.get("right_entropy", 0.0) or 0.0

        rows.append(
            _row(
                cand,
                "strength",
                {
                    "total_count": total,
                    "min_pmi": min_pmi,
                    "left_entropy": left_h,
                    "right_entropy": right_h,
                },
                float(min_pmi + left_h + right_h + math.log2(total) if total else 0.0),
            )
        )

        same_seg = int(not obs.get("alt_segmentation", 0))
        single_target = _single_target(cand)
        rows.append(
            _row(
                cand,
                "stability",
                {"same_segmentation": same_seg, "single_target": single_target},
                float(same_seg + single_target),
            )
        )

        reduces_unknown = int(bool(obs.get("is_unknown", 0)))
        reduces_single = int(bool(obs.get("is_single_char_run", 0)))
        # Fragmentation rieng single_char (review 3.3: het double-count) —
        # alt_segmentation da co nhom stability.
        reduces_frag = reduces_single
        benefit_score = reduces_unknown + reduces_single + reduces_frag
        if benefit_score > 0:
            benefit_positive += 1
        rows.append(
            _row(
                cand,
                "benefit",
                {
                    "reduces_unknown": reduces_unknown,
                    "reduces_single_char": reduces_single,
                    "reduces_fragmentation": reduces_frag,
                },
                float(benefit_score),
            )
        )

        m_conflict = int(_span_manual_conflict(dictionary, key))
        if m_conflict:
            manual_conflicts += 1
        o_existing = int(_overlap_existing(dictionary, key))
        junk = int(bool(obs.get("repetition_unstable", 0)))
        target_ambiguity = 1 - single_target
        rows.append(
            _row(
                cand,
                "risk",
                {
                    "manual_conflict": m_conflict,
                    "overlap_existing": o_existing,
                    "target_ambiguity": target_ambiguity,
                    "junk_likelihood": junk,
                },
                -float(m_conflict + o_existing + target_ambiguity + junk),
            )
        )

        rows.append(
            _row(
                cand,
                "scope",
                {
                    "chapter_count": obs.get("chapter_count", 0),
                    "total_count": total,
                    "books": 1,  # book scope; cross-book la Epic 4
                    "genre": None,  # chua co metadata the loai
                },
                0.0,
            )
        )

        rows.append(
            _row(
                cand,
                "regression",
                # AC 2: khong phu thuoc output — story 3.4 populate sau rerun.
                {"deferred": "story-3.4"},
                0.0,
            )
        )

    state.replace_evidence(book_id, dictionary_revision_id, rows)
    return EvidenceSummary(
        book_id=book_id,
        dictionary_revision_id=dictionary_revision_id,
        candidates=len(candidates),
        evidence_rows=len(rows),
        benefit_positive=benefit_positive,
        manual_conflicts=manual_conflicts,
    )
