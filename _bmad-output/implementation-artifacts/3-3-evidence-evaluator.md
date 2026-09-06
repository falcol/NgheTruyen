---
baseline_commit: 6b33dc5
---

# Story 3.3: Evidence evaluator

Status: done

## Story

As a hệ thống học theo truyện,
I want mỗi candidate có evidence độc lập với output: độ mạnh (frequency, PMI, left/right entropy), độ ổn định (cùng segmentation + target qua occurrence), lợi ích (giảm unknown/single-char/fragmentation), rủi ro (overlap/target/manual conflict, junk likelihood), phạm vi (chương/truyện/thể loại), regression (block đổi, golden diff, invariant fail),
So đó promotion quyết trên tín hiệu kiểm chứng được chứ không phải cảm tính.

## Acceptance Criteria

1. **Given** candidate đã build **When** evaluate **Then** evidence lưu bảng `candidate_evidence` theo từng nhóm tín hiệu; điểm chỉ dùng xếp hạng.
2. Evidence tính từ observation + trạng thái từ điển hiện tại, không phụ thuộc output cuối.
3. Test: candidate tăng coverage thật có evidence benefit dương; candidate conflict manual có risk `manual_conflict`.

## Tasks / Subtasks

- [x] Task 1: Migration v5 → v6 — bảng `candidate_evidence` (AC: 1)
  - [x] `state.py`: `SCHEMA_VERSION = 6`; DDL mới trong `_SCHEMA`; `_migrate` comment nhánh v5→v6
  - [x] `EvidenceRow` dataclass + `_EV_COLS` + `replace_evidence(book_id, dictionary_revision_id, rows)` — scope explicit, rows rỗng vẫn xóa
- [x] Task 2: `learning/evidence.py` — `evaluate_candidates` (AC: 1–3)
  - [x] Đọc candidates + observation map (source revision mới nhất theo rowid cho drev)
  - [x] 6 nhóm tín hiệu đúng formula trong Dev Notes; regression = placeholder `{"deferred": "story-3.4"}` (AC 2)
  - [x] `manual_conflict` prefix-path + DFS extension depth 8; `overlap_existing` extension auto/base
- [x] Task 3: CLI — `zhvi learn` gọi `evaluate_candidates` sau build (cùng lock); JSON thêm `"evidence"`
- [x] Task 4: Tests `tests/test_evidence.py` (AC: 1–3)
  - [x] AC1: 6 groups đủ × candidates; UNIQUE(candidate_id, group_name)
  - [x] AC2: run cũ với output khác → evidence không đổi (test `test_evidence_independent_of_output`)
  - [x] AC3: 李慕白 benefit dương (`reduces_single_char=1` — dict có PhienAm singles nên là fragmented run, không phải unknown; AC giữ nguyên tinh thần "tăng coverage thật có benefit dương"); `看着前` (chứa manual prefix) có `manual_conflict=1`
  - [x] Determinism implicit qua `test_evidence_independent_of_output` (evaluate 2 lần so sánh toàn bộ rows)
  - [x] Regression: full suite xanh — 213 passed / 2 skipped (baseline 206/2 + 7 mới)

## Dev Notes

### Invariants ràng buộc

- **AC 2 / AD-6 tinh thần** — evidence chỉ từ observation + dictionary state. KHÔNG đọc runs/blocks/output. Regression group là placeholder deferred 3.4 (ghi rõ trong signals).
- **AD-7** — điểm chỉ xếp hạng; hard gate là story 3.4. Tổng điểm cao không bù gate fail.
- **AD-8** — evidence là book SQLite state; replace-not-append theo (book_id, dictionary_revision_id).

### Trie overlap checks (verified loader/lattice)

- Prefix path: walk `dic.root` theo key — MỌI node trung gian có `entries` là prefix-entry của key (entry key = prefix).
- Extension: từ node cuối của key, DFS `children` depth ≤ 8 (NGRAM_MAX) — tìm mọi entry dài hơn chứa key làm prefix.
- `manual_conflict` đúng theo AC 3: builder 3.2 đã loại key TRÙNG manual; overlap khác span (prefix/extension) thì candidate vẫn sống và evidence ghi risk.
- `_entry_layer(e) >= Layer.GLOBAL_MANUAL` = manual (đã chuẩn hóa 3.2 qua `_entry_layer`).

### DDL candidate_evidence (v6)

```sql
CREATE TABLE IF NOT EXISTS candidate_evidence (
    id TEXT PRIMARY KEY,             -- sha256(book_id \x00 drev \x00 candidate_id \x00 group_name)
    candidate_id TEXT NOT NULL,
    book_id TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL,
    group_name TEXT NOT NULL,        -- strength|stability|benefit|risk|scope|regression
    signals_json TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.0, -- chi xep hang, khong gate (AD-7)
    created_at TEXT NOT NULL,
    UNIQUE(candidate_id, group_name)
);
CREATE INDEX IF NOT EXISTS idx_evidence_scope
    ON candidate_evidence(book_id, dictionary_revision_id);
```

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Candidates + observations | `SELECT ... FROM term_candidates` / `observations` WHERE book_id + drev | state.py |
| Trie walk / layer | `_trie_entries`, `_entry_layer` (import từ learning.candidate — public-ish cùng package) | `learning/candidate.py` |
| Lock + dictionary setup | `_learn_context` trong cli | `cli.py` |

### Phạm vi KHÔNG làm

- Không promotion/gates/revision build (3.4).
- Không regression signals thật (3.4 populate sau isolation rerun).
- Không cross-book/genre metadata (Epic 4; `books: 1` hardcoded, `genre: null`).
- Không đổi behavior `zhvi discover`.

### Previous story intelligence (3.2)

- Comments Việt không dấu; imports top; lint hook chặn F401 từng bước — imports + usage cùng edit.
- Edit tool khó match chuỗi chứa CJK range regex — edit tránh đụng dòng đó.
- Test fixture `_learned` pattern sẵn dùng.
- Suite baseline 206 passed / 2 skipped.

### Project Structure Notes

- `learning/evidence.py` mới; test `tests/test_evidence.py` mới.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3 (lines 304–316)]
- [Source: thiet-ke-he-thong-dich-truyen-zh-vi.md#Bước-5-tính-evidence (lines 197–210)]
- [Source: ARCHITECTURE-SPINE.md — AD-7, AD-8]
- [Source: zhvi/src/zhvi/learning/candidate.py — _trie_entries/_entry_layer/provenance shape]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_evidence.py RED (EvidenceRow import fail) → GREEN.
- Test design поправлено giữa chừng: fixture có ChinesePhienAmWords nên 李慕白 là fragmented run (is_single_char_run=1), không phải unknown — benefit assert đổi sang `reduces_single_char`; observation giả manual-conflict phải chung source revision gốc (rev riêng làm obs-map "mới nhất" che mất obs thật).

### Completion Notes List

- Evidence map dùng observation của source revision MỚI NHẤT cho dictionary revision — theo `source_revisions.created_at DESC` (review fix: rowid là thứ tự insert không phải recency), nhiều source revision cùng drev không nhân đôi evidence.
- `manual_conflict` semantics: overlap SPAN (manual key là prefix của candidate key — prefix-path check; hoặc candidate key là prefix của manual key — DFS extension depth ≤ 8). Builder 3.2 đã loại key trùng chính xác; evidence bắt overlap chéo — đúng AC 3. Tên hàm `_span_manual_conflict` (review fix: tránh đụng tên `_manual_conflict` của builder — khác semantics).
- `scope.books = 1` hardcoded (book scope; cross-book Epic 4); `genre: null` (chưa metadata).
- `regression` group là placeholder `{"deferred": "story-3.4"}` — populate sau isolation rerun ở promotion (AC 2: không phụ thuộc output).
- UNIQUE(candidate_id, group_name) an toàn vì candidate_id content-addressed theo (book, drev, key).
- Evidence ghi cho MỌI candidate kể unresolved (người duyệt cần thấy tín hiệu).
- **Review fixes (2 trục, 11 findings — tất cả đã xử lý):** type hints đủ (`_walk` return, `_has_extension` Callable, obs-map dict); rename `_span_manual_conflict`; promote `trie_entries`/`entry_layer` public trong candidate.py (hết private import chéo module); extract `_row(cand, group, signals, score)` nội bộ; `_single_target` dùng `all()`; bỏ `_GROUPS` unused; helper `cursor_dicts` trong state.py thay 5 chỗ `dict(zip(...))`; risk thêm `target_ambiguity` (đủ 4 tín hiệu thiết kế bước 5); `reduces_fragmentation` tách khỏi `alt_segmentation` (hết double-count); test thêm unknown thật (`未知语` unresolved vẫn có benefit `reduces_unknown=1` dương).

### File List

- zhvi/src/zhvi/state.py (sửa: SCHEMA_VERSION 6, DDL candidate_evidence + index, EvidenceRow, _EV_COLS, replace_evidence, helper cursor_dicts)
- zhvi/src/zhvi/learning/evidence.py (mới)
- zhvi/src/zhvi/learning/candidate.py (sửa: promote trie_entries/entry_layer public, dùng cursor_dicts)
- zhvi/src/zhvi/cli.py (sửa: learn gọi evaluate_candidates, JSON thêm evidence)
- zhvi/tests/test_evidence.py (mới)
- zhvi/tests/test_cli.py (sửa: test_learn_command_json thêm assert evidence)
- zhvi/tests/test_state.py (sửa: migrate assert version 6)
- zhvi/tests/test_candidate.py (sửa: schema assert >= 5)

## Change Log

- 2026-09-05: Story 3.3 implementation — bảng candidate_evidence (schema v6), evaluate_candidates 6 nhóm tín hiệu từ observations + dictionary, CLI learn wire evidence.
- 2026-09-05: Review fixes (11 findings) — obs-map theo created_at, risk đủ target_ambiguity, promote helpers public, _row/cursor_dicts extract, hết double-count benefit.
