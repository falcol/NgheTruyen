---
baseline_commit: 9d9123d
---

# Story 3.2: Candidate builder — target xác định hoặc unresolved

Status: done

## Story

As a hệ thống học theo truyện,
I want candidate builder chỉ sinh target từ 6 nguồn xác định (lớp thấp hơn, ghép longest-match entry con, phiên âm Hán–Việt cho tên riêng, template `LuatNhan.txt`, correction/glossary người dùng, target đã accept còn provenance),
So đó máy không bao giờ bịa nghĩa để tăng coverage.

## Acceptance Criteria

1. **Given** tập observation **When** build candidate **Then** candidate không có target từ 6 nguồn mang trạng thái `unresolved`; candidate có target kèm provenance nguồn.
2. Key chuẩn hóa NFC + giản thể để so khớp, source gốc lưu provenance; target chuẩn hóa khoảng trắng/dấu câu theo rule.
3. Target mơ hồ (`a/b`, placeholder, ký tự CJK) bị loại khỏi auto-promote; candidate trùng manual entry bị loại.
4. Candidate ghép entry con chỉ eligible khi mỗi entry con có đúng một target ưu tiên.

## Tasks / Subtasks

- [x] Task 1: Migration v4 → v5 — mở bảng `term_candidates` cho flow mới (AC: 1, 3, 4)
  - [x] `state.py`: `SCHEMA_VERSION = 5`; `_migrate` nhánh `if from_version < 5`: `ALTER TABLE term_candidates ADD COLUMN dictionary_revision_id TEXT NOT NULL DEFAULT ''`, `ADD COLUMN eligible_auto INTEGER NOT NULL DEFAULT 0` (additive, AD-19; bảng legacy chưa có code ghi — mở dùng an toàn)
  - [x] State method `replace_candidates(rows)` — replace-not-append theo scope `(book_id, dictionary_revision_id)` (candidate thuộc book + dict state, không theo source revision)
- [x] Task 2: `learning/candidate.py` — resolvers + `build_candidates` (AC: 1–4)
  - [x] `CandidateRow` dataclass trong state.py cạnh `ObservationRow`
  - [x] Resolver pipeline theo thứ tự ưu tiên cố định: `lower_layer` → `phien_am` (chỉ pattern person — đáng tin hơn compound cho tên riêng) → `compound` → `template`; nguồn 5 (`user`) + 6 (`accepted_elsewhere`) là stub None + note provenance (xem Completion Notes)
  - [x] Pre-check loại (AC 3): key trùng manual entry (layer ≥ GLOBAL_MANUAL — bao gồm QualityOverrides/Custom theo loader) → skip
  - [x] Chuẩn hóa (AC 2): key giản thể + NFC (không gian observation); target `re.sub(r"\s+", " ", t).strip()`
  - [x] Target mơ hồ (AC 3): regex `[/{}%]|CJK` → eligible_auto=0
  - [x] AC 4: compound ghi `ambiguous_parts` khi entry con có ≥2 target ưu tiên → eligible_auto=0
  - [x] Chọn observation: ≥1 tín hiệu học + `total_count >= MIN_OCCURRENCES` (3)
  - [x] `build_candidates` + `CandidateSummary.to_json()`
- [x] Task 3: CLI `zhvi learn -p PROJECT` (AC: 1)
  - [x] Command `learn`: guard + `ensure_book_dictionary` → `run_discovery` (idempotent — replace-not-append) → `build_candidates` → JSON `{discovery, candidates}`
  - [x] `zhvi discover` giữ nguyên
- [x] Task 4: Tests `tests/test_candidate.py` (AC: 1–4)
  - [x] Fixture: QualityOverrides (multi + singles) + ChinesePhienAmWords (BASE_SINGLE cho 李慕白); text 3 chương với 李慕白×3, 紫霄山×3, 未知语×3
  - [x] AC1: 李慕白 → `lý mộ bạch` resolver phien_am; 紫霄山 → `tử tiêu núi` resolver compound; 未知语 → unresolved + target rỗng + resolver None
  - [x] AC2/AC3: chuẩn hóa target; manual conflict (observation giả cho key có QualityOverrides entry) → skipped_manual=2, không tạo row
  - [x] Determinism: build 2 lần → cùng rows
  - [x] CLI e2e `test_learn_command_json` (dict thật)
  - [x] Regression: full suite xanh — 204 passed / 2 skipped (baseline 197/2 + 7 mới)

## Dev Notes

### Invariants ràng buộc

- **AD-6 (lõi story)** — target chỉ từ 6 nguồn đã biết; không dựng được target đơn nghĩa → `unresolved`. KHÔNG bao giờ fallback "chọn target giống nhất".
- **AD-5** — candidate trùng manual entry bị loại; manual luôn thắng.
- **AD-4** — candidate builder là LEARN; chỉ đọc dictionary.
- **AD-8** — candidate state trong book SQLite.
- Resolver thứ tự cố định = deterministic: target lấy từ resolver ĐẦU TIÊN trả != None; mọi nguồn tìm thấy đều ghi provenance.

### API có sẵn (verified story 3.1 + research)

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Trie lookup / segmentation | `vp_plan(dic, text)` hoặc `greedy_path(dic, text)`; walk tay `dic.root` (TrieNode: `children`, `entries: list[(target, precedence, policy)]`) | `vietphrase/lattice.py`, `vietphrase/loader.py` |
| Pattern rule | `fill_target(rule, match, translate)` — slots s/n, template {s}/{n}/{k} | `vietphrase/patterns.py` |
| Layers | `Layer` IntEnum: BASE_SINGLE=0, AUTO_GLOBAL=1, BOOK_AUTO=2, BASE_MULTI=3, GLOBAL_MANUAL=4, SERIES_MANUAL=5, BOOK_MANUAL=6, USER_SEGMENT=7 | `vietphrase/layers.py` |
| Manual glossary parse | `parse_dict_line(line) -> (zh, vi) \| None` | `vietphrase/loader.py` |
| Observations input | `SELECT * FROM observations WHERE source_revision_id=? AND dictionary_revision_id=?` | bảng story 3.1 |
| Dictionary setup chung | `ensure_book_dictionary(project, dict_dir, cfg)` | `pipeline.py` (story 3.1) |
| Replace semantics | copy pattern `replace_observations` | `state.py` |

**Trie walk chi tiết:** entry tại node có `entries` list `[(target, precedence, policy)]` — "một target ưu tiên" = số target KHÁC NHAU trong list sau khi sort theo precedence (entry cùng target gộp). Layer của entry = `precedence[0]`.

**Nguồn 5 (user) hiện trạng:** correction flow (2.5) ghi thẳng glossary manual → trùng key sẽ bị pre-check loại. Nguồn correction CHƯA trùng key cần feedback_events có (text_corrected) — chưa có flow ghi. Ghi `[Note]` trong code + provenance `"user": "pending-feedback-events"`. Đừng bịa nguồn.

**Nguồn 6 (accepted elsewhere):** registry cross-book là Epic 4 — stub `None` + provenance `"accepted": "deferred-registry"`. In-scope version này chỉ wire resolver slot.

### DDL mở rộng term_candidates (v5)

```sql
ALTER TABLE term_candidates ADD COLUMN dictionary_revision_id TEXT NOT NULL DEFAULT '';
ALTER TABLE term_candidates ADD COLUMN eligible_auto INTEGER NOT NULL DEFAULT 0;
```

Cột hiện có dùng lại: `id` (UUID — event-like), `book_id`, `source` (key giản thể NFC), `proposed_target` (NULL cho unresolved — cột hiện NOT NULL! → đổi thành nullable bằng bảng mới? KHÔNG — kiểm tra schema: `proposed_target TEXT NOT NULL` → unresolved lưu chuỗi rỗng `''` + status `unresolved`), `kind` (`term|name|pattern`), `status` (`candidate|unresolved`), `provenance_json` (`{"resolver": ..., "sources": [...], "original": ..., "notes": [...]}`).

**Lưu ý:** `proposed_target NOT NULL` — unresolved dùng `''`. Đừng ALTER thành nullable (additive-only migration).

### Phạm vi KHÔNG làm

- Không evidence, không promotion, không `zhvi terms` (3.3–3.5).
- Không registry/cross-book thật (Epic 4).
- Không config `[learning]` mới — constants (`MIN_OCCURRENCES = 3`).
- Không đổi `zhvi discover` behavior.

### Previous story intelligence (3.1)

- `Node.content` là property. Comments tiếng Việt KHÔNG dấu. Imports top-of-module.
- Test pattern: fixture `_mini_dict_dir` + `create_project` + `import_snapshot` + upsert + `ensure_active_revision` — copy từ test_discovery.py.
- Lint hook chặn F401 từng bước — thêm imports + usage cùng một edit.
- Suite baseline 197 passed / 2 skipped.

### Project Structure Notes

- `learning/candidate.py` mới trong package `learning/` (Structural Seed).
- Test `tests/test_candidate.py` mới.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2 (lines 289–303)]
- [Source: thiet-ke-he-thong-dich-truyen-zh-vi.md#Bước-3-sinh-target-không-dùng-ai + #Bước-4-chuẩn-hóa-candidate (lines 175–195)]
- [Source: _bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md — AD-4, AD-5, AD-6, AD-8]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/data-model.md — Bảng SQLite, entry identity]
- [Source: zhvi/src/zhvi/state.py — term_candidates DDL gốc, replace_observations pattern]
- [Source: zhvi/src/zhvi/vietphrase/layers.py — Layer enum; loader.py — TrieNode.entries shape]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_candidate.py RED (schema v5, CandidateRow import fail) → GREEN từng task.
- Resolver order đảo khi làm: `phien_am` TRƯỚC `compound` cho tên riêng — compound dùng mọi entry (kể cả non-phonetic) nên kém xác thực cho tên người; fixture xác nhận `李慕白 → lý mộ bạch` resolver `phien_am`.

### Completion Notes List

- Loader fact (verified `loader.py:181-185`): `QualityOverrides.txt`/`Custom.txt` → layer GLOBAL_MANUAL kể cả single char; `ChinesePhienAmWords.txt` single → BASE_SINGLE. Do đó `_manual_conflict` check `precedence[0] >= Layer.GLOBAL_MANUAL` bắt cả QualityOverrides key — đúng AD-5 (human-owned files), test `skipped_manual` xác nhận.
- Nguồn 5 (user correction): stub — correction flow 2.5 ghi thẳng glossary manual (đã bị pre-check loại nếu trùng key); nguồn correction CHƯA trùng key cần feedback_events schema mở (chưa có flow ghi). Ghi note `user: pending-feedback-events` trong provenance — không bịa nguồn (AD-6).
- Nguồn 6 (accepted elsewhere): stub `accepted_elsewhere: deferred-registry` — cần registry Epic 4.
- `proposed_target NOT NULL` → unresolved lưu `''` (không ALTER nullable — additive-only).
- Candidate id = SHA-256(book_id + drev + key) — content-addressed, deterministic rebuild (AC determinism test so toàn bộ row fields).
- **Review fixes (2 trục, 9 findings — tất cả đã xử lý):** `replace_candidates(book_id, drev, rows)` scope explicit — rows rỗng vẫn xóa scope (đồng bộ semantics replace_observations); `_resolve_lower_layer` mở rộng nhận MỘI entry auto/base (bao gồm BASE_MULTI — key có entry dict chính giữ target đó, không cho phien_am/compound đè); `_normalize_target` thêm rule dấu câu (strip punctuation hai đầu Latin+CJK, inner giữ nguyên); `build_candidates` nhận `min_occurrences` — CLI `learn` truyền `cfg.learning.min_name_occurrences` (hết duplicate hai nguồn chân lý); extract `_learn_context` dùng chung discover/learn; `_entry_layer` helper thay index lồng; test AC4 dual-target thật (`紫=tử` + `紫=tím` → `ambiguous_parts` + `eligible_auto=0`); bỏ assertion tautology ở CLI test.
- Template `_translate` passthrough span CJK không entry → bị `_AMBIGUOUS_RE` chặn eligible — AD-6 an toàn, có comment tại chỗ.

### File List

- zhvi/src/zhvi/state.py (sửa: SCHEMA_VERSION 5, migration nhánh v5, CandidateRow, _CAND_COLS, replace_candidates scope explicit)
- zhvi/src/zhvi/learning/candidate.py (mới)
- zhvi/src/zhvi/cli.py (sửa: command `learn`, helper `_learn_context` dùng chung discover/learn)
- zhvi/tests/test_candidate.py (mới)
- zhvi/tests/test_cli.py (sửa: test_learn_command_json)
- zhvi/tests/test_state.py (sửa: migrate assert version 5)
- zhvi/tests/test_discovery.py (sửa: schema assert >= 4 — v5 compatible)

## Change Log

- 2026-09-05: Story 3.2 implementation — term_candidates v5 (dictionary_revision_id, eligible_auto), candidate builder 6 nguồn (2 stub có ghi chú), CLI `zhvi learn` composite discovery→candidate.
- 2026-09-05: Review fixes (9 findings) — replace scope explicit, lower_layer bao BASE_MULTI, normalize dấu câu, min_occurrences từ config, extract _learn_context, test AC4 dual-target.
