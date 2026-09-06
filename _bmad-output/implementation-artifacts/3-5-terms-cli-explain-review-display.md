---
baseline_commit: dab0380
---

# Story 3.5: Terms CLI + explain/review display

Status: done

## Story

As a người duyệt candidate,
I want `zhvi terms list/accept/reject/revoke` và `zhvi explain TEXT` hiển thị source span, segmentation trace, entry/layer/revision của từng target span, candidate liên quan, affected blocks,
So đó quyết định sửa gì dựa trên trace đầy đủ thay vì đoán.

## Acceptance Criteria

1. **Given** project có candidate/auto entry **When** chạy terms list/accept/reject/revoke và explain **Then** list hiển thị candidate/evidence/trạng thái; accept tạo manual entry (từ đó manual thắng auto); reject ghi audit event; revoke như Story 3.4.
2. Explain hiển thị segmentation + provenance từng span (entry id, layer, revision) và các block khác sẽ đổi nếu đổi entry.
3. Mọi lệnh có audit event; test CLI full vòng: list → accept → translate đổi output đúng chỗ.

## Tasks / Subtasks

- [x] Task 1: `learning/terms.py` — list/accept/reject (AC: 1)
  - [x] `list_terms(state, *, book_id, drev=None, status=None)` → list dict: candidate (source, target, kind, status, eligible_auto, provenance) + evidence groups (từ `candidate_evidence`) + đếm events theo source; drev mặc định = drev của candidates mới nhất theo rowid; sort theo source
  - [x] `accept_term(state, *, project, dict_dir, cfg, source)` (AC: 1):
    1. Tìm candidate của book theo source (mới nhất theo rowid) — không có → `TermsError`; source đã có manual entry (trie entries `_entry_layer >= GLOBAL_MANUAL`) → `TermsError` (đã manual)
    2. Target = `proposed_target`; candidate unresolved (target rỗng) → `TermsError` (không có gì để accept)
    3. Append dòng `source=target` vào `project.manual_glossary` (tạo file nếu chưa có; NFC; append + flush + fsync — KHÔNG qua `atomic_write` vì file human-owned, guard chặn; đây là lệnh user-directed, comment giải thích AD-5: learner không ghi, CLI thực thi ý người)
    4. Publish revision mới với autos hiện tại (`_current_auto_entries` semantics như promotion.py — extract dùng chung hoặc re-implement qua `read_bundle_entries`): `publish_revision(dict_dir, project, autos, expected_active=active)`
    5. Event `accepted` (promotion_events, actor `user`, from status cũ → `accepted`); UPDATE status → `accepted`; feedback_events row action `terms_accept`
  - [x] `reject_term(state, *, book_id, source, drev)` — chỉ cho status `candidate`/`unresolved`/`accepted`? KHÔNG: book_auto phải đi revoke. Status `book_auto` → `TermsError` hướng dẫn revoke. Event `rejected` actor `user` + status → `rejected`; feedback_events row action `terms_reject`
- [x] Task 2: `revoke_book_auto` nhận actor + `terms revoke` wire (AC: 1)
  - [x] `promotion.py`: `revoke_book_auto(..., actor: str = "system")`; `_event` helper thêm param `actor` (mặc định "system" giữ call sites cũ)
  - [x] `terms revoke` CLI gọi `revoke_book_auto(actor="user")` + feedback_events row action `terms_revoke`
- [x] Task 3: `learning/explain.py` — `explain_text(...)` (AC: 2)
  - [x] Đầu vào: text (đoạn ZH); resolve dictionary active như `_learn_context` (open_project + ensure_book_dictionary — KHÔNG cần source revision cho explain; nhưng affected blocks CẦN source → dùng `latest_source_revision`, không có thì `affected_blocks: []` kèm note)
  - [x] `vp_plan(dic, text, beam=cfg.lattice_beam, occurrence_prefix="explain", collapse_reps=cfg.collapse_repetitions)` → draft
  - [x] Mỗi span trong `draft.spans`: `{source, target, source_start, source_end, policy, entry_version_id, alternatives, layer}` — layer tra qua `trie_entries(dic, span.source)` + `entry_layer` (public, candidate.py); entries nếu nhiều layer thì list hết `[{layer, target}]`
  - [x] Unknown spans: `draft.unknown_spans` → list `{start, end, text}`
  - [x] `candidates`: candidates của book có `source` bằng hoặc là substring của bất kỳ span source / xuất hiện trong text (query `term_candidates` mọi status; match bằng `source in text`)
  - [x] `affected_blocks`: `affected_block_ids(doc, {span sources}, dic.trad_simp)` — các block sẽ đổi nếu đổi entry
  - [x] `revision`: active revision id (mọi span cùng revision — run pin)
  - [x] feedback_events row action `terms_explain` (AC 3: audit mọi lệnh)
- [x] Task 4: CLI — `terms_app` typer + `explain` command (AC: 1–3)
  - [x] `terms_app = typer.Typer(help="Candidate/auto entry lifecycle: list/accept/reject/revoke.")`; `app.add_typer(terms_app, name="terms")`
  - [x] `terms list --project -p [--status] [--dict-dir]` → JSON list; feedback_events row `terms_list`
  - [x] `terms accept SOURCE --project -p --dict-dir` → JSON `{source, target, revision, manual_glossary}`; project_lock
  - [x] `terms reject SOURCE --project -p` → JSON `{source, status}`; project_lock
  - [x] `terms revoke SOURCE --project -p --dict-dir` → JSON `{source, revision}`; gọi revoke actor user
  - [x] `explain TEXT --project -p --dict-dir` → JSON explain payload (top-level command, không thuộc terms_app)
  - [x] `StaleActiveError` → EXIT_RUN_FAILED; `TermsError` → EXIT_STATE; lỗi chung như pattern learn
- [x] Task 5: Tests `tests/test_terms.py` (AC: 1–3)
  - [x] AC1 list: sau `_learned` fixture (pattern test_promotion) — list có 李慕白 với đủ groups + status candidate; `--status book_auto` filter sau promote
  - [x] AC1 accept: accept 李慕白 → glossary.manual.tsv có dòng; revision mới active; event accepted actor user; candidate status accepted; promote lại không đổi (manual thắng — auto_targets vẫn match hoặc candidate bị skip vì manual); translate `refresh_revision=True` cho target manual trong output
  - [x] AC1 accept edge: accept key không tồn tại → TermsError; accept key đã manual → TermsError; accept unresolved → TermsError
  - [x] AC1 reject: reject candidate → event rejected actor user + status rejected; reject book_auto → TermsError
  - [x] AC1 revoke CLI: sau promote, `terms revoke` → như test 3.4 + actor user trong event
  - [x] AC2 explain: JSON có spans (layer đúng — span 李慕白 layer BOOK_AUTO sau promote; layer GLOBAL_MANUAL cho 看着), unknown_spans, candidates chứa key, affected_blocks đúng tập block chứa span, revision = active
  - [x] AC3 feedback_events có row cho list/accept/reject/revoke/explain
  - [x] CLI full vòng (test_cli.py): init → import → learn → terms list (JSON có candidate) → terms accept → translate --refresh-revision → output chứa target manual
  - [x] Regression: full suite xanh — baseline 224 passed / 2 skipped

## Dev Notes

### Invariants ràng buộc

- **AD-5** — `terms accept` là lệnh NGƯỜI DÙNG chủ động thực thi qua CLI (actor=user trong event); learner không tự ghi file human-owned. Append glossary.manual.tsv bằng append thường + fsync, KHÔNG dùng `atomic_write`/`_write_synced` (guard `assert_machine_writable` chặn `glossary.manual.tsv` — đúng, vì những writer đó cho projection). Comment trong code phải nêu rõ phân biệt này.
- **AD-2** — mọi correction đi qua dictionary: accept = manual entry + revision mới; KHÔNG sửa block text.
- **AD-12** — revoke như 3.4 (revision mới chỉ bỏ key); actor user.
- **AD-8** — mutation ghi event append-only promotion_events; lệnh read-only (list/explain) ghi usage audit vào `feedback_events` (bảng có sẵn action/segment_id/candidate_id/entry_id/before_json/after_json — dùng action + candidate_id khi có).
- **AD-13** — terms accept/revoke giữ `project_lock(p)` + publish lock riêng như learn (đã verify không deadlock ở 3.4).
- **AD-15** — accept publish revision mới qua `publish_revision` (manual layer hash mới → revision id mới — cùng machinery correction 2.5).

### accepted semantics (quyết định story)

- Status mới `accepted` trong `term_candidates.status` (cột TEXT — không migration).
- Sau accept, entry sống trong glossary.manual.tsv (layer BOOK_MANUAL) → precedence thắng auto (AD-5). Auto entry cùng key (nếu có từ trước) vẫn nằm trong bundle nhưng renderer chọn manual theo layer — không cần xóa auto entry.
- Learn chạy lại: builder 3.2 loại candidate trùng manual key → candidate không tái sinh; nếu tái sinh (edge) thì promotion skip vì `_span_manual_conflict` risk → gate no_manual_conflict fail → rejected — an toàn.
- Reject không áp cho `book_auto` (đó là revoke); reject trên `accepted` cho phép (đổi ý → status rejected, glossary vẫn còn dòng manual — xóa dòng là việc người dùng sửa file, ngoài scope).

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Candidates + evidence + events | SELECT `term_candidates` / `candidate_evidence` / `promotion_events` + `cursor_dicts` | state.py |
| Auto entries hiện tại | `read_bundle_entries(project, revision_id)` filter BOOK_AUTO+book | projection.py |
| Publish revision mới | `publish_revision(dict_dir, project, autos, expected_active=active)` | revision.py |
| Revoke | `revoke_book_auto(state, project=..., dict_dir=..., source=...)` (3.4; cần thêm param actor) | learning/promotion.py |
| Event row | `_event` helper promotion.py (cần param actor) + `state.append_promotion_event` | learning/promotion.py |
| Trie layer tra cứu | `trie_entries(dic, key)`, `entry_layer(entry)` (public từ 3.3) | learning/candidate.py |
| Render + trace | `vp_plan(dic, text, beam, occurrence_prefix, collapse_reps)` → `VpDraft(spans, unknown_spans, ...)`; `VpSpan` fields: occurrence_id, source_start/end, source, target, alternatives, entry_version_id, policy, path_score | vietphrase/lattice.py, vietphrase/trace.py |
| Affected blocks | `affected_block_ids(doc, keys, trad_simp)` | correction.py |
| Dictionary active | `_learn_context` pattern (cli.py) — extract phần chung nếu gọn, KHÔNG bắt buộc refactor | cli.py |
| Usage audit | INSERT `feedback_events(id, action, segment_id, candidate_id, entry_id, before_json, after_json)` | state.py DDL |
| Manual layer check | `trie_entries` + `entry_layer(e) >= Layer.GLOBAL_MANUAL` | learning/candidate.py, layers.py |

### Explain — lưu ý shape

- `VpSpan` KHÔNG có layer — tra qua `trie_entries(dic, span.source)` (mỗi entry có precedence tuple; `entry_layer` lấy int). Nhiều entries cùng key (đa layer) → list hết.
- Span source là BẢN GỐC (phồn thể) — key trie là giản thể NFC; khi tra layer dùng `to_simplified(span.source, dic.trad_simp)` nếu khác.
- `occurrence_prefix="explain"` — không reuse block prefix.
- Text rỗng / không CJK → spans rỗng, không crash.

### CLI conventions (giữ nguyên pattern)

- JSON stdout (ensure_ascii=False), log stderr qua `err_console`, lỗi qua `_fail(EXIT_*)`.
- `terms_app` đặt cạnh `dict_app`; `explain` top-level.
- Mỗi command: try/except pattern như `learn` (typer.Exit re-raise, ProjectError, cuối cùng controller bắt fatal).

### Phạm vi KHÔNG làm

- Không xóa/dedupe dòng glossary.manual.tsv; không editor tương tác.
- Không đổi promotion gates / builder / discovery / evidence.
- Không cross-book/global (Epic 4).
- Không web UI/API.

### Previous story intelligence (3.4)

- Comments Việt không dấu; imports top; lint hook chặn F401/F841 từng edit — imports + usage cùng edit, hoặc append body cùng lúc.
- Edit tool khó match chuỗi chứa CJK — edit tránh đụng dòng đó.
- Fixture `_learned` (translate + discovery + candidates + evidence) tái dùng từ test_promotion.py — copy hoặc import helper.
- Promotion batch: nhiều candidates promote cùng lúc — test asserts dùng `>=`.
- Event log (không status) là nguồn idempotency — rejected cùng drev không lặp event.
- Suite baseline 224 passed / 2 skipped.

### Project Structure Notes

- `learning/terms.py` mới; `learning/explain.py` mới; test `tests/test_terms.py` mới.
- `state.py` sửa (feedback_events append helper nếu cần `append_feedback(action, candidate_id=...)`); `learning/promotion.py` sửa (actor param); `cli.py` sửa (terms_app + explain).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.5 (lines 333–345)]
- [Source: ARCHITECTURE-SPINE.md — AD-2, AD-5, AD-8, AD-12, AD-13, AD-15]
- [Source: data-model.md — layer table, feedback_events, mutation event]
- [Source: zhvi/src/zhvi/learning/promotion.py — _event/_current_auto_entries/revoke_book_auto]
- [Source: zhvi/src/zhvi/fsutil.py — ownership guard (glossary.manual.tsv human-owned)]
- [Source: zhvi/src/zhvi/review.py — CLI-facing store pattern]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_terms.py RED (ImportError learning.terms / explain) → GREEN từng task.
- feedback_events có cột created_at NOT NULL — _audit phải ghi utc_now().
- trie_entries trả entry TUPLES (target, precedence, policy) — không phải object; entry_layer(e) = e[1][0].
- Renderer tách unknown run thành từng ký tự đơn — test unknown join các text thay vì contiguous.
- CLI full vòng: join-con target trùng render singles (renderer space-separator) nên phải UPDATE proposed_target khác ("Lý Mộ Bạch Đại Hiệp") trước accept để chứng minh output đổi đúng chỗ.

### Completion Notes List

- `terms accept`: user-directed append vào glossary.manual.tsv (append + fsync, KHÔNG qua atomic_write — guard chặn file human-owned; AD-5: learner không ghi, CLI thi hành lệnh người) → publish_revision với autos hiện tại (manual layer hash mới → revision mới) → event `accepted` actor user + status `accepted` + feedback_events `terms_accept`.
- Guard accept: không candidate / unresolved (target rỗng) / key đã có manual entry (trie layer >= GLOBAL_MANUAL) → TermsError.
- `reject`: chỉ candidate chưa book_auto (book_auto phải revoke); event rejected actor user + feedback `terms_reject`. Reject trên `accepted` cho phép (glossary giữ dòng — xóa là việc người sửa file).
- `revoke`: reuse revoke_book_auto (3.4) với actor param mới "user" + feedback `terms_revoke`; promotion._event / current_auto_entries mở public cho terms reuse.
- `explain`: vp_plan trên dictionary active; mỗi span: entries tra qua trie_entries + entry_layer (list mọi layer cùng key), unknown spans (ký tự đơn), candidates match `source in text`, affected_blocks qua affected_block_ids trên source revision mới nhất, revision id active; feedback `terms_explain`.
- Audit mọi lệnh (AC 3): mutation → promotion_events (lifecycle, actor); list/explain → feedback_events usage audit (audit_usage public).
- CLI: terms_app (list/accept/reject/revoke) + explain top-level; project_lock cho accept/reject/revoke; StaleActiveError → EXIT_RUN_FAILED, TermsError/PromotionError → EXIT_STATE.
- Đã chấp nhận: accept target join-con thường trùng render hiện tại (chỉ segmentation đổi) — "đổi output đúng chỗ" test qua target đè khác.
- **Review fixes (2 trục, 19 findings — tất cả đã xử lý):** HIGH — bỏ assert luôn-đúng `or True` (test unknown spans). MED — `list_terms` thêm `provenance` + đếm `events` theo source (GROUP BY); test double-accept thay cho tautological manual-guard test (builder không sinh candidate cho key manual); test revoke CLI asserts đủ (revision mới, event actor user, key rời BOOK_AUTO, feedback terms_list/terms_revoke); `promotion_event` đổi public + `current_auto_entries` vào `__all__` (hết import private chéo); `dict_dir: Path` annotation; audit terms_revoke chuyển vào project_lock (list/explain audit ngoài lock kèm comment — read-only). LOW — pre-check duplicate dòng glossary trước append (retry sau StaleActiveError không nhân đôi); explain docstring chính xác (không phải read-only tuyệt đối); `_latest_candidate` LIMIT 1; audit_usage keyword-only; `terms list --dict-dir`; accept JSON thêm target (accept_term trả tuple); explain dùng `_terms_state`; format/blank line; test imports top hết; explain `affected_note` khi không source revision + test.

### File List

- zhvi/src/zhvi/learning/terms.py (mới)
- zhvi/src/zhvi/learning/explain.py (mới)
- zhvi/src/zhvi/learning/promotion.py (sửa: _event thêm actor param, revoke_book_auto thêm actor, current_auto_entries public)
- zhvi/src/zhvi/cli.py (sửa: terms_app list/accept/reject/revoke + explain + imports)
- zhvi/tests/test_terms.py (mới)

## Change Log

- 2026-09-05: Story created — ultimate context engine analysis completed.
- 2026-09-05: Story 3.5 implementation — learning/terms.py (list/accept/reject + audit), learning/explain.py, promotion actor param, CLI terms_app + explain, 7 test mới.
- 2026-09-05: Review fixes (19 findings, 2 trục Opus) — provenance/events trong list, double-accept guard test, revoke asserts, promotion_event public, glossary duplicate pre-check, affected_note + 1 test mới (8 total).
