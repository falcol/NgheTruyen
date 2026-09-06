---
baseline_commit: dfedf900f97619ce98f7c8eb6e85cd4a31710ab4
---

# Story 4.3: Global promotion fail-closed + drift report

Status: done

## Story

As a người quản lý từ điển chung,
I want `zhvi learn --global` đánh giá `global_candidate → global_auto` với hard gates (≥3 truyện độc lập, ≥20 occurrence, target agreement 100%, không manual conflict mọi project đã đăng ký, pass golden suite, không tăng unknown/CJK residue/structural failure, diff ngoài affected blocks bằng 0) và global auto-promotion khóa khi chưa có approved golden manifest,
So đó từ điển toàn cục chỉ đổi khi có bằng chứng không regression.

## Acceptance Criteria

1. **Given** candidate `global_candidate` có cross-book evidence **When** đánh giá global promotion **Then** thiếu bất kỳ hard gate (đặc biệt approved golden manifest) thì candidate dừng ở `global_candidate` với lý do từng gate; không file `expect*` nào tự thành golden.
2. Khi đủ điều kiện (golden manifest approved tồn tại): promotion atomic qua registry (lock, revision build, CAS active global); global activation không đổi active book revision hiện có; `AutoVietPhrase.txt` materialize chỉ bởi registry writer.
3. Xuất drift report theo revision (entry mới/đổi/revoked, affected books); revoke global auto entry append event và build revision mới.
4. Test: không golden manifest thì không thể global auto-promote dù evidence đủ — fail-closed xác nhận.

## Tasks / Subtasks

- [x] Task 1 — Registry schema v3 additive (AC: #1, #2)
  - [x] 1.1 `REGISTRY_SCHEMA_VERSION = 3`. `global_evidence` thêm cột `source TEXT NOT NULL DEFAULT ''`, `target TEXT NOT NULL DEFAULT ''` (identity xuyên sách — `candidate_id` là UUID book-local, không gom được 3 truyện). `EvidenceRecord` thêm `source: str = ""`, `target: str = ""` (default, 4.2 `_record()` không vỡ)
  - [x] 1.2 Bảng mới (CREATE IF NOT EXISTS): `global_candidates(source PRIMARY KEY, target, status, updated_at)`; `global_promotion_events` (append-only, cùng shape tinh thần book `promotion_events`); `global_active(scope TEXT PRIMARY KEY, revision_id, updated_at)` — một row `scope='global'`
  - [x] 1.3 `_migrate` v2→v3: ALTER ADD COLUMN source/target nếu thiếu + bump version (AD-19, không drop). `cross_book_by_source()`: GROUP BY `source` WHERE source!='' AND JOIN active book_sources — 4.3 dùng cái này, giữ `cross_book_summary()` theo candidate_id (4.2)
  - [x] 1.4 `ingest_evidence` INSERT kèm source/target. `build_evidence_records` join `term_candidates` lấy source/proposed_target
- [x] Task 2 — `zhvi/src/zhvi/learning/global_promotion.py` (AC: #1–#4)
  - [x] 2.1 Gates per-source (AD-7: fail một = không promote; điểm không bù). Suite-wide `golden_manifest`: `approved_cases(load_manifest())` rỗng → fail-closed (AD-14). Có approved → `run_golden_report`; mọi case approved phải `pass`. Per-source: `min_books` ≥ `cfg.learning.global_min_books` (3); `min_occurrences` = SUM `strength.total_count` ≥ `global_min_occurrences` (20); `target_agreement` mọi target giống nhau; `no_manual_conflict` mọi `risk.manual_conflict==0`
  - [x] 2.2 Fail-closed HOLD: không đổi status sang `rejected` (khác book 3.4) — giữ `global_candidate` + event `held` kèm gates. Retry khi golden được duyệt
  - [x] 2.3 Pass: trong `registry_lock` — build bundle (AutoEntry scope=`global`, Layer.AUTO_GLOBAL) vào `registry/workspace` (tái dùng `build_revision`, không activate book DB); CAS `global_active`; `atomic_write` `dict_dir/AutoVietPhrase.txt` (không nằm HUMAN_OWNED). Isolation + structural + CJK: `_isolation_check` trên project `-p` (reuse 3.4). Fail isolation → không CAS, held
  - [x] 2.4 Global CAS không đụng `active_revisions` book (AD-16). Test snapshot book active trước/sau
  - [x] 2.5 Drift report `registry/reports/drift-<revision_id>.json`: added/changed/revoked + affected book_ids
  - [x] 2.6 `revoke_global_auto(dict_dir, source, actor)` — revision mới bớt key, event `revoked`, rematerialize
- [x] Task 3 — CLI `zhvi learn --global` (AC: #2)
  - [x] 3.1 Flag `--global` trên `learn` (không thay auto_scope). `--manifest` override. Flow: submit_book_evidence rồi `run_global_promotion`. JSON key `"global_promotion"`
  - [x] 3.2 GoldenError/RegistryError/PromotionError → stderr + exit != 0
- [x] Task 4 — Tests `zhvi/tests/test_global_promotion.py` (AC: #1–#4)
  - [x] 4.1 Fail-closed: 3 book evidence đủ ngưỡng, KHÔNG approved golden → không AutoVietPhrase, status `global_candidate`, 0 promoted
  - [x] 4.2 expect* không tự golden: import expect rồi learn --global vẫn fail golden gate
  - [x] 4.3 Pass path: approved manifest (tmp, 1 case pass) + 3 books + agreement → AutoVietPhrase có entry, book active revision không đổi, drift report tồn tại
  - [x] 4.4 Target disagreement → held; revoke → entry biến khỏi AutoVietPhrase, revision_id đổi
  - [x] 4.5 CLI `--global` JSON parse được; lock ngoài → RegistryError
  - [x] 4.6 Migration v2→v3: DB v2 mở ra version 3, cột source/target có; meta cũ giữ
- [x] Task 5 — Sửa test 4.2 cứng schema (AC: schema)
  - [x] 5.1 `test_ingest.py`: `REGISTRY_SCHEMA_VERSION == 2` → `== 3` (cùng pattern 4.1→4.2). `test_ingest_creates_no_global_candidate...`: bảng v3 tồn tại nhưng ingest không INSERT global_candidates (COUNT=0)
- [x] Task 6 — Full suite + ruff

## Dev Notes

### Invariants

- **AD-14** — thiếu approved golden → không vượt `global_candidate`. `approved_cases` là port duy nhất (không parse manifest tay). File `expect*` không tự golden.
- **AD-7** — fail một gate là không promote; score không bù.
- **AD-13** — mọi mutate global (candidates, events, active, AutoVietPhrase) trong `registry_lock`.
- **AD-16** — global activation không đổi book active revision.
- **AD-15** — build temp → CAS pointer registry (không dùng `publish_revision` book).
- **AD-5** — AutoVietPhrase.txt machine projection; `atomic_write` + ownership guard (tên file không human-owned).
- **AD-19** — schema v3 additive.

### Quyết định

- Gom evidence theo **source** (cột mới), không theo candidate_id UUID.
- HOLD không REJECT: golden có thể được duyệt sau.
- Golden suite-wide: một fail chặn cả run.
- Isolation dùng project `-p` (registry không lưu book path). Golden là regression xuyên sách.
- Occurrence = SUM strength.total_count (chữ "≥20 occurrence tổng"), không phải số row (3 books × 6 group = 18 < 20).
- Dummy `registry/workspace` project chỉ để `build_revision` ghi bundle; pointer ở `global_active`.

### Phạm vi KHÔNG làm

- Không đổi book `run_promotion`. Không materialize AutoVietPhrase ngoài registry writer. Không auth actor. Không 5.1 QA run gate. Không sửa golden.py trừ khi 4.3 bắt buộc (không).

### Test 4.2 phải sửa

- `test_migration_v1_to_v2_preserves_meta` hardcode `== 2`
- `test_ingest_creates_no_global_candidate_or_revision_tables` so sánh set bảng đúng 3 tên

### References

- epics.md Story 4.3; AD-14/13/16; pipeline-contract golden + global gates; golden.py `approved_cases`; promotion.py `_isolation_check`; registry.py v2; config LearningConfig global_* 

## Dev Agent Record

### Agent Model Used

Grok 4.6

### Debug Log References

- TDD: test_global_promotion collection SyntaxError walrus → 7 passed.
- Revoke: AUTO_GLOBAL bi QO layer che trong bundle — doc `global_candidates` status=global_auto.
- Full suite: 271 passed / 2 skipped (264 + 7); ruff sạch.

### Completion Notes List

- Registry schema v3: source/target tren global_evidence; bang global_candidates / global_promotion_events / global_active. EvidenceRecord default `source=""`, `target=""`.
- `run_global_promotion`: golden fail-closed HOLD (khong rejected); gates min_books/occurrences/agreement/conflict; CAS global_active; AutoVietPhrase.txt chi registry writer; book active revision khong doi.
- `zhvi learn --global` + `--manifest`; JSON `global_promotion`.
- Sua test 4.2: schema == 3; ingest khong INSERT global_candidates.
- **Review fixes (2 trục, 1 hard — 8 fix / 5 skip):** import sqlite3/REGISTRY_DIRNAME top; `cross_book_by_source()`; materialize/drift sau commit; HOLD khong demote `global_auto`; drift `added` + event `revoked`; `ensure_ascii=False`; GoldenError CLI exit != 0; per-source gates tren summary. Skip: DRY HOLD/CAS, CJK alias, isolation dummy workspace, `global_require_golden_suite=False`, 4.2 phai goi `learn --global`.

### File List

- zhvi/src/zhvi/registry.py
- zhvi/src/zhvi/learning/global_promotion.py
- zhvi/src/zhvi/learning/ingest.py
- zhvi/src/zhvi/cli.py
- zhvi/tests/test_global_promotion.py
- zhvi/tests/test_ingest.py
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-09-06: Story created then implemented in same session.
- 2026-09-06: Global promotion fail-closed + drift/revoke; suite 271/2.
- 2026-09-06: Review fixes (8 fix / 5 skip) — cross_book_by_source, HOLD khong demote, projection sau commit, CLI GoldenError.
- 2026-09-06: Closed (review already applied; epic-4 done).
