---
baseline_commit: da916ba8487f608f949d1fd9de7921fd5de6b16f
---

# Story 5.1: QA structural gates + run report metric

Status: done

## Story

As a người dùng cần bản dịch đáng tin,
I want QA chỉ pass hoặc chặn export (đủ block đúng thứ tự, không duplicate/missing, structural span dựng lại được, không placeholder nội bộ, CJK residue trong policy, không artifact lặp, entity nhất quán theo revision, output hash + manifest khớp) và run report metric riêng lẻ,
So đó không có hidden repair và chất lượng đo được bằng con số kiểm chứng.

## Acceptance Criteria

1. QA fail → run `needs_dictionary_fix`, không export, không sửa output; QA pass mới export atomic.
2. Run report: dictionary_revision_id, coverage (ký tự + span), unknown spans, single-char ratio, fragmentation, candidate count theo trạng thái, entry auto dùng, affected blocks, regression pass/fail, output SHA-256, elapsed + chars/s — không quality score tổng hợp.
3. Test fixture từng loại QA fail tương ứng.

## Tasks / Subtasks

- [x] Task 1 — `zhvi/src/zhvi/quality/export_qa.py` (AC: #1, #3)
  - [x] 1.1 `QaFailure(RuntimeError)` + `ExportQaResult(ok, errors: list[str], metrics: dict)`
  - [x] 1.2 `run_export_qa(doc, output_text, blocks_by_id) -> ExportQaResult` — không sửa `output_text`. Gates (fail một = fail):
    - `duplicate_ids` / `missing_blocks` / `newline_mismatch` — reuse logic `export.verify_output` (bắt IntegrityFailure → error code)
    - `placeholder` — output chứa token nội bộ (`__ZHVI`, `\ufffc`)
    - `leftover_cjk` — CJK trong output ngoài allowlist rỗng (cùng `CJK_RE` invariants)
    - `repeated_artifact` — cùng cụm ≥2 ký tự lặp liền (`(\S{2,})\1`)
    - `entity_drift` — `chapter_audit.entity_alias_consistency` khi caller truyền `entity_targets`; rỗng → skip
  - [x] 1.3 Không hidden repair: hàm không trả output khác input
- [x] Task 2 — Pipeline chặn export (AC: #1, #2)
  - [x] 2.1 Sau khi mọi block committed, `build_output` in-memory → `run_export_qa`. Fail: `set_run_status(needs_dictionary_fix)`, KHÔNG gọi `export_run`, `PipelineResult.exit_code=9` (EXIT_INTEGRITY), `report["output"]=None`, `report["qa"]=errors`
  - [x] 2.2 Pass: `export_run` như hiện tại; report thêm metric (Task 3). `find_completed_run` không coi `needs_dictionary_fix` là xong (đã vậy — chỉ completed/exported)
  - [x] 2.3 Invariant per-block giữ nguyên (không sửa VP draft). Gate export là lớp document
- [x] Task 3 — Run report metric (AC: #2)
  - [x] 3.1 `build_run_report(...)` gom: `dictionary_revision_id`, `coverage_chars`, `coverage_spans` (từ qa json blocks: coverage / unknown_spans / single_char_ratio trung bình), `unknown_spans` tổng, `single_char_ratio`, `fragmentation` (= single_char_ratio nếu không có field riêng), `candidates` `{status: count}` từ term_candidates, `auto_entries` số BOOK_AUTO trong active revision, `affected_blocks` [] (không correction), `regression` `"pass"|"fail"|"n/a"`, `sha256` (None nếu chưa export), `elapsed_s`, `chars_per_s`. Cấm key `quality_score` / `score`
- [x] Task 4 — Tests `zhvi/tests/test_export_qa.py`
  - [x] 4.1 Từng gate fail: placeholder / leftover_cjk / missing / newline / repeated_artifact → `ok=False`, đúng error code
  - [x] 4.2 Happy: output sạch → ok, không sửa text
  - [x] 4.3 Pipeline: inject placeholder vào block committed (monkeypatch `vp_plan` hoặc stage) → status `needs_dictionary_fix`, file output không tồn tại
  - [x] 4.4 Report pass path có đủ key AC #2, không `quality_score`
- [x] Task 5 — Full suite + ruff. Sửa test cũ CHỈ nếu chúng kỳ vọng export khi leftover CJK (comment 5.1 đổi gate)

## Dev Notes

- CAP-7 / pipeline-contract mục 9: QA không sửa văn bản.
- `verify_output` + `build_output` đã có; 5.1 thêm lớp document-level + chặn export.
- Per-block leftover CJK hiện chỉ warning — 5.1 nâng thành chặn export. Mini dict test phải cover CJK hoặc fail sẽ lộ.
- Không đụng golden.py / global_promotion.

## Phạm vi KHÔNG làm

- Không 5.3 metamorphic. Không 5.4 E2E docs. Không sửa output khi fail.

## Dev Agent Record

### Agent Model Used

Grok 4.6

### Debug Log References

- leftover_cjk chan export: 5 test preprocess/projection fail → them entry QO (第一章/他/从天而降) dung quyen sua test cu.
- Full suite: 291 passed / 2 skipped (271 + 8 QA + 12 metamorphic/dict).

### Completion Notes List

- `quality/export_qa.py`: document-level gates, khong sua output. Fail → `needs_dictionary_fix`, khong `export_run`.
- Report metric roi, khong `quality_score`.
- 5.3 chay song song worktree: `test_metamorphic.py` + `test_dictionary_units.py` (12 test).

### File List

- zhvi/src/zhvi/quality/export_qa.py
- zhvi/src/zhvi/pipeline.py
- zhvi/tests/test_export_qa.py
- zhvi/tests/test_preprocess.py
- zhvi/tests/test_projection.py
- zhvi/tests/test_metamorphic.py
- zhvi/tests/test_dictionary_units.py
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-09-06: Story created + implemented.
- 2026-09-06: QA export gate + run report; 5.3 tests merged from worktree.
- 2026-09-06: Review fixes (7 fix / 5 skip) — IntegrityFailure.code, coverage_chars, hash/manifest, tautology AC 1.3.
