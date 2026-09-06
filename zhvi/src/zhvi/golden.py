"""Golden corpus manifest + diff report (story 5.2, AD-14 / CAP-8).

Manifest la artifact committed (zhvi/tests/golden/manifest.json), khong
phai state per-project. Tooling ghi manifest + report; khong mutate
dictionary/revision. File ten expect* khong tu thanh golden — chi
is_approved / approved_cases la port gate 4.3 doc.
"""
from __future__ import annotations

import hashlib
import json
import re
from difflib import unified_diff
from itertools import zip_longest
from pathlib import Path

from .fsutil import atomic_write
from .pipeline import TranslateRequest, translate_project
from .project import Project
from .state import utc_now

MANIFEST_SCHEMA_VERSION = 1
DEFAULT_GOLDEN_MANIFEST = (
    Path(__file__).resolve().parents[2] / "tests" / "golden" / "manifest.json"
)
VALID_SCOPES = frozenset({"full", "contains"})
PROVENANCE_KEYS = ("origin", "mapping_rule", "imported_at")
MAPPING_RULE = "so trong ten expected -> chap{n}_raw.txt; mac dinh n=1"
_MAX_MISMATCHES = 5

__all__ = [
    "DEFAULT_GOLDEN_MANIFEST",
    "GoldenError",
    "MANIFEST_SCHEMA_VERSION",
    "approve_case",
    "approved_cases",
    "import_candidates",
    "is_approved",
    "load_manifest",
    "run_golden_report",
    "save_manifest",
]


class GoldenError(RuntimeError):
    """Loi schema/approve/IO cua golden manifest."""


def _resolve_manifest(path: Path | None) -> Path:
    return Path(path) if path is not None else DEFAULT_GOLDEN_MANIFEST


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _empty_manifest() -> dict:
    return {"schema_version": MANIFEST_SCHEMA_VERSION, "cases": {}}


def load_manifest(path: Path | None = None) -> dict:
    target = _resolve_manifest(path)
    if not target.is_file():
        raise GoldenError(f"Khong tim thay manifest: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GoldenError(f"Manifest JSON khong hop le: {e}") from e
    if not isinstance(data, dict):
        raise GoldenError("Manifest phai la object JSON")
    ver = data.get("schema_version")
    if not isinstance(ver, int):
        raise GoldenError("schema_version khong hop le")
    if ver > MANIFEST_SCHEMA_VERSION:
        raise GoldenError(
            f"schema_version {ver} moi hon {MANIFEST_SCHEMA_VERSION}"
        )
    cases = data.get("cases")
    if not isinstance(cases, dict):
        raise GoldenError("cases phai la object")
    return data


def save_manifest(path: Path | None, manifest: dict) -> Path:
    target = _resolve_manifest(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    atomic_write(target, payload.encode("utf-8"))
    return target


def _missing_gate_fields(case: dict) -> list[str]:
    """Field bat buoc cua AC #2 / 1.2 — dung chung is_approved va approve_case."""
    missing: list[str] = []
    if not case.get("source_sha256"):
        missing.append("source_sha256")
    if not case.get("expected_sha256"):
        missing.append("expected_sha256")
    if case.get("assertion_scope") not in VALID_SCOPES:
        missing.append("assertion_scope")
    prov = case.get("provenance")
    if not isinstance(prov, dict):
        missing.append("provenance")
        return missing
    for key in PROVENANCE_KEYS:
        if not prov.get(key):
            missing.append(f"provenance.{key}")
    return missing


def is_approved(case: dict) -> bool:
    """True chi khi du 5 thanh phan (AD-14: expect* khong tu golden)."""
    if not isinstance(case, dict):
        return False
    if _missing_gate_fields(case):
        return False
    approval = case.get("approval")
    if not isinstance(approval, dict):
        return False
    if not approval.get("actor") or not approval.get("approved_at"):
        return False
    return True


def approved_cases(manifest: dict) -> list[dict]:
    """API gate 4.3: chi case is_approved. Khong tu parse manifest o 4.3."""
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, dict):
        return []
    return [case for _, case in sorted(cases.items()) if is_approved(case)]


def _chapter_n(expected_name: str) -> int:
    m = re.search(r"(\d+)", Path(expected_name).stem)
    return int(m.group(1)) if m else 1


def _expected_files(reference_dir: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in ("expect*.txt", "excpect*.txt"):
        found.update(
            p.resolve() for p in reference_dir.glob(pattern) if p.is_file()
        )
    return sorted(found)


def _new_case(expected: Path, reference_dir: Path) -> dict:
    n = _chapter_n(expected.name)
    source = reference_dir / f"chap{n}_raw.txt"
    note = ""
    source_path = ""
    source_sha = ""
    if source.is_file():
        source_path = str(source.resolve())
        source_sha = _file_sha256(source)
    else:
        note = f"thieu source: chap{n}_raw.txt"
    return {
        "source_path": source_path,
        "source_sha256": source_sha,
        "expected_path": str(expected.resolve()),
        "expected_sha256": _file_sha256(expected),
        "assertion_scope": "full",
        "provenance": {
            "origin": expected.name,
            "mapping_rule": MAPPING_RULE,
            "imported_at": utc_now(),
        },
        "approval": None,
        "note": note,
    }


def _find_case_id(cases: dict, expected_path: str) -> str | None:
    for cid, case in cases.items():
        if isinstance(case, dict) and case.get("expected_path") == expected_path:
            return cid
    return None


def import_candidates(
    reference_dir: Path | str, manifest_path: Path | None = None
) -> dict:
    """Nhap expect*.txt + excpect*.txt thanh candidate (approval null)."""
    ref = Path(reference_dir)
    target = _resolve_manifest(manifest_path)
    if target.is_file():
        manifest = load_manifest(target)
    else:
        manifest = _empty_manifest()
    cases = manifest.setdefault("cases", {})
    imported = updated = unchanged = 0
    for expected in _expected_files(ref):
        expected_s = str(expected.resolve())
        new_case = _new_case(expected, ref)
        cid = _find_case_id(cases, expected_s)
        if cid is None:
            cid = expected.stem
            if cid in cases:
                cid = f"{expected.stem}-{new_case['expected_sha256'][:8]}"
            cases[cid] = new_case
            imported += 1
            continue
        old = cases[cid]
        if old.get("expected_sha256") == new_case["expected_sha256"]:
            unchanged += 1
            continue
        # 2.2: chi cap nhat hash expected + reset approval; giu scope/note/provenance.
        old["expected_sha256"] = new_case["expected_sha256"]
        old["approval"] = None
        cases[cid] = old
        updated += 1
    manifest["schema_version"] = MANIFEST_SCHEMA_VERSION
    save_manifest(target, manifest)
    return {
        "imported": imported,
        "updated": updated,
        "unchanged": unchanged,
        "total": len(cases),
    }


def approve_case(
    manifest_path: Path | None, case_id: str, actor: str
) -> dict:
    manifest = load_manifest(manifest_path)
    cases = manifest["cases"]
    if case_id not in cases:
        raise GoldenError(f"Khong co case {case_id!r}")
    case = cases[case_id]
    if not isinstance(case, dict):
        raise GoldenError(f"Case {case_id!r} khong hop le")
    missing = _missing_gate_fields(case)
    if missing:
        raise GoldenError(f"Thieu field bat buoc: {', '.join(missing)}")
    case["approval"] = {"actor": actor, "approved_at": utc_now()}
    save_manifest(manifest_path, manifest)
    return case


def _hash_match(path_str: str, recorded: str) -> bool:
    if not path_str or not recorded:
        return False
    path = Path(path_str)
    if not path.is_file():
        return False
    return _file_sha256(path) == recorded


def _zh_snippet(source_text: str) -> str:
    for line in source_text.splitlines():
        if line.strip():
            return line.strip()[:80]
    return source_text.strip()[:80]


def _compare(
    expected_text: str,
    output_text: str,
    scope: str,
    case_id: str,
    *,
    source_text: str = "",
    source_path: str = "",
) -> tuple[bool, int, list[dict], str]:
    if scope == "contains":
        left, right = expected_text.strip(), output_text.strip()
        passed = left in right
    else:
        left = expected_text.rstrip("\n")
        right = output_text.rstrip("\n")
        passed = left == right
    if passed:
        return True, 0, [], ""
    exp_lines = left.splitlines()
    out_lines = right.splitlines()
    diff = list(
        unified_diff(
            exp_lines, out_lines, fromfile="expected", tofile="output", lineterm=""
        )
    )
    diff_lines = sum(
        1
        for line in diff
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    mismatches: list[dict] = []
    for i, (a, b) in enumerate(zip_longest(exp_lines, out_lines, fillvalue="")):
        if a != b:
            mismatches.append({"line": i + 1, "expected": a, "output": b})
            if len(mismatches) >= _MAX_MISMATCHES:
                break
    snippet = _zh_snippet(source_text)
    quoted = json.dumps(snippet, ensure_ascii=False) if snippet else '""'
    hint = f"zhvi explain {quoted} # {case_id} source={source_path}"
    return False, diff_lines, mismatches, hint


def _base_record(case_id: str, case: dict) -> dict:
    return {
        "case_id": case_id,
        "status": "approved" if is_approved(case) else "candidate",
        "pass": False,
        "source_sha256_match": _hash_match(
            str(case.get("source_path") or ""), str(case.get("source_sha256") or "")
        ),
        "expected_sha256_match": _hash_match(
            str(case.get("expected_path") or ""),
            str(case.get("expected_sha256") or ""),
        ),
        "diff_lines": 0,
        "mismatches": [],
        "trace_hint": "",
    }


def run_golden_report(
    project: Project,
    manifest_path: Path | None = None,
    dict_dir: str | None = None,
) -> dict:
    """Chay pipeline so expected; khong chan case khac khi mot case loi."""
    manifest = load_manifest(manifest_path)
    records: list[dict] = []
    reports_dir = project.state_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for case_id, case in sorted(manifest.get("cases", {}).items()):
        if not isinstance(case, dict):
            continue
        rec = _base_record(case_id, case)
        source_path = Path(case["source_path"]) if case.get("source_path") else None
        expected_path = (
            Path(case["expected_path"]) if case.get("expected_path") else None
        )
        if source_path is None or not source_path.is_file():
            rec["error"] = "missing source"
            records.append(rec)
            continue
        if expected_path is None or not expected_path.is_file():
            # Spec 4.3 chi bat "missing source"; van ghi loi rieng de khong
            # chan case khac (report khong phai QA gate).
            rec["error"] = "missing expected"
            records.append(rec)
            continue
        out_path = reports_dir / f".golden-{case_id}.vi.txt"
        try:
            translate_project(
                project,
                TranslateRequest(
                    source=source_path,
                    output=out_path,
                    dict_dir=dict_dir,
                ),
            )
            output_text = out_path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001 — report khong chan case khac
            rec["error"] = f"{type(e).__name__}: {e}"
            records.append(rec)
            continue
        finally:
            if out_path.exists():
                out_path.unlink()
        expected_text = expected_path.read_text(encoding="utf-8")
        source_text = source_path.read_text(encoding="utf-8")
        scope = case.get("assertion_scope") or "full"
        passed, diff_lines, mismatches, hint = _compare(
            expected_text,
            output_text,
            scope,
            case_id,
            source_text=source_text,
            source_path=str(source_path),
        )
        rec["pass"] = passed
        rec["diff_lines"] = diff_lines
        rec["mismatches"] = mismatches
        rec["trace_hint"] = hint
        records.append(rec)

    payload = {"report_path": "", "cases": records}
    report_path = reports_dir / "golden-diff.json"
    payload["report_path"] = str(report_path)
    atomic_write(
        report_path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return payload
