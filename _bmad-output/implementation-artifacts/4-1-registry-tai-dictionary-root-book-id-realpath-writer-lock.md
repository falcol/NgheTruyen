---
baseline_commit: 5e2d8822c7fbc4158eb5f046020e8b1f89083ee9
---

# Story 4.1: Registry tại dictionary root — book_id, realpath, writer lock

Status: done

## Story

As a hệ thống học toàn cục,
I want registry SQLite tại `<dict_dir>/.zhvi-registry/state.sqlite3` xác định duy nhất qua `realpath(dict_dir)`, `zhvi init` tạo stable `book_id`, một registry writer lock,
So đó chỉ một writer được mutate global state/projection và copy project không giả tạo truyện độc lập.

## Acceptance Criteria

1. **Given** dictionary root (có thể qua symlink) **When** truy cập registry **Then** registry resolve qua realpath; mỗi resolved root đúng một registry + một writer lock (`locks/registry.lock`).
2. `zhvi init` tạo `book_id` một lần lưu trong `zhvi.toml`; bản copy project giữ cùng ID nên registry không tính là truyện độc lập.
3. Hai writer concurrently: một bị chặn với thông báo lock rõ ràng; không giữ lock trong discovery.

## Tasks / Subtasks

- [x] Task 1 — Registry module `zhvi/src/zhvi/registry.py` (AC: #1)
  - [x] 1.1 `resolve_registry_dir(dict_dir) -> Path`: `Path(os.path.realpath(dict_dir)) / ".zhvi-registry"` — realpath resolve symlink trước khi xác định registry (data-model "Concurrency" #2)
  - [x] 1.2 `RegistryState`: SQLite tại `state.sqlite3`, copy pattern `State.__init__` (WAL, `synchronous=FULL`, `foreign_keys=ON`, bảng `meta(key, value)`, `REGISTRY_SCHEMA_VERSION = 1`, migration additive AD-19 chuẩn bị cho 4.2)
  - [x] 1.3 `RegistryError(RuntimeError)` — error type riêng của registry
- [x] Task 2 — Registry writer lock (AC: #1, #3)
  - [x] 2.1 `registry_lock(registry_dir)` contextmanager: flock `LOCK_EX | LOCK_NB` trên `locks/registry.lock` (mkdir `locks/` lazy), copy pattern `project_lock` (project.py:137-154)
  - [x] 2.2 Bị chặn → raise `RegistryError` với thông báo rõ ràng: path lock file + process đang giữ (pid) theo pattern message `project_lock`
- [x] Task 3 — Tests `zhvi/tests/test_registry.py` (AC: #1, #2, #3)
  - [x] 3.1 Symlink dict_dir: 2 path (thật + symlink) resolve cùng registry dir; `RegistryState` mở từ cả 2 → cùng file DB (`st_dev`/`st_ino` hoặc resolve path bằng nhau)
  - [x] 3.2 Lock dedupe qua symlink: giữ lock qua path A, acquire qua path B → `RegistryError` (chứng minh 1 resolved root = 1 lock)
  - [x] 3.3 Concurrent: 2 fd mở lock file riêng trong cùng process → fd thứ 2 chặn `BlockingIOError` (flock gắn open file description — cùng process vẫn conflict); message chứa path
  - [x] 3.4 book_id stability: `create_project` tạo `book_id` hex; gọi lần 2 (re-init idempotent) giữ nguyên ID; copy cả project tree sang chỗ khác → `Project.book_id` bằng ID gốc (AC #2)
  - [x] 3.5 Discovery không giữ registry lock: giữ `registry_lock` trong khi `run_discovery` chạy (fixture book nhỏ) → discovery hoàn thành bình thường (không cần/không chờ registry lock)
- [x] Task 4 — Full suite pass (AC: toàn bộ)
  - [x] 4.1 `pytest zhvi/tests` xanh toàn bộ (baseline 232 passed / 2 skipped → 241 passed / 2 skipped)

## Dev Notes

### Invariants ràng buộc

- **AD-13** — `realpath(dict_dir)` xác định duy nhất registry tại `<dict_dir>/.zhvi-registry/`; chỉ registry writer lock được mutate global state/projection. Story này đặt nền: identity + lock; chưa có mutation global nào (4.2 ingest, 4.3 promotion).
- **AD-17** — `zhvi init` tạo stable `book_id`; copy giữ ID không tính truyện độc lập. Phần code ĐÃ CÓ (project.py:109-118 tạo + project.py:71-78 đọc); story này bổ sung test chứng minh stability — KHÔNG viết lại logic.
- **AD-19** — registry schema migration additive (chỉ add/transform); schema v1 tối giản chỉ `meta` — bảng evidence/candidate/active pointer toàn cục thuộc 4.2/4.3, thêm qua `REGISTRY_SCHEMA_VERSION` bump theo pattern `State._migrate`.
- **data-model "Concurrency"** — không giữ global lock trong discovery; chỉ lock khi build/activate revision (4.3). Discovery hiện tại hoàn toàn book-local — test 3.5 chốt invariant này để 4.2/4.3 không phá.

### Quyết định thiết kế story

- Registry khởi tạo LAZY: `RegistryState`/`registry_lock` mkdir `.zhvi-registry/` (+ `locks/`) lần đầu mở. `zhvi init` KHÔNG đụng registry — init là book project scope; dictionary root có thể chia sẻ nhiều book. Không tạo registry khi không dùng.
- `RegistryState` tách class riêng trong module `registry.py`, KHÔNG import/nhét vào `state.py` — hai mutation scope khác nhau (book DB vs global registry), AD-13.
- dict_dir từ config là `str`, có thể relative (theo cwd — cùng semantics loader dictionaries đang dùng). Test dùng absolute path `tmp_path` để không phụ thuộc cwd.
- KHÔNG thêm CLI command, KHÔNG đụng doctor/status — AC không yêu cầu; 4.2 sẽ expose ingest entry point.
- Schema v1 chỉ `meta(key PRIMARY KEY, value TEXT)` + row `schema_version=1`. Đủ để registry tồn tại, idempotent mở lại, và có chỗ bump version cho 4.2.

### API có sẵn

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Pattern lock + message lỗi | `project_lock` (flock LOCK_EX\|LOCK_NB, ghi pid, raise khi BlockingIOError) | project.py:137-154 |
| Pattern SQLite init + meta + migration | `State.__init__` / `State._migrate` (WAL, synchronous=FULL, SCHEMA_VERSION) | state.py:338-394 |
| book_id tạo/đọc | `create_project` / `Project.book_id` | project.py:89-127, 71-78 |
| Discovery fixture | pattern `_learned`/discovery fixture từ test_discovery.py | tests/test_discovery.py |
| Registry layout reference | structural seed `.zhvi-registry/` | ARCHITECTURE-SPINE.md:202-206 |

### Previous story intelligence (3.5)

- Comments Việt không dấu; imports top; lint hook chặn F401/F841 từng edit — imports + usage cùng edit.
- Edit tool khó match chuỗi chứa CJK — edit tránh đụng dòng CJK.
- Suite baseline 232 passed / 2 skipped.
- CLI JSON stdout (ensure_ascii=False), log stderr `err_console` — không áp dụng story này (không CLI mới).

### Project Structure Notes

- `zhvi/src/zhvi/registry.py` mới — module registry (identity + state + lock).
- `zhvi/tests/test_registry.py` mới — mọi test story.
- KHÔNG sửa file hiện có trừ khi test lộ bug (lúc đó comment `[Note]` + báo, không âm thầm fix).
- Đặt cạnh `project.py`/`state.py` ở top-level `zhvi/` (không vào `learning/` — registry là state/infrastructure, không phải learner).

### Phạm vi KHÔNG làm

- Không bảng global candidates/evidence/active pointer toàn cục (4.2/4.3).
- Không ingest evidence, không global promotion, không `AutoVietPhrase.txt` materialize.
- Không CLI/doctor mới; không đụng `zhvi init` logic (đã đúng).
- Không đổi project_lock/state.py hiện có.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1 (lines 351–363)]
- [Source: ARCHITECTURE-SPINE.md — AD-13 (line 115), AD-17 (line 139), structural seed (lines 201–212), conventions table (line 164)]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/data-model.md — registry layout (lines 86–89), Concurrency (lines 109–121)]
- [Source: zhvi/src/zhvi/project.py — book_id (71-78, 109-118), project_lock (137-154)]
- [Source: zhvi/src/zhvi/state.py — State.__init__/_migrate pattern (338-394)]
- [Source: zhvi/tests/test_discovery.py — discovery fixture]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_registry.py RED (ModuleNotFoundError zhvi.registry) → GREEN 9/9.
- Full suite 241 passed / 2 skipped (baseline 232 + 9 mới, 0 regression).
- Ruff: 0 issue trên 2 file mới.
- venv: `.venv/bin/python -m pytest` từ `zhvi/` (system python thiếu module zhvi).

### Completion Notes List

- `resolve_registry_dir`: `os.path.realpath(dict_dir)` resolve symlink trước khi ghép `.zhvi-registry` — 2 path (thật + symlink) cùng root resolve về một registry (test so sánh path + `st_ino` DB file).
- `RegistryState`: copy pattern `State.__init__` (WAL, `synchronous=FULL`, `foreign_keys=ON`); schema v1 chỉ `meta` + row `schema_version=1`; migration additive AD-19 theo pattern `_migrate`; check "DB mới hơn binary" raise `RegistryError`. Registry lazy-init (mkdir khi mở) — `zhvi init` không đụng registry.
- `registry_lock`: copy pattern `project_lock` — flock `LOCK_EX|LOCK_NB` trên `locks/registry.lock` (mkdir lazy), ghi pid, chặn → `RegistryError("Một process khác đang giữ lock registry: <path>")`. Lock dedupe qua symlink test bằng acquire path A giữ + acquire path B chặn.
- Concurrent test cùng process dùng 2 fd riêng — flock gắn open file description nên vẫn conflict (không cần subprocess).
- book_id: code có sẵn từ trước (project.py) — chỉ thêm test: re-init idempotent giữ ID; `shutil.copytree` project giữ ID (AC #2 — nền cho 4.2 dedupe theo book_id).
- Discovery không giữ registry lock: giữ `registry_lock` quanh `run_discovery` (dict root cùng thư mục) — discovery chạy bình thường, chứng minh book-local, không chờ/không cần global lock (data-model Concurrency).
- **Review fixes (2 trục Opus, 11 findings — tất cả đã xử lý):** Standards — import `run_discovery` lên module top (MED), bỏ dead store `self.path`, comment drift close-conn trước raise, `SRC` constant lên top. Spec — message lock chặn thêm pid holder đọc từ lock file + test assert `pid=` (MED), bỏ assertion `st_ino` tautological, assert layout `locks/registry.lock` khi giữ lock, assert book_id hex 32 ký tự, copy test thêm `create_project(copy_root)` (ghép luồng copy + re-init thật), test lazy-init (`zhvi init` không tạo registry + mkdir khi mở) + guard schema mới hơn raise RegistryError. Skip: File List sprint-status (workflow metadata do automator quản, consistent các story trước).

### File List

- zhvi/src/zhvi/registry.py (mới)
- zhvi/tests/test_registry.py (mới)

## Change Log

- 2026-09-05: Story created — ultimate context engine analysis completed.
- 2026-09-05: Story 4.1 implementation — registry.py (realpath identity + RegistryState v1 + registry_lock), 9 test mới; full suite 241/2.
- 2026-09-06: Review fixes (11 findings, 2 trục Opus) — pid holder trong lock message, bỏ st_ino tautology, layout/hex/copy-flow asserts, lazy-init + schema-guard tests (11 total).
