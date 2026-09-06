---
baseline_commit: 82278835e0d8928fc36cc7c9e0c0117126ed4c31
---

# Story 4.2: Cross-book evidence ingest + dedupe

Status: done

## Story

As a hệ thống học toàn cục,
I want book project gửi evidence bất biến (kèm book_id, source revision, occurrence identity) vào registry, dedupe theo `(book_id, source_revision_id, candidate_id, occurrence_span)`, chỉ tính active source revision mỗi book,
So đó copy project/import lại không tăng cross-book count.

## Acceptance Criteria

1. **Given** nhiều book project submit evidence cho cùng candidate **When** ingest **Then** occurrence trùng key dedupe; chỉ active source revision của mỗi book vào promotion evidence; book không mutate global candidate/revision trực tiếp.
2. Copy project + import lại cùng source không tăng cross-book count và không tăng occurrence tổng.

## Tasks / Subtasks

- [x] Task 1 — Registry schema v2: bảng evidence + active book pointer (AC: #1)
  - [x] 1.1 `REGISTRY_SCHEMA_VERSION = 2`; `_REGISTRY_SCHEMA` thêm (CREATE IF NOT EXISTS — additive AD-19):
    - `global_evidence(book_id, source_revision_id, candidate_id, occurrence_span, dictionary_revision_id, group_name, signals_json, score, ingested_at)` với `UNIQUE(book_id, source_revision_id, candidate_id, occurrence_span)` — dedupe key AD-17
    - `book_sources(book_id PRIMARY KEY, active_source_revision_id, active_source_created_at, updated_at)` — active source revision pointer mỗi book
  - [x] 1.2 `_migrate` v1→v2: chỉ CREATE TABLE IF NOT EXISTS + bump `schema_version` — không drop/sửa bảng v1 (AD-19)
- [x] Task 2 — Evidence record + ingest API trong `registry.py` (AC: #1, #2)
  - [x] 2.1 `@dataclass(frozen=True) EvidenceRecord`: `book_id, source_revision_id, candidate_id, occurrence_span, dictionary_revision_id, group_name, signals_json, score, source_created_at` — payload bất biến book gửi (mọi field `str`/`float`, không object phức tạp)
  - [x] 2.2 `ingest_evidence(registry_dir, records)` — với `registry_lock` quanh toàn bộ mutation (AD-13: mutate global state phải qua writer lock), mở `RegistryState`, MỘT transaction:
    - `INSERT OR IGNORE INTO global_evidence` từng record — trùng dedupe key là no-op (AC #1 dedupe)
    - upsert `book_sources`: chỉ move pointer khi `source_created_at` MỚI HƠN giá trị hiện có (chống ingest out-of-order lùi pointer); book mới insert thẳng
  - [x] 2.3 `RegistryState.cross_book_summary() -> list[dict]` — per `candidate_id`: `books` = DISTINCT book_id, `occurrences` = số row, CHỈ tính row có `source_revision_id == active_source_revision_id` của book đó (JOIN `book_sources`; book chưa có pointer không tính). Không compute gate nào — 4.3 dùng cho hard gates.
- [x] Task 3 — Book-side submitter `zhvi/src/zhvi/learning/ingest.py` (AC: #1, #2)
  - [x] 3.1 `build_evidence_records(state: State) -> list[EvidenceRecord]` — đọc `state.latest_source_revision()` (state.py:547; None → trả `[]`), map từng `candidate_evidence` row thành record với `occurrence_span = group_name` (xem Dev Notes — quyết định map identity), `source_created_at` từ `source_revisions.created_at`
  - [x] 3.2 `submit_book_evidence(state, dict_dir)` — convenience: build + `ingest_evidence(resolve_registry_dir(dict_dir), records)`; trả summary dict `{submitted, inserted, books}` cho caller/test
- [x] Task 4 — Tests `zhvi/tests/test_ingest.py` (AC: #1, #2)
  - [x] 4.1 Dedupe: ingest cùng records 2 lần → `SELECT COUNT(*)` global_evidence không đổi; `cross_book_summary()` không đổi
  - [x] 4.2 Copy project (AC #2): project thật qua pipeline mini (create_project → snapshot source → discovery → evaluate_candidates, pattern test_discovery.py); `shutil.copytree` + `create_project(copy_root)` re-init idempotent; build records từ cả 2 project, ingest cả 2 → cùng candidate: `books == 1`, occurrences không tăng so với ingest một bản
  - [x] 4.3 Active source revision only (AC #1): book A ingest rev1 rồi rev2 (source sửa, created_at mới hơn) → summary chỉ tính rev2 rows; rev1 rows VẪN CÒN trong bảng (bảo toàn) nhưng không đếm; `book_sources.active_source_revision_id == rev2`
  - [x] 4.4 Out-of-order: ingest rev2 trước rồi rev1 (created_at cũ hơn) → pointer vẫn rev2, summary không đổi
  - [x] 4.5 Cross-book: 2 book_id khác nhau cùng candidate → `books == 2`
  - [x] 4.6 Lock (AC #1, AD-13): giữ `registry_lock` ngoài → `ingest_evidence` raise `RegistryError` (message có path lock)
  - [x] 4.7 Migration v1→v2: tạo DB v1 thủ công (chỉ bảng `meta`, `schema_version=1` — mô phỏng registry tạo bởi story 4.1) → mở `RegistryState` → `schema_version == 2`, đủ 3 bảng; registry v1 cũ không mất dữ liệu meta
  - [x] 4.8 Scope (AC #1 "không mutate global candidate/revision"): sau ingest, danh sách bảng registry == `{meta, global_evidence, book_sources}` — KHÔNG bảng global candidate/entry/revision (4.3 mới thêm)
- [x] Task 5 — Full suite pass (AC: toàn bộ)
  - [x] 5.1 `cd zhvi && .venv/bin/python -m pytest tests` xanh toàn bộ (baseline 243 passed / 2 skipped)
  - [x] 5.2 Ruff sạch file mới/sửa (qua pyenv shim)

## Dev Notes

### Invariants ràng buộc

- **AD-17** — dedupe occurrence theo `(book_id, source_revision_id, candidate_id, occurrence_span)`; chỉ active source revision mỗi book vào promotion evidence. Copy project giữ `book_id` (4.1 đã test) nên re-ingest trùng key → no-op.
- **AD-13** — chỉ registry writer lock được mutate global state. `ingest_evidence` PHẢI lấy `registry_lock`; KHÔNG giữ lock trong discovery (submitter gọi SAU khi book evidence đã xong).
- **AD-19** — migration additive: v1→v2 chỉ CREATE TABLE IF NOT EXISTS + bump `schema_version` trong `meta`. Registry v1 của user thật giữ nguyên.
- **data-model "Phân quyền nguồn chân lý"** — book project GỬI evidence bất biến, không mutate global candidate/revision trực tiếp → schema v2 không có bảng global candidate/revision; chúng thuộc 4.3.

### Quyết định thiết kế story

- **`occurrence_span = group_name`** — evidence book hiện là aggregate theo 6 signal groups (strength/stability/benefit/risk/scope/regression — evidence.py:180-270), KHÔNG có per-text-span. Map `occurrence_span` = tên group cho identity deterministic: mỗi (candidate, book, source_revision) có tối đa 6 occurrence records. Từ chối phương án per-text-span (chapter/offset từng occurrence): book DB không track span từng occurrence, phải mở observations schema + đổi discovery — ngoài scope, làm sau additive nếu 4.3 cần. `occurrence_span` là TEXT opaque với registry — semantics do submitter định nghĩa, đổi semantics sau không phá schema.
- **Active pointer chống out-of-order qua `source_created_at`** — registry không biết thứ tự thời gian source revision của book; record mang `created_at` của `source_revisions` (book có sẵn), pointer chỉ move khi mới hơn. Không tin thứ tự gọi ingest.
- **`INSERT OR IGNORE` + UNIQUE key** — idempotent tự nhiên; không cần đọc-trước-ghi. Trùng key với payload KHÁC (score/signals đổi) vẫn ignore — evidence bất biến theo (book, source_revision); source đổi → source_revision_id đổi → row mới, đúng semantics.
- **Registry KHÔNG import book State** — `registry.py` nhận `EvidenceRecord` thuần dữ liệu; book-side mapping ở `learning/ingest.py` (import registry, một chiều). Hai mutation scope tách bạch (4.1 đã đặt nền).
- **Không CLI** — `zhvi learn --global` là 4.3 (đánh giá promotion). 4.2 expose Python entry point (`submit_book_evidence`) đủ cho 4.3 wiring.
- **`cross_book_summary` là query thuần** — không gate, không ngưỡng; 4.3 quyết cách tính "≥20 occurrence" (row count hay sum total_count từ signals — đã store signals_json nên cả hai khả thi).

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Registry state + lock + realpath | `RegistryState`, `registry_lock`, `resolve_registry_dir` | registry.py (4.1) |
| Book active source revision | `State.latest_source_revision()` | state.py:547-551 |
| Evidence rows book | `candidate_evidence` (UNIQUE candidate_id+group_name), `_EV_COLS` | state.py:165-177, 211-214 |
| Id evidence content-addressed | `ev_id(book_id, drev, candidate_id, group)` | evidence.py:92-99 |
| Timestamp UTC | `utc_now()` | state.py:229 |
| Pipeline mini fixture | pattern discovery/evaluate fixture | tests/test_discovery.py, test_evidence.py |
| Migration pattern | `State._migrate` + 4.1 `_migrate` | state.py, registry.py:64-72 |

### Previous story intelligence (4.1)

- Comments Việt không dấu (convention module zhvi); imports top; lint hook chặn F401/F841 từng edit.
- Edit tool khó match chuỗi CJK — edit tránh đụng dòng CJK.
- Registry lazy-init; test dùng absolute path `tmp_path`.
- Copy project test: `shutil.copytree` + `create_project(copy_root)` cho re-init thật (không chỉ copy file).
- Suite baseline 243 passed / 2 skipped (~7 phút); venv `.venv/bin/python -m pytest` từ `zhvi/`.
- `RegistryState.__init__` close conn trước raise (không leak connection) — giữ pattern khi thêm code mở-đóng.

### Project Structure Notes

- `zhvi/src/zhvi/registry.py` — sửa (schema v2 + EvidenceRecord + ingest + summary).
- `zhvi/src/zhvi/learning/ingest.py` — mới (book-side submitter; import `EvidenceRecord`, `ingest_evidence` từ `zhvi.registry`, `State` từ `zhvi.state` — một chiều, không cycle).
- `zhvi/tests/test_ingest.py` — mới (mọi test story).
- KHÔNG sửa `state.py`, `evidence.py`, `project.py`, CLI — trừ khi test lộ bug (comment `[Note]` + báo, không âm thầm fix).

### Phạm vi KHÔNG làm

- Không bảng global candidate/entry/active revision toàn cục, không `AutoVietPhrase.txt` materialize (4.3).
- Không hard gates, không `zhvi learn --global` CLI, không golden manifest (4.3).
- Không đổi schema book DB (state.py), không đổi discovery/evidence evaluator.
- Không per-occurrence text span tracking (xem quyết định thiết kế).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2 (lines 365–376)]
- [Source: ARCHITECTURE-SPINE.md — AD-13 (line 111), AD-17 (line 135), AD-19 (line 147), registry layout (202–206)]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/data-model.md — Phân quyền nguồn chân lý (lines 5–13), Concurrency (109–115), registry layout (86–89)]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/SPEC.md — CAP-4 (lines 34–36)]
- [Source: zhvi/src/zhvi/registry.py — toàn bộ (4.1)]
- [Source: zhvi/src/zhvi/state.py — candidate_evidence (165-177), latest_source_revision (547-551), source_revisions (38-45)]
- [Source: zhvi/src/zhvi/learning/evidence.py — 6 groups (180-270), ev_id (92-99)]
- [Source: zhvi/tests/test_registry.py — pattern registry test 4.1]
- [Source: _bmad-output/implementation-artifacts/4-1-registry-tai-dictionary-root-book-id-realpath-writer-lock.md — previous story]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_ingest.py RED (ModuleNotFoundError zhvi.learning.ingest) → GREEN 10/10.
- Full suite 253 passed / 2 skipped (baseline 243 + 10 mới, 0 regression; 7 phút).
- Ruff: 0 issue trên 3 file mới/sửa (registry.py, learning/ingest.py, test_ingest.py).
- venv: `.venv/bin/python -m pytest` từ `zhvi/`.

### Completion Notes List

- Schema v2 additive (AD-19): `global_evidence` UNIQUE `(book_id, source_revision_id, candidate_id, occurrence_span)` (AD-17 dedupe key) + `book_sources` active pointer per book. `_migrate` v1→v2 chỉ bump `schema_version` — bảng do `_REGISTRY_SCHEMA` CREATE IF NOT EXISTS tạo, registry v1 cũ giữ meta.
- `EvidenceRecord` frozen dataclass thuần dữ liệu; registry KHÔNG import book State — `learning/ingest.py` import registry một chiều.
- `ingest_evidence`: `registry_lock` quanh toàn bộ mutation (AD-13); MỘT transaction INSERT OR IGNORE + upsert pointer có điều kiện `WHERE excluded.active_source_created_at > book_sources.active_source_created_at` (SQLite UPSERT, chống out-of-order); `inserted` đếm qua `cursor.rowcount` (0 khi bị UNIQUE ignore).
- `occurrence_span = group_name` — mỗi (candidate, book, source_revision) tối đa 6 records; TEXT opaque với registry.
- `cross_book_summary()`: JOIN `book_sources` trên `active_source_revision_id` — chỉ active revision mỗi book đếm; rev cũ rows bảo toàn trong bảng nhưng không vào promotion evidence.
- Sửa 3 test story 4.1 hardcode `schema_version == 1` → dùng `REGISTRY_SCHEMA_VERSION` (bump v2 có chủ đích, comment test 4.1 đã dự liệu "chuẩn bị cho 4.2 bump version"); test newer-schema giờ set `VERSION+1`.
- Test copy project (AC #2) dùng pipeline thật: discovery + build_candidates + evaluate_candidates, copytree + re-init, ingest bản copy → `inserted == 0`, summary không đổi.
- **Review fixes (2 trục Opus, 0 hard / 8 findings — 7 fix, 1 skip):** Standards — bỏ assert tautology (`X or True`) thành assert thật (build rỗng không tạo registry), bỏ Python `newest` dict trùng lớp SQL WHERE (WHERE là hàng rào chống lùi duy nhất, đúng mọi thứ tự), `cross_book_summary` dùng `cursor_dicts`, comment pin ISO format cho `source_created_at` string-compare, comment import `utc_now` là leaf helper (không import class State). Spec — thêm literal re-import (import_snapshot lần 2 cùng nội dung, AC #2 chữ "import lại"); full suite 5.1 đã chạy trước review (253/2). Skip: tách fixture `SRC`/`_dict_dir`/`_learned_book` vào conftest.py — đụng 2 file test cũ ngoài phạm vi story (story ghi "KHÔNG sửa file hiện có"); flag cho story sau khi thêm conftest chung.

### File List

- zhvi/src/zhvi/registry.py (sửa — schema v2 + EvidenceRecord + ingest_evidence + cross_book_summary)
- zhvi/src/zhvi/learning/ingest.py (mới — build_evidence_records + submit_book_evidence)
- zhvi/tests/test_ingest.py (mới — 10 test)
- zhvi/tests/test_registry.py (sửa — 3 test bỏ hardcode schema_version)

## Change Log

- 2026-09-06: Story created — ultimate context engine analysis completed.
- 2026-09-06: Story 4.2 implementation — registry schema v2 (global_evidence + book_sources), ingest + dedupe, book submitter; 10 test mới; full suite 253/2.
- 2026-09-06: Review fixes (2 trục Opus, 7 fix / 1 skip) — assert thật, bỏ newest dict, cursor_dicts, format comment, literal re-import; suite 253/2.
