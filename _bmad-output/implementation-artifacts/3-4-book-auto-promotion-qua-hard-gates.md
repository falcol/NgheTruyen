---
baseline_commit: ed3969a
---

# Story 3.4: Book-auto promotion qua hard gates

Status: done

## Story

As a hệ thống học theo truyện,
I want candidate promote lên `book_auto` chỉ khi pass hard gates (ngưỡng occurrence/chapter, target stability 100%, không manual conflict, coverage/fragmentation cải thiện, structural invariant pass, affected-block isolation pass),
So đó auto entry an toàn cho truyện và rollback được.

## Acceptance Criteria

1. **Given** candidate có evidence **When** đánh giá promotion **Then** lifecycle `observed → candidate → book_auto` (kèm `unresolved`, `rejected`, `revoked`) ghi event append-only (before/after/actor/timestamp/provenance).
2. Gate fail một mục là reject, điểm cao không bù; promotion ghi `glossary.auto.tsv` (projection, qua revision builder) và chỉ ảnh hưởng truyện đó.
3. Số block thay đổi đúng tập block chứa candidate (isolation test).
4. Revoke một book-auto entry build revision mới và chỉ đổi affected blocks.

## Tasks / Subtasks

- [x] Task 1: Migration v6 → v7 — bảng `promotion_events` (AC: 1)
  - [x] `state.py`: `SCHEMA_VERSION = 7`; DDL mới trong `_SCHEMA`; `_migrate` comment nhánh v6→v7 (bảng CREATE IF NOT EXISTS — additive)
  - [x] `PromotionEventRow` dataclass + method `append_promotion_event(row)` (INSERT thuần — append-only, KHÔNG replace) + `promotion_events_for(book_id, source=None)` đọc lại cho CLI/test
- [x] Task 2: `learning/promotion.py` — gates + `run_promotion` + `revoke_book_auto` (AC: 1–4)
  - [x] `_evidence_map(state, book_id, drev)` → `{candidate_id: {group: signals}}` từ `candidate_evidence`
  - [x] `_evaluate_gates(cand, ev, cfg)` → list `GateResult(name, passed, detail)`; gates từ evidence (AD-7: điểm KHÔNG tham gia — chỉ signals):
    - `min_occurrences`: `strength.total_count >= cfg.learning.min_term_occurrences` AND `scope.chapter_count >= cfg.learning.min_chapters`
    - `target_stability`: `stability.single_target == 1` AND `stability.same_segmentation == 1` (100%)
    - `no_manual_conflict`: `risk.manual_conflict == 0`
    - `benefit_positive`: tổng benefit signals (`reduces_unknown + reduces_single_char + reduces_fragmentation`) > 0
    - điều kiện vào đánh giá: `status='candidate'` AND `eligible_auto=1` (builder 3.2)
  - [x] Idempotency: candidate có `(source, target)` trùng auto entry hiện có của active revision → skip (đã promoted, không lặp event)
  - [x] `run_promotion(state, project, dict_dir, cfg, dic, drev)`:
    1. Gates từng candidate; fail bất kỳ gate → event `rejected` (from `candidate` to `rejected`, provenance chứa gates fail) + UPDATE status
    2. Tập pass rỗng → return summary (không build)
    3. Auto hiện tại: `read_bundle_entries(project, active)` filter layer `BOOK_AUTO`+scope `book` → `AutoEntry`; thêm entries mới (scope `"book"`)
    4. `build_revision(dict_dir, project, autos)` — build trước, CHƯA CAS activate
    5. Isolation check (xem `_isolation_check` dưới) trên revision mới; fail → mọi candidate pass gates bị event `rejected` (gate `isolation`), KHÔNG activate (AC 2: fail một mục là reject)
    6. Pass → `publish_revision(..., expected_active=active)` (CAS; bundle content-addressed nên lần 2 reuse — StaleActiveError để CLI bắt)
    7. Event `promoted` cho từng candidate (from `candidate` to `book_auto`, actor `system`, `revision_id` mới, provenance = gates + snapshot signals); UPDATE status → `book_auto`
    8. Populate regression evidence (xem dưới)
  - [x] `_isolation_check(state, project, cfg, dic_new, keys)` (review: bo `dic_old` — tham so khong dung):
    - doc = parse source revision mới nhất; affected = `affected_block_ids(doc, keys, dic_new.trad_simp)`
    - baseline = `latest_completed_run_for_source` → `committed_blocks(run_id)`; mỗi node: render mới qua `vp_plan(dic_new, sanitize_source(...))` (đúng cfg `qa_strip_junk`/`collapse_repetitions`/`lattice_beam` như pipeline); block khác baseline = changed
    - Pass khi mọi changed ∈ affected; KHÔNG có baseline (chưa translate lần nào) → pass với detail `no_baseline`
    - Structural invariant (AD-20): `run_invariants(source, output, block_id)` cho MỌI block changed — fail bất kỳ → gate structural_invariant fail
    - Trả `(passed, changed_block_ids, invariant_errors)` — đầu vào cho regression signals
  - [x] Populate regression evidence (AC từ 3.3 deferred): state method mới `replace_evidence_group(book_id, drev, group, rows)` (delete + insert CHỈ group đó — không đụng 5 group kia); ghi group `regression` cho candidates promoted với signals thật: `{changed_blocks, affected_blocks, invariant_errors, structural_invariant_pass, isolation_pass, baseline_run}` — hết placeholder `deferred`
  - [x] `revoke_book_auto(state, project, dict_dir, source_key)` (review: bo `cfg` — khong dung) (AC: 4):
    1. Auto hiện tại từ active bundle; key không có → error
    2. autos mới = hiện tại trừ key; `publish_revision(expected_active=active)` — AD-12: revision mới, không sửa bundle cũ
    3. Event `revoked` (from `book_auto` to `revoked`, actor mặc định `system` — 3.5 CLI user); UPDATE candidate status → `revoked`
    4. Chỉ affected blocks đổi: verify qua `diff_revisions(old, new).affected_keys == {source_key}` (auto entries khác giữ nguyên)
    5. API-only trong story này; CLI `terms revoke` là 3.5
- [x] Task 3: CLI — `zhvi learn` thêm bước promotion (cùng lock, sau evaluate) (AC: 2)
  - [x] JSON thêm `"promotion"`: summary (promoted/rejected/skipped, revision cũ/mới, changed blocks)
  - [x] `StaleActiveError` → exit `EXIT_RUN_FAILED` như correction flow
  - [x] Guard `cfg.learning.enabled` (mặc định True) và `cfg.learning.auto_scope == "book"` (global là Epic 4)
- [x] Task 4: Tests `tests/test_promotion.py` (AC: 1–4)
  - [x] AC1: promote tạo events append-only đủ field (before/after/actor/timestamp/provenance); chạy promotion 2 lần cùng state → không nhân đôi event (idempotent skip)
  - [x] AC2: fixture candidate đủ mọi gate TRỪ chapter_count (score strength cao) → `rejected`, không có entry trong bundle/projection; candidate đủ hết → promoted, `glossary.auto.tsv` có `source=target`, manifest có layer `auto:book`, `dict_dir` không bị ghi (scope book)
  - [x] AC3: isolation — có baseline run; sau promote: block chứa key đổi, block ngoài tập giữ NGUYÊN final_text; changed == tập affected
  - [x] AC4: revoke — active revision mới ≠ cũ; `diff_revisions` affected đúng key; render block ngoài key identical; event `revoked` có revision_id mới
  - [x] Regression evidence: sau promote, group `regression` của candidate promoted có signals thật (không `deferred`)
  - [x] test_state: migrate assert version 7; test_cli: `learn` JSON có `promotion`
  - [x] Regression: full suite xanh — baseline 213 passed / 2 skipped

## Dev Notes

### Invariants ràng buộc

- **AD-7 / AC 2** — hard gates: fail MỘT gate là reject. Score chỉ xếp hạng, KHÔNG bao giờ bù gate. Gates đọc signals thô, không đọc score.
- **AD-20** — book-auto bắt buộc: deterministic single target, không manual conflict, structural QA pass, affected-block isolation pass; ngưỡng thống kê là CONFIG (`min_term_occurrences=5`, `min_chapters=2` đã có trong `LearningConfig` — KHÔNG thêm field mới).
- **AD-12 / AC 4** — revoke là revision MỚI (tập entry bớt key); bundle cũ giữ nguyên read-only.
- **AD-15** — build temp → CAS active; promotion dùng đúng `build_revision` (dry-run) + `publish_revision(expected_active=...)` có sẵn. Content-addressed: build lần 2 cùng tập entry → reuse bundle.
- **AD-13** — chạy trong `project_lock(p)` của CLI `learn` (mặc định `"translate"`); `publish_revision` tự lấy lock `"publish"` riêng. Đã verify `project.py`: lock theo file `{name}.lock` — hai TÊN khác nhau là hai file khác nhau, acquire lồng nhau cùng process không deadlock (giữ pattern `dict_rollback` đang dùng).
- **AD-4** — LEARN kết thúc bằng revision ready/active; translate chỉ đọc. Promotion đổi active revision ở cuối flow learn — đúng pha.
- **AD-6** — chỉ candidate `eligible_auto=1` được đánh giá; builder đã lọc target mơ hồ.
- **AD-8 / data-model** — "Mọi mutation candidate/entry/revision ghi event append-only gồm before, after, actor, timestamp, provenance". `promotion_events` KHÔNG dùng replace-not-append (khác observations/candidates/evidence).
- **AC 2 "chỉ ảnh hưởng truyện đó"** — AutoEntry scope `"book"` → layer BOOK_AUTO; projection `glossary.auto.tsv` nằm trong project root. KHÔNG materialize `AutoVietPhrase.txt` (global, Epic 4).

### DDL promotion_events (v7)

```sql
CREATE TABLE IF NOT EXISTS promotion_events (
    id TEXT PRIMARY KEY,             -- uuid4 hex (data-model: UUID cho event)
    book_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,            -- normalized key (NFC + giản thể)
    event_type TEXT NOT NULL,        -- rejected | promoted | revoked
    from_status TEXT NOT NULL DEFAULT '',
    to_status TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL,             -- system | user
    dictionary_revision_id TEXT NOT NULL DEFAULT '',
    revision_id TEXT NOT NULL DEFAULT '',  -- bundle moi (promoted/revoked)
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_promotion_events_book
    ON promotion_events(book_id, source, created_at);
```

Lifecycle đầy đủ `observed → candidate → ...`: trạng thái `observed`/`candidate` do discovery/builder ghi (bảng riêng, không event) — events bắt đầu từ quyết định promotion (`rejected`/`promoted`/`revoked`). Candidate status mới trong `term_candidates.status`: thêm `book_auto`, `rejected`, `revoked` (cột TEXT đã mở, không cần migration).

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Auto entries hiện tại | `read_bundle_entries(project, revision_id)` filter `parts[0] == str(int(Layer.BOOK_AUTO))` | `projection.py` |
| Build / CAS publish | `build_revision`, `publish_revision`, `AutoEntry`, `StaleActiveError` | `revision.py` |
| Diff 2 revision / affected blocks | `diff_revisions`, `affected_block_ids` | `correction.py` |
| Render block (isolation) | `vp_plan(dic, vp_input, beam, occurrence_prefix, collapse_reps)`, `sanitize_source` | `vietphrase/lattice.py`, `qa.py` |
| Structural invariant | `run_invariants(source, output, block_id)` → `InvariantResult(ok, errors)` | `quality/invariants.py` |
| Baseline run/blocks | `latest_completed_run_for_source(source_rev_id, exclude_run_id=None)`, `committed_blocks(run_id)` (có `final_text`, `source_hash`) | `state.py` |
| Source mới nhất | `latest_source_revision()` → snapshot_path/encoding | `state.py` |
| Block id từ node | `node_block_id(node)` | `export.py` |
| Evidence đọc | `SELECT * FROM candidate_evidence WHERE book_id=? AND dictionary_revision_id=?` + `cursor_dicts` | `state.py` |
| Config ngưỡng | `cfg.learning.min_term_occurrences`, `min_chapters`, `enabled`, `auto_scope` | `config.py` |

### Isolation check — chi tiết

- Render phải chỉnh đúng cfg như pipeline (`sanitize_source` khi `qa_strip_junk`, `collapse_reps`, `beam`) nếu không so hash sai.
- `occurrence_prefix` dùng block id (như pipeline) để tránh leak state giữa block.
- So sánh text (`final_text`), không so hash — cần list block đổi cho regression signals.
- Perf: O(tổng block) mỗi lần promote — chấp nhận (pure trie walk, không model). Implementation render FULL mọi block mỗi lần promote — chủ đích chặt hơn skip-prescription (bắt được violation ở mọi block, không chỉ affected); block có baseline + không đổi được skip invariant (đã pass lúc translate), block không baseline luôn chạy invariant (AD-20).
- Baseline None (project chưa translate): isolation pass (`no_baseline`), invariant vẫn chạy trên affected blocks.

### Promotion flow — thứ tự bắt buộc

1. Gates (evidence) — reject sớm, KHÔNG build.
2. Build dry-run → dic mới.
3. Isolation + structural invariant trên dic mới.
4. Fail → reject (gate isolation) + KHÔNG activate. Pass → publish CAS.
5. Events + status updates + regression evidence SAU activate thành công (crash giữa hai bước → revision mới đã active nhưng candidate vẫn 'candidate'; lần learn sau idempotency skip bắt lại — chấp nhận, ghi note).

### Idempotency (chạy `zhvi learn` nhiều lần)

- Discovery/candidates/evidence replace theo (book, drev) — an toàn.
- Sau promote, drev mới → lần learn sau candidates build lại ở drev mới. Candidate đã promote: key giờ là auto entry → discovery thấy segment đã khớp (không còn is_unknown/single_char_run) HOẶC vẫn sinh candidate — mọi trường hợp: skip vì `(source, target)` đã trong auto entries hiện có.
- Rejected theo drev — drev mới được đánh giá lại (reject không vĩnh viễn).

### Phạm vi KHÔNG làm

- Không CLI `terms` (list/accept/reject/revoke/explain) — story 3.5. `revoke_book_auto` chỉ API + test.
- Không global promotion / cross-book / golden manifest (Epic 4, AD-14).
- Không đổi hành vi `discover` / `translate` / builder 3.2 / evidence 3.3.
- Không smoke corpus step 8 mới (publish hiện hữu giữ nguyên).

### Previous story intelligence (3.3)

- Comments Việt không dấu; imports top; lint hook chặn F401 từng bước — imports + usage cùng edit.
- Edit tool khó match chuỗi chứa CJK range regex — edit tránh đụng dòng đó.
- Test fixture `_learned` pattern sẵn dùng (xem `tests/test_evidence.py`).
- Suite baseline 213 passed / 2 skipped.

### Project Structure Notes

- `learning/promotion.py` mới; test `tests/test_promotion.py` mới.
- `state.py` sửa (v7, promotion_events, append/read, replace_evidence_group); `cli.py` sửa (learn wire promotion).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4 (lines 318–331)]
- [Source: ARCHITECTURE-SPINE.md — AD-4, AD-6, AD-7, AD-8, AD-12, AD-13, AD-15, AD-20]
- [Source: data-model.md — promotion_events, publish protocol, layer table, concurrency]
- [Source: zhvi/src/zhvi/revision.py — build_revision/publish_revision/AutoEntry/AUTO_LAYER_BY_SCOPE]
- [Source: zhvi/src/zhvi/correction.py — diff_revisions/affected_block_ids pattern]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_promotion.py RED (ImportError PromotionEventRow / promotion module) → GREEN từng task.
- Task 1 GREEN cần thêm field `created_at` vào PromotionEventRow (SELECT * trả cột đó).
- Task 2: fixture thực nghiệm cho thấy builder `" ".join` targets con + renderer space-separator khiến promoted entry hầu như KHÔNG đổi text (chỉ đổi segmentation spans) — isolation test phải đè `proposed_target` khác render cũ ("Lý Mộ Bạch Đại Hiệp") để có thay đổi thật kiểm chứng changed == affected.
- Candidate 看着前 ban đầu bị unresolved vì 前 thiếu entry trong fixture dict — thêm `前=trước` vào QualityOverrides để compound build được target + risk manual_conflict (prefix 看着 manual).
- Promotion là BATCH: mọi candidate pass gates promote cùng một revision. Tests assert `promoted >= 1` thay vì `== 1`.

### Completion Notes List

- Lifecycle events: bảng `promotion_events` append-only (UUID id, before/after/actor/timestamp/provenance) — KHÔNG replace theo scope, khác observations/candidates/evidence. Events chỉ bắt đầu từ quyết định promotion (`rejected`/`promoted`/`revoked`); transition observed→candidate do builder ghi (bảng riêng, replace).
- 4 hard gates từ evidence signals (score không tham gia — AD-7): min_occurrences (total_count + chapter_count theo `cfg.learning`), target_stability (single_target + same_segmentation), no_manual_conflict, benefit_positive. Điều kiện vào đánh giá: status='candidate' AND eligible_auto=1.
- Isolation + structural invariant là 2 gate post-build trên revision dry-run: render lại MỌI block với dic mới (đúng cfg như pipeline), changed ⊆ affected, `run_invariants` cho block đổi. Fail → reject cả batch, KHÔNG activate (AC 2).
- Idempotency: `(source, target)` trùng auto entry active → skip không lặp event; rejected/revoked cùng drev không đánh giá lại (drev mới được đánh giá lại tự nhiên).
- Re-promote key với target khác: auto entry cũ cùng key bị replace (giữ cả hai sẽ BuildError conflict cùng scope/layer).
- Regression evidence populate: `replace_evidence_group` mới (chỉ group regression) với signals thật `{changed_blocks, affected_blocks, invariant_errors, structural_invariant_pass, isolation_pass, baseline_run}` — hết placeholder `deferred` cho candidates promoted.
- Revoke: build revision mới = autos trừ key (content-addressed bảo đảm chỉ khác key đó); event revoked cho mọi candidate book_auto của key, hoặc event mồ côi (candidate_id='') nếu không còn row.
- CLI `learn` wire promotion sau evaluate (cùng project_lock "translate"; publish_revision tự lấy lock "publish" riêng — đã verify không deadlock); guard `cfg.learning.enabled` + `auto_scope == "book"`; `StaleActiveError` → EXIT_RUN_FAILED.
- Perf note: isolation render full book mỗi lần promote (pure trie walk) — chấp nhận theo story; chưa cần optimize.
- **Review fixes (2 trục, 15 findings — tất cả đã xử lý):** HIGH — structural invariant giờ chạy cho block changed VÀ block không baseline (trước đó flow "learn trước translate" promote với 0 lần invariant); MED — event log chặn rejected lặp lại khi composite learn re-run cùng drev (replace_candidates reset status); revoke emit event mồ côi theo flag "đã thấy row book_auto" thay vì `not cands` (lấp gap mất provenance); `PromotionError(RuntimeError)` thay ValueError (convention src); `evaluate_gates` bỏ param `cand` unused; `ev_id` promote public trong evidence.py (hết nhân đôi content-addressed formula). LOW — revoked guard: key từng revoke không tự re-promote ở drev sau (quyết định bền, 3.5 accept lại); IsolationResult reuse doc/baseline (hết parse đôi); `to_json` thêm book_id; `promotion_events_for` dùng cursor_dicts; test_evidence assert `== SCHEMA_VERSION`; test thêm: no-baseline invariant spy, composite re-run không nhân đôi rejected, `diff.changed == []` + `affected_keys == [key]` revoke, các gate khác đều pass trong reject "điểm không bù". 2 finding resolve-by-doc: full-render isolation chủ đích chặt hơn skip-prescription; API signature ghi nhận trong Tasks.

### File List

- zhvi/src/zhvi/state.py (sửa: SCHEMA_VERSION 7, DDL promotion_events + index, PromotionEventRow, _EVT_COLS, append_promotion_event, promotion_events_for, update_candidate_status, replace_evidence_group)
- zhvi/src/zhvi/learning/promotion.py (mới)
- zhvi/src/zhvi/cli.py (sửa: learn wire run_promotion, JSON thêm promotion, StaleActiveError handler)
- zhvi/tests/test_promotion.py (mới)
- zhvi/tests/test_state.py (sửa: migrate assert version 7)
- zhvi/tests/test_cli.py (sửa: test_learn_command_json thêm assert promotion)

## Change Log

- 2026-09-05: Story created — ultimate context engine analysis completed.
- 2026-09-05: Story 3.4 implementation — migration v7 promotion_events, learning/promotion.py (4 gates + isolation + revoke + regression evidence), CLI learn wire, 9 test promotion mới.
- 2026-09-05: Review fixes (15 findings, 2 trục Opus) — invariant no-baseline, event idempotency qua event log, revoke audit gap, PromotionError, ev_id public, revoked guard + 2 test mới.
