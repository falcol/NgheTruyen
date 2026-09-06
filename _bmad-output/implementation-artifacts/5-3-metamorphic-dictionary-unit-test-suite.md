---
baseline_commit: da916ba8487f608f949d1fd9de7921fd5de6b16f
---

# Story 5.3: Metamorphic + dictionary unit test suite

Status: done

<!-- Review 5.1+5.3: reorder auto dung key khong trung QO + revision_id; import top; comment khong dau. -->

## Story

As a người bảo đảm chất lượng,
I want suite metamorphic (thêm entry không có trong source không đổi output; reorder file auto không đổi output; dịch cả truyện một lần == từng chương; resume == clean run; rollback + chạy lại khôi phục output hash; phồn/giản thể alias chọn cùng entry) và dictionary unit tests (parse mọi dòng, auto không duplicate/conflict, precedence, alias, pattern không nuốt literal dài hơn, deterministic),
So đó mọi invariant kiến trúc được kiểm liên tục không cần model.

## Acceptance Criteria

1. **Given** repo sau Epic 1–4 **When** chạy suite **Then** cả 6 bất biến metamorphic có test riêng và pass; dictionary unit tests phủ 6 nhóm nêu trên.
2. Test dùng fixture tự chứa (khai báo dependency trong root test collection), không gọi network/model.
3. Suite chạy trong thời gian hợp lý cho CI local (< vài phút).

## Tasks / Subtasks

- [x] Task 1 — `zhvi/tests/test_metamorphic.py` (AC: #1, #2) — mỗi invariant một test function
  - [x] 1.1 Thêm auto entry key KHÔNG có trong source → output SHA-256 không đổi (`publish_revision` + `translate_project`)
  - [x] 1.2 Reorder dòng file auto/base dict → output SHA-256 không đổi (layer hash canonical, xem `test_revision.py`)
  - [x] 1.3 Dịch cả truyện một lần == nối bản dịch từng chương (cùng source cắt theo `parse_document` chapter_id)
  - [x] 1.4 Resume sau interrupt == clean run (cùng helper `test_baseline.py` `test_resume_parity`, không sửa file đó)
  - [x] 1.5 Rollback + chạy lại khôi phục output SHA-256 (`rollback_revision` / publish rollback)
  - [x] 1.6 Phồn/giản thể alias chọn cùng entry (`trad-simp.txt` + pipeline SHA)
- [x] Task 2 — `zhvi/tests/test_dictionary_units.py` (AC: #1, #2) — 6 nhóm
  - [x] 2.1 `parse_dict_line`: hợp lệ, skip junk/comment/`{0}`
  - [x] 2.2 Auto không duplicate/conflict: `BuildError` cùng scope+key khác target; cùng target dedupe; khác scope OK
  - [x] 2.3 Precedence: Layer enum `BOOK_MANUAL > BOOK_AUTO > BASE_SINGLE`; functional manual thắng auto/base
  - [x] 2.4 Alias trad/simp: `load_trad_simp` / `to_simplified` / `vp_plan` cùng entry; Custom.txt simp keys
  - [x] 2.5 Pattern `{n}` không nuốt literal dài hơn (longest match)
  - [x] 2.6 Deterministic: cùng input → cùng SHA-256 (+ cùng `build_revision` id)
- [x] Task 3 — Fixture tự chứa, không network/model (AC: #2)
  - [x] 3.1 Mini dict trong `tmp_path` (pattern `_mini_dict_dir` của `test_baseline.py`)
  - [x] 3.2 Reuse API: `translate_project`, `TranslateRequest`, `create_project`, `build_revision`, `publish_revision`, `parse_dict_line`, `Layer`
  - [x] 3.3 Không thêm production feature; tests only + story markdown
- [x] Task 4 — Chạy suite + ruff (AC: #3)
  - [x] 4.1 `cd zhvi && .venv/bin/python -m pytest tests/test_metamorphic.py tests/test_dictionary_units.py -q` — 12 passed
  - [x] 4.2 Ruff sạch file mới

## Dev Notes

### Invariants ràng buộc

- **CAP-11** — regression không model: dictionary unit tests + golden + metamorphic. Story này là lớp unit + metamorphic; golden đã có ở 5.2.
- **AD-9** — output deterministic; layer hash canonical (sort source+target) nên reorder dòng file không đổi revision id / output SHA.
- **AD-5** — BOOK_AUTO fill-only, thấp hơn BASE_MULTI; manual thắng tuyệt đối. Test precedence phản ánh Layer enum thật, không giả định auto > phrase nen.
- **AD-12** — rollback chỉ CAS active pointer, không sửa bundle cũ.

### Quyết định thiết kế story

- Chỉ NEW files (isolation worktree). Không sửa `pipeline.py` / `export.py` / `qa.py` / `cli.py` / `registry.py` / `sprint-status.yaml` / test cũ.
- Resume: copy helper `test_resume_parity` (monkeypatch `zhvi.pipeline.vp_plan` KeyboardInterrupt sau block đầu) — không import từ `test_baseline.py` để fixture tự chứa.
- Rollback restore: đổi glossary + `refresh_revision=True` tạo SHA khác, `rollback_revision` về r1, translate ra file output mới (tránh nhánh noop giữ file cũ).
- Whole == per-chapter: cắt lossless theo `chapter_id` (`"".join(chapters) == SRC`), mỗi chương project riêng, so SHA concat.
- Comments Việt không dấu; imports module top.

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Pipeline | `translate_project` / `TranslateRequest` | pipeline.py |
| Project | `create_project` | project.py |
| Revision | `build_revision` / `publish_revision` / `AutoEntry` / `BuildError` | revision.py |
| Rollback | `rollback_revision` | correction.py |
| Parse dict | `parse_dict_line` / `load_dictionary` / `load_trad_simp` / `to_simplified` | vietphrase/loader.py |
| Layer | `Layer` | vietphrase/layers.py |
| Lattice | `vp_plan` | vietphrase/lattice.py |
| Chapter split | `parse_document` | document.py |
| Resume pattern | `test_resume_parity_interrupted_equals_clean` | tests/test_baseline.py |

### Phạm vi KHÔNG làm

- Không production feature / sửa pipeline / QA gate / golden / CLI.
- Không sửa test cũ (`test_baseline.py`, `test_revision.py`, `test_lattice.py`, `test_correction.py`).
- Không 5.4 E2E CLI docs.
- Không cập nhật `sprint-status.yaml` (isolation: only NEW files).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.3 (lines 425-437)]
- [Source: thiet-ke-he-thong-dich-truyen-zh-vi.md — mục 13 Regression không cần model (512-543)]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/SPEC.md — CAP-11]
- [Source: zhvi/tests/test_baseline.py — `_mini_dict_dir`, `test_resume_parity`]
- [Source: zhvi/tests/test_revision.py — layer hash reorder, BuildError conflict]
- [Source: zhvi/tests/test_correction.py — rollback]
- [Source: zhvi/tests/test_lattice.py — trad/simp alias, literal vs pattern]

## Dev Agent Record

### Agent Model Used

Grok 4.6

### Debug Log References

- Worktree không có `zhvi/.venv`; pytest chạy qua `/home/falcol/NgheTruyen/zhvi/.venv/bin/python` với cwd worktree (pythonpath `src`).
- Green: 12 passed in 0.24s.
- Ruff 0.15.20: No issues found.

### Completion Notes List

- 6 metamorphic + 6 dictionary unit, fixture `tmp_path` mini dict, không network/model.
- Unused auto: `publish_revision` entry `玄女` (không có trong SRC) rồi dịch lại — SHA giữ nguyên, entry có trong `entries.tsv`.
- Reorder: QualityOverrides đảo dòng + AutoEntry đảo thứ tự; `build_revision` id khớp.
- Whole/chapter: 2 chương, concat byte-equal.
- Resume: KeyboardInterrupt sau vp_plan lần 1, resume exit 0, SHA = clean.
- Rollback: glossary đổi SHA; rollback pointer; output mới SHA = v1.
- Pattern: `小{n}` không nuốt literal `小天才`; dict không literal thì pattern vẫn khớp prefix (đối chứng).

### File List

- zhvi/tests/test_metamorphic.py
- zhvi/tests/test_dictionary_units.py
- _bmad-output/implementation-artifacts/5-3-metamorphic-dictionary-unit-test-suite.md

## Change Log

- 2026-09-06: Story created + implemented (tests only + story markdown).
