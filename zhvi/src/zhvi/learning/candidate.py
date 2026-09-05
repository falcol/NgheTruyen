"""Candidate builder — sinh target chi tu 6 nguon xac dinh (story 3.2).

AD-6: khong dung duoc target don nghia tu 6 nguon thi candidate la
`unresolved` — may khong bao gio bia nghia de tang coverage.
AD-5: candidate trung manual entry bi loai; manual luon thang.
AD-4: builder la pha LEARN, chi doc dictionary.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from zhvi.state import CandidateRow, State
from zhvi.vietphrase.layers import Layer
from zhvi.vietphrase.loader import Dictionary
from zhvi.vietphrase.patterns import fill_target

# Default khoi tao theo spec pipeline-contract [learning] min_name_occurrences;
# CLI learn truyen cfg.learning.min_name_occurrences — day chi la fallback khi
# goi truc tiep (test). Nguong promotion that su thuoc story 3.4.
MIN_OCCURRENCES = 3

_WS_RE = re.compile(r"\s+")
# AC 2 rule dau cau: strip dau cau hai dau (Latin + CJK) — dau cau ben trong
# la phan nghia cua target.
_EDGE_PUNCT = "\"'`!?.,;:()[]<>«»·…—–-，。！？；：、（）《》「」『』"
# Target mo ho (AC 3): lua chon a/b, placeholder, % hay CJK con sot.
_AMBIGUOUS_RE = re.compile(r"[/{}%]|[㐀-䶿一-鿿豈-﫿]")

# Entry = (target, precedence, policy); precedence = (layer, trust, load_index).


@dataclass(frozen=True)
class CandidateSummary:
    book_id: str
    dictionary_revision_id: str
    observations: int
    selected: int
    candidates: int
    unresolved: int
    eligible_auto: int
    skipped_manual: int

    def to_json(self) -> dict:
        return {
            "book_id": self.book_id,
            "dictionary_revision": self.dictionary_revision_id,
            "observations": self.observations,
            "selected": self.selected,
            "candidates": self.candidates,
            "unresolved": self.unresolved,
            "eligible_auto": self.eligible_auto,
            "skipped_manual": self.skipped_manual,
        }


def _trie_entries(dic: Dictionary, key: str) -> list[tuple[str, tuple, str]]:
    """Entries tai dung node key — [] neu key khong ton tai trong trie."""
    node = dic.root
    for ch in key:
        node = node.children.get(ch)
        if node is None:
            return []
    return list(node.entries)


def _entry_layer(entry: tuple[str, tuple, str]) -> int:
    """Layer cua entry tuple trie (precedence[0])."""
    return entry[1][0]


def _distinct_targets(entries: list[tuple[str, tuple, str]]) -> list[str]:
    """Cac target khac nhau, uu tien giam dan theo precedence."""
    ordered = sorted(entries, key=lambda e: e[1], reverse=True)
    seen: list[str] = []
    for target, _, _ in ordered:
        if target not in seen:
            seen.append(target)
    return seen


def _manual_conflict(dic: Dictionary, key: str) -> bool:
    """AD-5: key da co entry lop manual (GLOBAL_MANUAL tro len) — bo candidate."""
    return any(
        _entry_layer(e) >= Layer.GLOBAL_MANUAL for e in _trie_entries(dic, key)
    )


def _resolve_lower_layer(
    dic: Dictionary, key: str
) -> tuple[str, dict] | None:
    """Nguon 1: entry da ton tai cho dung key (moi lop auto/base).

    Review 3.2: bao gom BASE_MULTI — key da co entry dict chinh phai giu
    target do (phien am/ghep khong duoc de). Pre-check da lo manual; con lai
    auto/base: lay target cua entry precedence cao nhat.
    """
    entries = _trie_entries(dic, key)
    if not entries:
        return None
    top = max(entries, key=lambda e: e[1])
    return top[0], {"layer": _entry_layer(top)}


def _resolve_compound(dic: Dictionary, key: str) -> tuple[str, dict] | None:
    """Nguon 2: ghep longest-match cac entry con — moi doan phai co entry.

    AC 4: neu mot entry con co nhieu hon mot target uu tien khac nhau thi
    candidate van build nhung eligible_auto = 0.
    """
    parts: list[str] = []
    ambiguous_parts: list[str] = []
    pos = 0
    while pos < len(key):
        matched = False
        for end in range(len(key), pos, -1):
            targets = _distinct_targets(_trie_entries(dic, key[pos:end]))
            if targets:
                parts.append(targets[0])
                if len(targets) > 1:
                    ambiguous_parts.append(key[pos:end])
                pos = end
                matched = True
                break
        if not matched:
            return None
    info: dict = {"compound": True}
    if ambiguous_parts:
        info["ambiguous_parts"] = ambiguous_parts
    return " ".join(parts), info


def _resolve_phien_am(dic: Dictionary, key: str) -> tuple[str, dict] | None:
    """Nguon 3: phien am Han-Viet tung ky tu (BASE_SINGLE) cho ten rieng."""
    parts: list[str] = []
    for ch in key:
        singles = [
            e
            for e in _trie_entries(dic, ch)
            if _entry_layer(e) == Layer.BASE_SINGLE and e[0]
        ]
        if not singles:
            return None
        parts.append(_distinct_targets(singles)[0])
    return " ".join(parts), {"phien_am": True}


def _resolve_template(dic: Dictionary, key: str) -> tuple[str, dict] | None:
    """Nguon 4: template rule LuatNhan khop toan bo key."""

    def _translate(span: str) -> str:
        targets = _distinct_targets(_trie_entries(dic, span))
        # Span khong co entry: tra nguyen CJK — se bi _AMBIGUOUS_RE danh
        # eligible_auto=0 (AD-6 an toan: khong bia nghia tu template).
        return targets[0] if targets else span

    for rules in dic.patterns.values():
        for rule in rules:
            match = rule.regex.fullmatch(key)
            if match is None:
                continue
            target = _normalize_target(fill_target(rule, match, _translate))
            if target:
                return target, {"template": rule.key}
    return None


def _normalize_target(target: str) -> str:
    """AC 2: collapse khoang trang + strip dau cau hai dau."""
    collapsed = _WS_RE.sub(" ", target).strip()
    return collapsed.strip(_EDGE_PUNCT).strip()


def _cand_id(book_id: str, drev: str, key: str) -> str:
    """Content-addressed (khong phai event) — deterministic khi rebuild."""
    return hashlib.sha256(
        (book_id + "\x00" + drev + "\x00" + key).encode("utf-8")
    ).hexdigest()


def _has_learning_signal(obs: dict) -> bool:
    return bool(
        obs["is_single_char_run"]
        or obs["is_unknown"]
        or obs["alt_segmentation"]
        or obs["repetition_unstable"]
        or obs["pattern_hits_json"] != "[]"
    )


def build_candidates(
    state: State,
    *,
    book_id: str,
    dictionary: Dictionary,
    dictionary_revision_id: str,
    source_revision_id: str,
    min_occurrences: int = MIN_OCCURRENCES,
) -> CandidateSummary:
    """Doc observations co tin hieu hoc, sinh candidate tu 6 nguon (AD-6).

    Resolver chay theo thu tu uu tien co dinh; target lay tu resolver dau
    tien tra != None; moi nguon tim thay deu ghi provenance.
    """
    cur = state.conn.execute(
        "SELECT * FROM observations WHERE source_revision_id=? "
        "AND dictionary_revision_id=?",
        (source_revision_id, dictionary_revision_id),
    )
    cols = [d[0] for d in cur.description]
    observations = [dict(zip(cols, r)) for r in cur.fetchall()]
    selected = sorted(
        (
            o
            for o in observations
            if _has_learning_signal(o) and o["total_count"] >= min_occurrences
        ),
        key=lambda o: o["ngram"],
    )

    rows: list[CandidateRow] = []
    skipped_manual = 0
    unresolved = 0
    eligible = 0
    for obs in selected:
        key = obs["ngram"]
        if _manual_conflict(dictionary, key):
            skipped_manual += 1
            continue
        pattern_hits = json.loads(obs["pattern_hits_json"])
        is_name = "person" in pattern_hits

        # Thu tu uu tien co dinh (deterministic): lop thap -> phien am (chi
        # ten rieng — dang tin cay hon ghep entry chung) -> ghep -> template.
        # Nguon 5/6 chua co data source that.
        attempts: list[tuple[str, tuple[str, dict] | None]] = [
            ("lower_layer", _resolve_lower_layer(dictionary, key)),
        ]
        if is_name:
            attempts.append(
                ("phien_am", _resolve_phien_am(dictionary, key))
            )
        attempts.append(("compound", _resolve_compound(dictionary, key)))
        attempts.append(
            ("template", _resolve_template(dictionary, key))
        )
        notes = [
            # [Note] Nguon 5 (correction/glossary nguoi dung chua trung key):
            # chua co flow ghi feedback_events — pending, khong bia nguon.
            "user: pending-feedback-events",
            # [Note] Nguon 6 (target accept o truyen khac): can registry Epic 4.
            "accepted_elsewhere: deferred-registry",
        ]
        found = [
            (name, res) for name, res in attempts if res is not None
        ]
        if not found:
            unresolved += 1
            rows.append(
                CandidateRow(
                    id=_cand_id(book_id, dictionary_revision_id, key),
                    book_id=book_id,
                    source=key,
                    proposed_target="",
                    kind="name" if is_name else "term",
                    status="unresolved",
                    provenance_json=json.dumps(
                        {
                            "original": obs["ngram_original"],
                            "resolver": None,
                            "sources": [],
                            "notes": notes,
                        },
                        sort_keys=True,
                    ),
                    dictionary_revision_id=dictionary_revision_id,
                    eligible_auto=0,
                )
            )
            continue

        resolver, (target, info) = found[0]
        target = _normalize_target(target)
        ambiguous = bool(_AMBIGUOUS_RE.search(target)) or bool(
            info.get("ambiguous_parts")
        )
        if ambiguous:
            notes.append("ambiguous_target")
        if not ambiguous:
            eligible += 1
        rows.append(
            CandidateRow(
                id=_cand_id(book_id, dictionary_revision_id, key),
                book_id=book_id,
                source=key,
                proposed_target=target,
                kind=(
                    "name"
                    if is_name
                    else ("pattern" if resolver == "template" else "term")
                ),
                status="candidate",
                provenance_json=json.dumps(
                    {
                        "original": obs["ngram_original"],
                        "resolver": resolver,
                        "sources": [
                            {"name": name, "info": res[1]}
                            for name, res in found
                        ],
                        "notes": notes,
                    },
                    sort_keys=True,
                ),
                dictionary_revision_id=dictionary_revision_id,
                eligible_auto=int(not ambiguous),
            )
        )

    state.replace_candidates(book_id, dictionary_revision_id, rows)
    return CandidateSummary(
        book_id=book_id,
        dictionary_revision_id=dictionary_revision_id,
        observations=len(observations),
        selected=len(selected),
        candidates=len(rows) - unresolved,
        unresolved=unresolved,
        eligible_auto=eligible,
        skipped_manual=skipped_manual,
    )
