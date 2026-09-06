---
baseline_commit: 4eaca6b3eaba94f4371c81d4b4a7a20605686659
---

# Story 5.2: Golden manifest tooling + diff report candidate reference

Status: done

## Story

As a người duyệt golden corpus,
I want công cụ tạo/sửa golden manifest (`zhvi/tests/golden/manifest.json`: source hash, expected hash, phạm vi assertion, provenance, dấu duyệt), import `raw_china/expect*.txt` + `excpect*.txt` làm candidate, và chạy pipeline xuất diff report cho toàn bộ candidate reference,
So đó quyết định golden dựa trên diff thật và global gate chỉ chạy trên case đã duyệt.

## Acceptance Criteria

1. **Given** các file `raw_china/expect.txt`, `raw_china/excpect2.txt` (và mọi file khớp `expect*`/`excpect*`) **When** chạy lệnh golden tooling **Then** pipeline dịch source đã pin, so sánh với expected đã pin (byte hoặc approved structural diff), xuất diff report cho từng case với trace tới candidate/entry.
2. Chỉ case trạng thái `approved` (đủ source hash + expected hash + assertion scope + provenance + dấu duyệt) tham gia promotion gate; case chưa duyệt hiện trong report với nhãn candidate.
3. Global auto-promotion (Story 4.3) đọc cùng manifest này; test xác nhận case không approved không thể mở global gate.

## Tasks / Subtasks

- [x] Task 1 — Module `zhvi/src/zhvi/golden.py` (AC: #1, #2)
  - [x] 1.1 `DEFAULT_GOLDEN_MANIFEST`: `Path(__file__).resolve().parents[2] / "tests" / "golden" / "manifest.json"` (= `zhvi/tests/golden/manifest.json` theo epics); mọi hàm nhận `manifest_path: Path | None = None` override
  - [x] 1.2 Manifest schema v1 (JSON, indent 2, sort_keys): `{"schema_version": 1, "cases": {case_id: case}}`; mỗi case: `source_path`, `source_sha256`, `expected_path`, `expected_sha256`, `assertion_scope` (`"full"` | `"contains"`), `provenance` (dict: `origin`, `mapping_rule`, `imported_at`), `approval` (`null` | `{"actor": str, "approved_at": ISO-utc_now}`), `note` (optional). `GoldenError(RuntimeError)` riêng cho module
  - [x] 1.3 `is_approved(case) -> bool` — True chỉ khi đủ: source_sha256 + expected_sha256 + assertion_scope hợp lệ + provenance + approval (AD-14: file tên `expect*` KHÔNG tự thành golden)
  - [x] 1.4 `approved_cases(manifest) -> list[case]` — filter qua `is_approved`; đây là API gate 4.3 đọc (AC #3 nền)
  - [x] 1.5 `load_manifest(path)` + `save_manifest(path, manifest)` — load validate schema_version (mới hơn → `GoldenError`); save atomic (write temp + `os.replace`, pattern `atomic_write` export.py:69-73)
- [x] Task 2 — Import candidates (AC: #1)
  - [x] 2.1 `import_candidates(reference_dir, manifest_path) -> dict` — glob `expect*.txt` + `excpect*.txt` (KHÔNG đụng `out*.txt`, `*.json`, `chap*_raw.txt`); mỗi file tạo case `candidate` (approval null). Mapping source: heuristic số trong tên expected (`excpect2.txt` → 2; không số → 1) ghép `chap{N}_raw.txt` trong cùng dir; thiếu source → case vẫn tạo với `source_path` rỗng + note lỗi (hiện trong report, không crash toàn bộ import)
  - [x] 2.2 Idempotent: case trùng `expected_path` + `expected_sha256` giữ nguyên (không đụng approval đã có — approve không bị import xóa); hash expected đổi → cập nhật hash + reset approval về null (evidence stale)
  - [x] 2.3 Legacy `excpect*.txt` giữ nguyên tên file làm provenance (SPEC open-questions #115: giữ để audit, không chuẩn hóa tên)
- [x] Task 3 — Approve (AC: #2)
  - [x] 3.1 `approve_case(manifest_path, case_id, actor) -> case` — set `approval = {"actor", "approved_at": utc_now()}`; thiếu field bắt buộc nào (source_sha256, expected_sha256, scope, provenance) → `GoldenError` liệt kê field thiếu
- [x] Task 4 — Diff report chạy pipeline (AC: #1)
  - [x] 4.1 `run_golden_report(project, manifest_path, dict_dir=None) -> dict` — mỗi case có source: `translate_project(project, TranslateRequest(source=case.source_path, output=tmp))` (pipeline.py:123; dict_dir pass-through), đọc output, so với expected theo scope: `full` → strip trailing newline hai phía rồi byte equal; `contains` → expected (strip) là substring output (strip). Per case record: `case_id`, `status` (`candidate` | `approved`), `pass` (bool), `source_sha256_match`, `expected_sha256_match`, `diff_lines` (số dòng khác qua `difflib.unified_diff`), `mismatches` (tối đa 5 excerpt line-pair expected/output), `trace_hint` (chuỗi gợi ý `zhvi explain` cho vị trí đầu tiên)
  - [x] 4.2 Ghi report `<project>/.zhvi/reports/golden-diff.json` (mkdir, atomic write) + trả dict cho CLI in summary
  - [x] 4.3 Case không có source (import lỗi mapping) xuất trong report với `status: candidate`, `error: "missing source"`, không chặn các case khác
- [x] Task 5 — CLI `golden` group (AC: #1, #2) — thêm vào `cli.py` theo pattern `dict_app` (cli.py:56-57)
  - [x] 5.1 `zhvi golden import -p PROJECT --dir raw_china [--manifest PATH]` — gọi `import_candidates`, stdout JSON summary (ensure_ascii=False): `{imported, updated, unchanged, total}` (pattern JSON stdout + err_console log của module)
  - [x] 5.2 `zhvi golden approve CASE_ID --actor NAME [--manifest PATH]` — không cần `-p` (manifest standalone); lỗi in stderr + exit code != 0 (pattern TermsError/ProjectError hiện có)
  - [x] 5.3 `zhvi golden report -p PROJECT [--manifest PATH]` — chạy `run_golden_report`, stdout JSON summary per case
- [x] Task 6 — Tests `zhvi/tests/test_golden.py` (AC: #1, #2, #3)
  - [x] 6.1 Import: fixture mini `raw_china`-giả trong tmp (2 source ZH nhỏ + `expect.txt` + `excpect2.txt`) → import → 2 case candidate, approval null; `out.txt`/`chap*_raw.txt`/JSON không bị nhặt; heuristic mapping ghép đúng source; idempotent lần 2 (unchanged); hash expected đổi → reset approval
  - [x] 6.2 Approve: đủ field → approved, `is_approved` True, vào `approved_cases`; thiếu source_sha256 (case lỗi mapping) → `GoldenError` liệt kê field; approve không bị import sau đó xóa (6.1 idempotent + 6.2 kết hợp)
  - [x] 6.3 AD-14: import xong toàn bộ → `approved_cases() == []` (file expect* không tự golden)
  - [x] 6.4 Report: project mini (pattern test_ingest `_learned_book` / test_registry discovery fixture — mini dict + source) + manifest case full khớp expected → `pass: True`; case expected sai một dòng → `pass: False`, `diff_lines > 0`, có mismatch excerpt + trace_hint; case thiếu source → error entry, case khác vẫn chạy
  - [x] 6.5 AC #3 nền: case không approved KHÔNG xuất hiện trong `approved_cases` dù mọi field khác đủ (chỉ thiếu approval) — hợp đồng 4.3 đọc
  - [x] 6.6 CLI qua `typer.testing.CliRunner` (pattern test_cli.py): import/approve/report chạy happy path, JSON stdout parse được; approve lỗi exit code != 0
  - [x] 6.7 Manifest schema guard: `schema_version` 2 → `GoldenError`
- [x] Task 7 — Full suite pass (AC: toàn bộ)
  - [x] 7.1 `cd zhvi && .venv/bin/python -m pytest tests` xanh toàn bộ (baseline 253 passed / 2 skipped)
  - [x] 7.2 Ruff sạch file mới/sửa

## Dev Notes

### Invariants ràng buộc

- **AD-14** — global promotion fail-closed: file tên `expect*` không tự trở thành golden; chỉ case approved (đủ 5 thành phần) tham gia promotion gate. `is_approved` là port duy nhất kiểm — 4.3 phải gọi `approved_cases`, không tự parse manifest.
- **AD-19 tinh thần** — legacy `excpect*.txt` (tên sai chính tả) giữ nguyên làm provenance audit, không rename.
- **data-model "Phân quyền"** — golden manifest human-owned sau duyệt; tooling ghi manifest + report, không mutate dictionary/revision.
- Spec CAP-8 (SPEC.md:50-52): import → diff report → duyệt → mới vào promotion gate.

### Quyết định thiết kế story

- **Manifest đặt `zhvi/tests/golden/manifest.json`** — đúng chữ epics. Đây là artifact committed (golden corpus của repo), KHÔNG phải state per-project; runtime path tính từ package root (`parents[2]`), CLI `--manifest` override cho test dùng tmp. Diff report thì per-project (`.zhvi/reports/`) vì gắn run/project.
- **Dấu duyệt (SPEC open-question 114)** — format `approval: {actor, approved_at}`; actor do người duyệt tự khai báo qua `--actor` (không xác thực LDAP/git — out of scope, ghi minh bạch provenance). Case approved = TOÀN BỘ 5 field + approval (AC #2 chữ "đủ").
- **So sánh "byte hoặc approved structural diff"** — v1 dùng scope `"full"` (byte, strip trailing newline) và `"contains"` (subset) — đã là "structural" mức tối thiểu; diff whitespace-tolerant đầy đủ thêm sau additive nếu review cần. Mọi case import mặc định scope `"full"`.
- **Hash đổi → reset approval** — evidence stale: expected file sửa thì dấu duyệt cũ vô hiệu; bắt duyệt lại. Source hash đổi tương tự qua `source_sha256_match: False` trong report (không auto-reset — người duyệt thấy trong report).
- **Report không chặn** — golden report là công cụ duyệt, KHÔNG phải QA gate của run (5.1 đã lo QA run); report luôn xuất đủ mọi case, pass/fail chỉ thông tin.
- **Trace tới candidate/entry** — mức v1: mismatch excerpt + `trace_hint` trỏ lệnh `zhvi explain` (đã có, learning/explain.py) cho vị trí đầu tiên; auto-trace per-span vào report là mở rộng sau (note Phạm vi KHÔNG làm).
- **Pipeline chạy với temp output** — không đụng `dist/book.vi.txt` của user; output case ghi temp rồi đọc so sánh.

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Chạy pipeline | `translate_project(project, TranslateRequest(source=..., output=...))` | pipeline.py:50-57, 123-129 |
| Atomic write | pattern `atomic_write` (temp + os.replace) | export.py:69-73 |
| SHA-256 file | `hashlib.sha256(path.read_bytes())` — pattern `block_source_hash`/snapshot | snapshot.py |
| Timestamp UTC | `utc_now()` | state.py:229 |
| Typer sub-app | pattern `dict_app = typer.Typer(...)` + `app.add_typer` | cli.py:56-57 |
| CLI JSON stdout + err log | pattern commands hiện có (`json.dumps(..., ensure_ascii=False)` stdout, `err_console` stderr) | cli.py |
| Diff | `difflib.unified_diff` (cli.py đã import SequenceMatcher/unified_diff) | cli.py:8 |
| Mini fixture project | pattern `_learned_book` test_ingest / discovery fixture test_registry | tests/test_ingest.py, tests/test_registry.py |
| CliRunner test | pattern test_cli.py | tests/test_cli.py |

### Previous story intelligence (4.2)

- Comments Việt không dấu; imports top; lint hook chặn F401/F841 TỪNG edit — khi import + usage tách 2 edit, edit usage TRƯỚC hoặc chấp nhận 1 lần block rồi edit tiếp.
- Edit tool khó match chuỗi CJK — test fixture CJK viết bằng Write cả file, tránh Edit trên dòng CJK.
- Suite baseline 253 passed / 2 skipped (~7 phút); `.venv/bin/python -m pytest` từ `zhvi/`.
- Edit test cũ chỉ khi story dự liệu (4.2 sửa 3 test 4.1 hardcode schema_version — có comment chuẩn bị sẵn).
- Đã flag (chưa xử lý): fixture `SRC`/`_dict_dir` copy 3 file test — story này copy thêm lần 4 thì cân nhắc nhận note, KHÔNG tự tách conftest (ngoài scope từng story).

### Project Structure Notes

- `zhvi/src/zhvi/golden.py` — mới (manifest + import + approve + report API).
- `zhvi/src/zhvi/cli.py` — sửa (thêm `golden_app` group: import/approve/report).
- `zhvi/tests/test_golden.py` — mới (mọi test story).
- `zhvi/tests/golden/` — tạo qua CLI khi user chạy import thật (test dùng tmp `--manifest`, không commit manifest trong story này).
- KHÔNG sửa pipeline.py/state.py/export.py — chỉ dùng API.

### Phạm vi KHÔNG làm

- Không global promotion gate / `zhvi learn --global` (4.3 — chỉ cung cấp `approved_cases` API + test hợp đồng).
- Không chạy golden gate trong QA run (5.1 QA đã định nghĩa riêng).
- Không auto-trace per-span entry vào report (chỉ trace_hint); không structural diff whitespace-tolerant nâng cao.
- Không import/sửa file thật trong `raw_china/` — tooling đọc; manifest thật tạo khi user tự chạy CLI.
- Không xác thực actor (no auth); không rename legacy excpect.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2 (lines 411-423)]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/SPEC.md — CAP-8 (50-52), Out-of-scope (109), open-questions (114-115)]
- [Source: ARCHITECTURE-SPINE.md — AD-14 (line 117)]
- [Source: zhvi/src/zhvi/pipeline.py — TranslateRequest/translate_project (50-57, 123-129)]
- [Source: zhvi/src/zhvi/export.py — atomic_write (69-73)]
- [Source: zhvi/src/zhvi/cli.py — Typer app + dict_app pattern (38-57), JSON stdout pattern]
- [Source: zhvi/tests/test_cli.py — CliRunner pattern]
- [Source: zhvi/tests/test_ingest.py — mini fixture pipeline pattern (_learned_book)]
- [Source: raw_china/ — expect.txt, excpect2.txt, chap1_raw.txt, chap2_raw.txt (mapping heuristic gốc)]

## Dev Agent Record

### Agent Model Used

Grok 4.6

### Debug Log References

- Red: `tests/test_golden.py` collection `ModuleNotFoundError: zhvi.golden` (đúng TDD).
- Green: 9 passed in test_golden.py; ruff no issues.
- Full suite: 262 passed / 2 skipped in 419s (baseline 253 + 9; 0 regression).
- Review fixes: test_golden 11 passed; full suite 264 passed / 2 skipped; ruff sạch.

### Completion Notes List

- `zhvi/src/zhvi/golden.py`: manifest schema v1, `is_approved`/`approved_cases` (port 4.3, AD-14), import glob expect*/excpect* idempotent + stale-hash reset approval, approve fail-closed, `run_golden_report` ghi `.zhvi/reports/golden-diff.json`.
- CLI `zhvi golden {import,approve,report}`; `--dict-dir` trên report để test/isolation (cùng pattern translate/learn).
- Không commit `zhvi/tests/golden/manifest.json` — test dùng tmp `--manifest`.
- `approved_cases` rỗng sau import (expect* không tự golden).
- **Review fixes (2 trục, 0 hard — 8 fix / 5 skip):** provenance bắt 3 key `origin`/`mapping_rule`/`imported_at` (chung `_missing_gate_fields`); stale expected chỉ cập nhật hash + `approval=null` (giữ scope/note); `contains` pass → `diff_lines=0`; `trace_hint` = `zhvi explain` snippet ZH; test source-hash không reset, report `status=approved`, approve thiếu source, nhiều field, stderr `_fail`. Skip: tách module, data-clump path+sha, collision stem-sha, `--dict-dir` report, `error: "missing expected"` (giữ + comment).

### File List

- zhvi/src/zhvi/golden.py
- zhvi/src/zhvi/cli.py
- zhvi/tests/test_golden.py
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-09-06: Story created — ultimate context engine analysis completed.
- 2026-09-06: Implemented golden tooling (import/approve/report) + 9 tests; suite 262 passed / 2 skipped.
- 2026-09-06: Review fixes (2 trục, 8 fix / 5 skip) — provenance keys, stale hash giữ scope, contains/trace_hint, test gate; suite 264/2.
