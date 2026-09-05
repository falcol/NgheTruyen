"""Book-auto promotion qua hard gates (story 3.4, AD-7/AD-20).

Candidate chi promote len BOOK_AUTO khi pass TOAN BO gates tu evidence
(diem cao khong bu du — AD-7): nguong occurrence/chapter (config), target stability
100%, khong manual conflict, benefit duong; sau do isolation check tren
revision dry-run (block doi dung tap chua key + structural invariant pass)
moi publish CAS (AD-15). Revoke la revision MOI chi bo key (AD-12).

Moi mutation candidate ghi event append-only promotion_events (AC 1 / AD-8).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from zhvi.config import Config
from zhvi.correction import affected_block_ids
from zhvi.document import parse_document
from zhvi.export import node_block_id
from zhvi.learning.evidence import ev_id
from zhvi.project import Project
from zhvi.projection import read_bundle_entries
from zhvi.qa import sanitize_source
from zhvi.quality.invariants import run_invariants
from zhvi.revision import (
    AutoEntry,
    build_revision,
    load_revision_dictionary,
    publish_revision,
)
from zhvi.state import EvidenceRow, PromotionEventRow, State, cursor_dicts
from zhvi.vietphrase.layers import Layer
from zhvi.vietphrase.loader import Dictionary
from zhvi.vietphrase.lattice import vp_plan

__all__ = [
    "GateResult", "IsolationResult", "PromotionError", "PromotionSummary",
    "evaluate_gates", "run_promotion", "revoke_book_auto",
]


class PromotionError(RuntimeError):
    """Promotion/revoke that bai (khong active revision, khong co entry...) —
    convention src/: domain error la RuntimeError subclass."""


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class IsolationResult:
    passed: bool
    isolated: bool
    changed_block_ids: list[str]
    invariant_errors: list[str]
    note: str = ""
    doc: object | None = None  # parse lai dung cho regression evidence
    baseline_run_id: str = ""


@dataclass(frozen=True)
class PromotionSummary:
    book_id: str
    promoted: int
    rejected: int
    skipped: int
    revision_before: str | None
    revision_after: str | None
    changed_blocks: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "book_id": self.book_id,
            "promoted": self.promoted,
            "rejected": self.rejected,
            "skipped": self.skipped,
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "changed_blocks": self.changed_blocks,
        }


def _evidence_map(
    state: State, book_id: str, dictionary_revision_id: str
) -> dict[str, dict[str, dict]]:
    """candidate_id -> {group_name: signals} (signals da parse JSON)."""
    cur = state.conn.execute(
        "SELECT candidate_id, group_name, signals_json FROM candidate_evidence "
        "WHERE book_id=? AND dictionary_revision_id=?",
        (book_id, dictionary_revision_id),
    )
    out: dict[str, dict[str, dict]] = {}
    for cand_id, group, signals_json in cur.fetchall():
        out.setdefault(cand_id, {})[group] = json.loads(signals_json)
    return out


def evaluate_gates(ev: dict[str, dict], cfg: Config) -> list[GateResult]:
    """4 hard gates tu evidence signals (AD-7: diem khong tham gia)."""
    learn = cfg.learning
    strength = ev.get("strength", {})
    scope = ev.get("scope", {})
    stability = ev.get("stability", {})
    risk = ev.get("risk", {})
    benefit = ev.get("benefit", {})
    total = strength.get("total_count", 0)
    chapters = scope.get("chapter_count", 0)
    return [
        GateResult(
            "min_occurrences",
            total >= learn.min_term_occurrences and chapters >= learn.min_chapters,
            f"total={total}/min={learn.min_term_occurrences}, "
            f"chapters={chapters}/min={learn.min_chapters}",
        ),
        GateResult(
            "target_stability",
            stability.get("single_target", 0) == 1
            and stability.get("same_segmentation", 0) == 1,
            f"single_target={stability.get('single_target')}, "
            f"same_segmentation={stability.get('same_segmentation')}",
        ),
        GateResult(
            "no_manual_conflict",
            risk.get("manual_conflict", 1) == 0,
            f"manual_conflict={risk.get('manual_conflict')}",
        ),
        GateResult(
            "benefit_positive",
            benefit.get("reduces_unknown", 0)
            + benefit.get("reduces_single_char", 0)
            + benefit.get("reduces_fragmentation", 0)
            > 0,
            f"benefit={benefit}",
        ),
    ]


def _current_auto_entries(project: Project, revision_id: str | None) -> list[AutoEntry]:
    """Auto entries book hien co cua active revision (doc tu bundle pin)."""
    if revision_id is None:
        return []
    out: dict[str, AutoEntry] = {}
    for parts in read_bundle_entries(project, revision_id):
        if len(parts) >= 4 and parts[0] == str(int(Layer.BOOK_AUTO)) and parts[1] == "book":
            out[parts[2]] = AutoEntry(source=parts[2], target=parts[3], scope="book")
    return sorted(out.values(), key=lambda a: a.source)


def _event(
    *,
    book_id: str,
    candidate_id: str,
    source: str,
    event_type: str,
    from_status: str,
    to_status: str,
    drev: str,
    revision_id: str,
    provenance: dict,
) -> PromotionEventRow:
    return PromotionEventRow(
        id=uuid.uuid4().hex,
        book_id=book_id,
        candidate_id=candidate_id,
        source=source,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor="system",
        dictionary_revision_id=drev,
        revision_id=revision_id,
        provenance_json=json.dumps(provenance, sort_keys=True, ensure_ascii=False),
    )


def _isolation_check(
    state: State,
    *,
    project: Project,
    cfg: Config,
    dic_new: Dictionary,
    keys: set[str],
) -> IsolationResult:
    """Render lai moi block voi dictionary moi; block doi phai thuoc tap
    chua key (AC 3) + structural invariant cho moi block doi HOAC chua co
    baseline (AD-20 — invariant la hard gate, khong duoc bo khi chua translate)."""
    rev = state.latest_source_revision()
    if rev is None:
        return IsolationResult(False, False, [], [], "no_source")
    text = Path(rev.snapshot_path).read_text(encoding=rev.encoding)
    doc = parse_document(
        text, chapter_detection=cfg.chapter_detection, chapter_regex=cfg.chapter_regex
    )
    affected = set(affected_block_ids(doc, keys, dic_new.trad_simp))
    baseline_run = state.latest_completed_run_for_source(rev.id)
    baseline = state.committed_blocks(baseline_run.id) if baseline_run else {}

    changed: list[str] = []
    inv_errors: list[str] = []
    for node in doc.translatable_nodes():
        bid = node_block_id(node)
        vp_input, _junk = (
            sanitize_source(node.content) if cfg.qa_strip_junk else (node.content, [])
        )
        draft = vp_plan(
            dic_new,
            vp_input,
            beam=cfg.lattice_beam,
            occurrence_prefix=bid,
            collapse_reps=cfg.collapse_repetitions,
        )
        old = baseline.get(bid)
        text_changed = old is not None and old["final_text"] != draft.text
        if text_changed:
            changed.append(bid)
        if text_changed or old is None:
            # AD-20: invariant cho block doi + block chua co baseline.
            inv = run_invariants(source=vp_input, output=draft.text, block_id=bid)
            if not inv.ok:
                inv_errors.extend(inv.errors)
    isolated = all(bid in affected for bid in changed)
    note = "" if baseline else "no_baseline"
    return IsolationResult(
        passed=isolated and not inv_errors,
        isolated=isolated,
        changed_block_ids=sorted(changed),
        invariant_errors=inv_errors,
        note=note,
        doc=doc,
        baseline_run_id=baseline_run.id if baseline_run else "",
    )


def run_promotion(
    state: State,
    *,
    project: Project,
    dict_dir: Path,
    cfg: Config,
    dictionary_revision_id: str,
) -> PromotionSummary:
    """Danh gia gates cho moi candidate (book, drev) roi promote tap pass.

    Reject ghi event ngay; promote phai cho isolation pass tren revision
    dry-run moi publish CAS (AD-15) + events + regression evidence.
    """
    book_id = project.book_id
    drev = dictionary_revision_id
    cur = state.conn.execute(
        "SELECT * FROM term_candidates WHERE book_id=? AND dictionary_revision_id=?",
        (book_id, drev),
    )
    candidates = cursor_dicts(cur)
    active = state.active_revision_id("book", book_id)
    autos = _current_auto_entries(project, active)
    auto_targets = {a.source: a.target for a in autos}
    ev_map = _evidence_map(state, book_id, drev)

    rejected = 0
    skipped = 0
    to_promote: list[tuple[dict, list[GateResult]]] = []
    # Event log la nguon chan idempotency (status bi replace_candidates reset
    # khi chay lai composite learn cung drev):
    # - rejected cung drev -> khong lap lai event (evidence deterministic).
    # - revoked (bat ky drev) -> revoke ben vung, khong tu dong promote lai.
    prior = state.conn.execute(
        "SELECT DISTINCT source, dictionary_revision_id, event_type "
        "FROM promotion_events WHERE book_id=?",
        (book_id,),
    ).fetchall()
    rejected_here = {s for s, d, t in prior if t == "rejected" and d == drev}
    revoked_keys = {s for s, _d, t in prior if t == "revoked"}
    for cand in sorted(candidates, key=lambda c: c["source"]):
        if auto_targets.get(cand["source"]) == cand["proposed_target"]:
            skipped += 1  # idempotency: da promoted trong active revision
            continue
        if cand["source"] in revoked_keys:
            skipped += 1  # revoke la quyet dinh ben vung (user/may) — 3.5 accept lai
            continue
        if cand["source"] in rejected_here:
            state.update_candidate_status(cand["id"], "rejected")
            skipped += 1
            continue
        if cand["status"] != "candidate" or not cand["eligible_auto"]:
            continue  # unresolved — khong duoc danh gia
        gates = evaluate_gates(ev_map.get(cand["id"], {}), cfg)
        if all(g.passed for g in gates):
            to_promote.append((cand, gates))
        else:
            state.append_promotion_event(
                _event(
                    book_id=book_id,
                    candidate_id=cand["id"],
                    source=cand["source"],
                    event_type="rejected",
                    from_status="candidate",
                    to_status="rejected",
                    drev=drev,
                    revision_id="",
                    provenance={
                        "gates": [
                            {"name": g.name, "passed": g.passed, "detail": g.detail}
                            for g in gates
                        ]
                    },
                )
            )
            state.update_candidate_status(cand["id"], "rejected")
            rejected += 1

    if not to_promote:
        return PromotionSummary(
            book_id, 0, rejected, skipped, active, active
        )

    keys = {cand["source"] for cand, _g in to_promote}
    # Replace theo key: auto entry cu cung key (target khac) bi de — neu giu
    # ca hai se BuildError conflict cung scope/layer.
    new_autos = [a for a in autos if a.source not in keys] + [
        AutoEntry(source=cand["source"], target=cand["proposed_target"], scope="book")
        for cand, _g in to_promote
    ]
    bundle = build_revision(dict_dir, project, new_autos)
    dic_new = load_revision_dictionary(project, bundle.revision_id)
    iso = _isolation_check(state, project=project, cfg=cfg, dic_new=dic_new, keys=keys)

    if not iso.passed:
        # AC 2: fail mot muc (isolation/invariant) la reject ca tap — diem khong bu.
        iso_gates = [
            GateResult("isolation", iso.isolated, f"changed={iso.changed_block_ids}"),
            GateResult(
                "structural_invariant",
                not iso.invariant_errors,
                f"errors={iso.invariant_errors[:5]}",
            ),
        ]
        for cand, gates in to_promote:
            state.append_promotion_event(
                _event(
                    book_id=book_id,
                    candidate_id=cand["id"],
                    source=cand["source"],
                    event_type="rejected",
                    from_status="candidate",
                    to_status="rejected",
                    drev=drev,
                    revision_id="",
                    provenance={
                        "gates": [
                            {"name": g.name, "passed": g.passed, "detail": g.detail}
                            for g in [*gates, *iso_gates]
                        ],
                        "isolation": {
                            "changed_blocks": iso.changed_block_ids,
                            "invariant_errors": iso.invariant_errors,
                            "note": iso.note,
                        },
                    },
                )
            )
            state.update_candidate_status(cand["id"], "rejected")
            rejected += 1
        return PromotionSummary(book_id, 0, rejected, skipped, active, active)

    result = publish_revision(
        dict_dir, project, new_autos, expected_active=active
    )
    # Regression evidence (that cho 3.3 deferred) — reuse doc/baseline tu
    # isolation check, khong parse lai lan hai.
    reg_rows = []
    for cand, gates in to_promote:
        state.append_promotion_event(
            _event(
                book_id=book_id,
                candidate_id=cand["id"],
                source=cand["source"],
                event_type="promoted",
                from_status="candidate",
                to_status="book_auto",
                drev=drev,
                revision_id=result.revision_id,
                provenance={
                    "gates": [
                        {"name": g.name, "passed": g.passed, "detail": g.detail}
                        for g in gates
                    ],
                    "isolation": {
                        "changed_blocks": iso.changed_block_ids,
                        "note": iso.note,
                    },
                },
            )
        )
        state.update_candidate_status(cand["id"], "book_auto")
        reg_rows.append(
            EvidenceRow(
                id=ev_id(book_id, drev, cand["id"], "regression"),
                candidate_id=cand["id"],
                book_id=book_id,
                dictionary_revision_id=drev,
                group_name="regression",
                signals_json=json.dumps(
                    {
                        "changed_blocks": len(iso.changed_block_ids),
                        "affected_blocks": len(
                            affected_block_ids(
                                iso.doc, {cand["source"]}, dic_new.trad_simp
                            )
                        ),
                        "invariant_errors": len(iso.invariant_errors),
                        "structural_invariant_pass": int(not iso.invariant_errors),
                        "isolation_pass": 1,
                        "baseline_run": iso.baseline_run_id,
                    },
                    sort_keys=True,
                ),
                score=0.0,
            )
        )
    state.replace_evidence_group(book_id, drev, "regression", reg_rows)
    return PromotionSummary(
        book_id,
        promoted=len(to_promote),
        rejected=rejected,
        skipped=skipped,
        revision_before=active,
        revision_after=result.revision_id,
        changed_blocks=iso.changed_block_ids,
    )


def revoke_book_auto(
    state: State, *, project: Project, dict_dir: Path, source: str
) -> str:
    """Bo mot book-auto entry khoi active revision (AC 4 / AD-12): build
    revision MOI khong co key, chi affected blocks doi; event revoked."""
    book_id = project.book_id
    active = state.active_revision_id("book", book_id)
    if active is None:
        raise PromotionError("Project chua co active revision")
    autos = _current_auto_entries(project, active)
    kept = [a for a in autos if a.source != source]
    if len(kept) == len(autos):
        raise PromotionError(
            f"Khong co book-auto entry {source!r} trong active revision"
        )

    old_autos = {a.source: a.target for a in autos}
    # Tap entry = active tru dung key -> revision moi chi khac o key nay
    # (content-addressed dam bao).
    result = publish_revision(dict_dir, project, kept, expected_active=active)

    cur = state.conn.execute(
        "SELECT * FROM term_candidates WHERE book_id=? AND source=? "
        "ORDER BY rowid DESC",
        (book_id, source),
    )
    cands = cursor_dicts(cur)
    revoked_any = False
    for cand in cands:
        if cand["status"] != "book_auto":
            continue
        state.append_promotion_event(
            _event(
                book_id=book_id,
                candidate_id=cand["id"],
                source=source,
                event_type="revoked",
                from_status="book_auto",
                to_status="revoked",
                drev=cand["dictionary_revision_id"],
                revision_id=result.revision_id,
                provenance={"target": old_autos[source]},
            )
        )
        state.update_candidate_status(cand["id"], "revoked")
        revoked_any = True
    if not revoked_any:
        # Khong tim thay row candidate book_auto (reset boi replace_candidates
        # hoac promote boi version cu) — van ghi event de lich su revision
        # duoc truy ve (AD-8: moi mutation phai co event).
        state.append_promotion_event(
            _event(
                book_id=book_id,
                candidate_id="",
                source=source,
                event_type="revoked",
                from_status="book_auto",
                to_status="revoked",
                drev="",
                revision_id=result.revision_id,
                provenance={"target": old_autos[source]},
            )
        )
    return result.revision_id
