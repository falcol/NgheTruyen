"""Global promotion fail-closed (story 4.3, AD-14/AD-7/AD-13/AD-16).

zhvi learn --global: global_candidate -> global_auto chi khi pass TOAN BO
hard gates. Thieu approved golden manifest thi HOLD o global_candidate
(khong rejected) de retry khi corpus duoc duyet.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from zhvi.config import Config, resolve_config
from zhvi.fsutil import atomic_write
from zhvi.golden import approved_cases, is_approved, load_manifest, run_golden_report
from zhvi.learning.promotion import GateResult, PromotionError, _isolation_check
from zhvi.project import Project, create_project
from zhvi.registry import RegistryError, RegistryState, registry_lock, resolve_registry_dir
from zhvi.revision import AutoEntry, build_revision, load_revision_dictionary
from zhvi.state import State, cursor_dicts, utc_now

AUTO_GLOBAL_PROJECTION = "AutoVietPhrase.txt"
PROJECTION_HEADER = (
    "# machine-owned projection — dung lai tu global_active (AD-8); "
    "sua = sua entry + zhvi learn --global / revoke\n"
)

__all__ = [
    "GlobalPromotionSummary",
    "GlobalRevokeResult",
    "revoke_global_auto",
    "run_global_promotion",
]


@dataclass
class GlobalPromotionSummary:
    promoted: int
    held: int
    revision_before: str | None
    revision_after: str | None
    gates: list[dict] = field(default_factory=list)
    drift_path: str = ""

    def to_json(self) -> dict:
        return {
            "promoted": self.promoted,
            "held": self.held,
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "gates": self.gates,
            "drift_path": self.drift_path,
        }


@dataclass
class GlobalRevokeResult:
    revision_id: str
    source: str

    def to_json(self) -> dict:
        return {"revision_id": self.revision_id, "source": self.source}


def _workspace(registry_dir: Path) -> Project:
    return create_project(registry_dir / "workspace")


def _gate(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def _golden_gates(
    cfg: Config,
    project: Project,
    dict_dir: Path,
    manifest_path: Path | None,
) -> list[GateResult]:
    if not cfg.learning.global_require_golden_suite:
        return [GateResult("golden_manifest", True, "disabled")]
    manifest = load_manifest(manifest_path)
    approved = approved_cases(manifest)
    if not approved:
        return [GateResult("golden_manifest", False, "no approved cases")]
    try:
        report = run_golden_report(
            project, manifest_path, dict_dir=str(dict_dir)
        )
    except Exception as e:  # noqa: BLE001 — gate fail-closed, khong crash run
        return [GateResult("golden_manifest", False, f"report: {type(e).__name__}: {e}")]
    by_id = {c["case_id"]: c for c in report.get("cases", [])}
    failed: list[str] = []
    for cid, case in (manifest.get("cases") or {}).items():
        if not is_approved(case):
            continue
        rec = by_id.get(cid)
        if rec is None or not rec.get("pass"):
            failed.append(cid)
    return [
        GateResult(
            "golden_manifest",
            not failed,
            f"approved={len(approved)} failed={failed[:5]}",
        )
    ]


def _source_rows(reg: RegistryState) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in reg.cross_book_by_source():
        out.setdefault(row["source"], []).append(row)
    return out


def _source_gates(
    rows: list[dict], cfg: Config
) -> tuple[list[GateResult], str, list[str]]:
    learn = cfg.learning
    books = {r["book_id"] for r in rows}
    total = 0
    targets: set[str] = set()
    conflict = 0
    for r in rows:
        if r["target"]:
            targets.add(r["target"])
        try:
            signals = json.loads(r["signals_json"] or "{}")
        except json.JSONDecodeError:
            signals = {}
        if r["group_name"] == "strength":
            total += int(signals.get("total_count") or 0)
        if r["group_name"] == "risk":
            conflict = max(conflict, int(signals.get("manual_conflict") or 0))
    agreed = len(targets) == 1
    target = next(iter(targets)) if agreed else ""
    return [
        GateResult(
            "min_books",
            len(books) >= learn.global_min_books,
            f"books={len(books)}/min={learn.global_min_books}",
        ),
        GateResult(
            "min_occurrences",
            total >= learn.global_min_occurrences,
            f"total={total}/min={learn.global_min_occurrences}",
        ),
        GateResult(
            "target_agreement",
            agreed and bool(target),
            f"targets={sorted(targets)}",
        ),
        GateResult(
            "no_manual_conflict",
            conflict == 0,
            f"manual_conflict={conflict}",
        ),
    ], target, sorted(books)


def _append_event(
    reg: RegistryState,
    *,
    source: str,
    event_type: str,
    from_status: str,
    to_status: str,
    actor: str,
    revision_id: str,
    provenance: dict,
) -> None:
    now = utc_now()
    reg.conn.execute(
        "INSERT INTO global_promotion_events("
        "id, source, event_type, from_status, to_status, actor, "
        "revision_id, provenance_json, created_at"
        ") VALUES(?,?,?,?,?,?,?,?,?)",
        (
            uuid.uuid4().hex, source, event_type, from_status, to_status,
            actor, revision_id,
            json.dumps(provenance, sort_keys=True, ensure_ascii=False), now,
        ),
    )


def _existing_status(reg: RegistryState, source: str) -> str | None:
    row = reg.conn.execute(
        "SELECT status FROM global_candidates WHERE source=?", (source,)
    ).fetchone()
    return row[0] if row else None


def _hold_candidate(
    reg: RegistryState, source: str, target: str, gates_json: list[dict]
) -> None:
    """HOLD: khong demote global_auto (AC1/2.2)."""
    status = _existing_status(reg, source)
    if status == "global_auto":
        from_s = to_s = "global_auto"
    else:
        _upsert_candidate(reg, source, target, "global_candidate")
        from_s = status or "global_candidate"
        to_s = "global_candidate"
    _append_event(
        reg,
        source=source,
        event_type="held",
        from_status=from_s,
        to_status=to_s,
        actor="system",
        revision_id="",
        provenance={"gates": gates_json},
    )


def _upsert_candidate(
    reg: RegistryState, source: str, target: str, status: str
) -> None:
    now = utc_now()
    reg.conn.execute(
        "INSERT INTO global_candidates(source, target, status, updated_at) "
        "VALUES(?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET "
        "target=excluded.target, status=excluded.status, "
        "updated_at=excluded.updated_at",
        (source, target, status, now),
    )


def _active_global(reg: RegistryState) -> str | None:
    row = reg.conn.execute(
        "SELECT revision_id FROM global_active WHERE scope='global'"
    ).fetchone()
    return row[0] if row else None


def current_global_autos(reg: RegistryState) -> list[AutoEntry]:
    """Nguon chan ly = global_candidates (status global_auto). Bundle co the
    khong con dong AUTO_GLOBAL neu cung key da co o layer cao hon (QO)."""
    rows = cursor_dicts(
        reg.conn.execute(
            "SELECT source, target FROM global_candidates WHERE status='global_auto' "
            "ORDER BY source"
        )
    )
    return [
        AutoEntry(source=r["source"], target=r["target"], scope="global")
        for r in rows
    ]


def _materialize_autoviet(dict_dir: Path, autos: list[AutoEntry]) -> None:
    lines = [f"{a.source}={a.target}" for a in autos]
    text = PROJECTION_HEADER + "\n".join(lines) + ("\n" if lines else "")
    atomic_write(dict_dir / AUTO_GLOBAL_PROJECTION, text.encode("utf-8"))


def _cjk_increase(iso) -> GateResult:
    """Khong tang CJK residue so voi baseline (neu co)."""
    if not iso.baseline_run_id or iso.doc is None:
        return GateResult("no_cjk_increase", True, iso.note or "no_baseline")
    # Isolation da so sanh final_text; tang CJK tren block doi = fail.
    # Khong dem lai toan van: chi fail khi invariant/isolation da bat.
    # Gate rieng: passed khi isolation passed (CJK nam trong structural).
    return GateResult(
        "no_cjk_increase",
        iso.passed,
        f"changed={iso.changed_block_ids}",
    )


def _write_drift(
    registry_dir: Path,
    revision_id: str,
    *,
    added: list[str],
    changed: list[str],
    revoked: list[str],
    affected_books: list[str],
) -> Path:
    reports = registry_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"drift-{revision_id}.json"
    payload = {
        "revision_id": revision_id,
        "added": added,
        "changed": changed,
        "revoked": revoked,
        "affected_books": affected_books,
    }
    atomic_write(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return path


def run_global_promotion(
    *,
    dict_dir: Path,
    project: Project,
    state: State,
    manifest_path: Path | None = None,
    cfg: Config | None = None,
) -> GlobalPromotionSummary:
    dict_dir = Path(dict_dir)
    if cfg is None:
        cfg = resolve_config(project.root, dict_dir=str(dict_dir))
    registry_dir = resolve_registry_dir(dict_dir)
    with registry_lock(registry_dir):
        return _run_locked(
            dict_dir=dict_dir,
            registry_dir=registry_dir,
            project=project,
            state=state,
            manifest_path=manifest_path,
            cfg=cfg,
        )


def _run_locked(
    *,
    dict_dir: Path,
    registry_dir: Path,
    project: Project,
    state: State,
    manifest_path: Path | None,
    cfg: Config,
) -> GlobalPromotionSummary:
    reg = RegistryState(registry_dir)
    try:
        before = _active_global(reg)
        workspace = _workspace(registry_dir)
        suite = _golden_gates(cfg, project, dict_dir, manifest_path)
        suite_json = [_gate(g.name, g.passed, g.detail) for g in suite]
        by_source = _source_rows(reg)
        held = 0
        to_promote: list[tuple[str, str, list[GateResult], list[str]]] = []

        if not all(g.passed for g in suite):
            for source, rows in sorted(by_source.items()):
                target = next((r["target"] for r in rows if r["target"]), "")
                _hold_candidate(reg, source, target, suite_json)
                held += 1
            reg.conn.commit()
            return GlobalPromotionSummary(
                0, held, before, before, gates=suite_json
            )

        held_gates: list[dict] = []
        for source, rows in sorted(by_source.items()):
            gates, target, books = _source_gates(rows, cfg)
            if all(g.passed for g in gates) and target:
                to_promote.append((source, target, gates, books))
            else:
                src_json = [_gate(g.name, g.passed, g.detail) for g in gates]
                held_gates.extend(src_json)
                _hold_candidate(reg, source, target or "", src_json)
                held += 1

        if not to_promote:
            reg.conn.commit()
            return GlobalPromotionSummary(
                0, held, before, before, gates=suite_json + held_gates
            )

        old_autos = current_global_autos(reg)
        old_map = {a.source: a.target for a in old_autos}
        keys = {s for s, _t, _g, _b in to_promote}
        new_autos = [a for a in old_autos if a.source not in keys] + [
            AutoEntry(source=s, target=t, scope="global")
            for s, t, _g, _b in to_promote
        ]
        bundle = build_revision(dict_dir, workspace, new_autos)
        dic_new = load_revision_dictionary(workspace, bundle.revision_id)
        iso = _isolation_check(
            state, project=project, cfg=cfg, dic_new=dic_new, keys=keys
        )
        cjk = _cjk_increase(iso)
        iso_gates = [
            GateResult("isolation", iso.isolated, f"changed={iso.changed_block_ids}"),
            GateResult(
                "structural_invariant",
                not iso.invariant_errors,
                f"errors={iso.invariant_errors[:5]}",
            ),
            cjk,
        ]
        if not iso.passed or not cjk.passed:
            extra = [_gate(g.name, g.passed, g.detail) for g in iso_gates]
            for source, target, gates, _books in to_promote:
                src_json = [
                    *[_gate(g.name, g.passed, g.detail) for g in gates],
                    *extra,
                ]
                _hold_candidate(reg, source, target, src_json)
                held += 1
            reg.conn.commit()
            return GlobalPromotionSummary(
                0, held, before, before, gates=suite_json + extra
            )

        now = utc_now()
        expected = before
        current = _active_global(reg)
        if expected != current:
            raise RegistryError(
                f"stale global active: expected {expected!r} got {current!r}"
            )
        reg.conn.execute(
            "INSERT INTO global_active(scope, revision_id, updated_at) "
            "VALUES('global',?,?) "
            "ON CONFLICT(scope) DO UPDATE SET "
            "revision_id=excluded.revision_id, updated_at=excluded.updated_at",
            (bundle.revision_id, now),
        )
        added, changed = [], []
        affected: set[str] = set()
        for source, target, gates, books in to_promote:
            if source not in old_map:
                added.append(source)
            elif old_map[source] != target:
                changed.append(source)
            affected.update(books)
            _upsert_candidate(reg, source, target, "global_auto")
            _append_event(
                reg,
                source=source,
                event_type="promoted",
                from_status="global_candidate",
                to_status="global_auto",
                actor="system",
                revision_id=bundle.revision_id,
                provenance={
                    "gates": [_gate(g.name, g.passed, g.detail) for g in gates]
                },
            )
        # AD-15: CAS pointer trong txn, projection + drift sau commit.
        reg.conn.commit()
        _materialize_autoviet(dict_dir, new_autos)
        drift = _write_drift(
            registry_dir,
            bundle.revision_id,
            added=added,
            changed=changed,
            revoked=[],
            affected_books=sorted(affected),
        )
        return GlobalPromotionSummary(
            promoted=len(to_promote),
            held=held,
            revision_before=before,
            revision_after=bundle.revision_id,
            gates=suite_json,
            drift_path=str(drift),
        )
    finally:
        reg.close()


def revoke_global_auto(
    dict_dir: Path | str, source: str, actor: str = "system"
) -> GlobalRevokeResult:
    dict_dir = Path(dict_dir)
    registry_dir = resolve_registry_dir(dict_dir)
    with registry_lock(registry_dir):
        reg = RegistryState(registry_dir)
        try:
            before = _active_global(reg)
            workspace = _workspace(registry_dir)
            autos = current_global_autos(reg)
            if not any(a.source == source for a in autos):
                raise PromotionError(f"Khong co global auto {source!r}")
            new_autos = [a for a in autos if a.source != source]
            bundle = build_revision(dict_dir, workspace, new_autos)
            now = utc_now()
            if _active_global(reg) != before:
                raise RegistryError(
                    f"stale global active: expected {before!r}"
                )
            reg.conn.execute(
                "INSERT INTO global_active(scope, revision_id, updated_at) "
                "VALUES('global',?,?) "
                "ON CONFLICT(scope) DO UPDATE SET "
                "revision_id=excluded.revision_id, updated_at=excluded.updated_at",
                (bundle.revision_id, now),
            )
            _upsert_candidate(reg, source, "", "revoked")
            _append_event(
                reg,
                source=source,
                event_type="revoked",
                from_status="global_auto",
                to_status="revoked",
                actor=actor,
                revision_id=bundle.revision_id,
                provenance={},
            )
            # AD-15: CAS pointer trong txn, projection + drift sau commit.
            reg.conn.commit()
            _materialize_autoviet(dict_dir, new_autos)
            _write_drift(
                registry_dir,
                bundle.revision_id,
                added=[],
                changed=[],
                revoked=[source],
                affected_books=[],
            )
            return GlobalRevokeResult(bundle.revision_id, source)
        finally:
            reg.close()
