---
baseline_commit: b168642
---

# Story 5.4: CLI integration end-to-end + documentation

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a người vận hành zhvi,
I want integration test chạy happy path đầy đủ `zhvi translate FILE -o OUT` (snapshot → discover → book-auto learn → freeze → translate → QA → export → report) trên fixture truyện nhỏ, và tài liệu cập nhật,
So đó người dùng mới chạy được toàn vòng đời bằng một lệnh.

## Acceptance Criteria

1. **Given** fixture TXT tiếng Trung nhỏ trong repo test **When** chạy `zhvi translate fixture.txt -o out.vi.txt` (subprocess hoặc invoke Typer) **Then** output + manifest tồn tại, manifest chứa run ID + revision ID + output SHA-256; lệnh `--no-learn`, `status`, `export`, `doctor` đều chạy đúng vai trò.
2. README/docs zhvi mô tả kiến trúc mới, CLI contract, vòng correction (entry → revision → rerun) và trạng thái khóa của global auto-promotion.
3. Toàn bộ suite `zhvi` pass.

## Tasks / Subtasks

- [x] Task 1 — Quyết định CLI `--no-learn` (AC: #1) — **THÊM flag, không map lệnh khác**
  - [x] 1.1 `zhvi translate` thêm `no_learn: bool = typer.Option(False, "--no-learn")`
  - [x] 1.2 Default (không flag) = LEARN rồi TRANSLATE. `--no-learn` = bỏ LEARN, dịch bằng revision active hiện tại (hành vi `translate_project` hôm nay)
  - [x] 1.3 KHÔNG nhét LEARN vào vòng lặp block / `translate_project` (AD-4). Orchestrate ở CLI trước khi gọi pipeline
- [x] Task 2 — Wire LEARN vào happy-path `translate` (AC: #1)
  - [x] 2.1 Extract `_run_book_learn(p, st, rev, cfg, drev, dic) -> dict` từ thân `learn()` hiện tại (discovery → candidates → evaluate → book `run_promotion` nếu `cfg.learning.enabled and auto_scope=="book"`). `learn` command gọi lại helper này. Không chạy `--global` trên happy path
  - [x] 2.2 `translate` khi `not no_learn`: snapshot + upsert source (cùng pattern `import_`) → `_learn_context`/`_run_book_learn` dưới `project_lock` → rồi `translate_project` (lock lần 2, snapshot no-op). `learning.enabled=false` cũng skip LEARN (cùng nghĩa `--no-learn`)
  - [x] 2.3 `-p` không FILE: `_source_for_translate` lấy snapshot đã import (pipeline-contract `translate -p --no-learn`). Chưa import → `_require_latest_source` fail
- [x] Task 3 — Fixture + E2E tests `zhvi/tests/test_cli_e2e.py` (AC: #1, #3)
  - [x] 3.1 NEW `zhvi/tests/fixtures/mini_story.txt` — TXT ZH nhỏ (2–3 chương, vài câu; đủ CJK để discovery ghi observation; dùng production `crawler/vietphrase/dicts` như `test_cli.py` để QA leftover_cjk không fail)
  - [x] 3.2 `test_happy_path_translate_writes_manifest`: copy fixture → tmp, `CliRunner.invoke(app, ["translate", src, "-o", out, "--dict-dir", DICT, "--json"])` exit 0; `out` tồn tại; `manifest.json` dưới `.zhvi/runs/<run_id>/` có `run_id`, `dictionary_revision` (revision ID), `output.sha256` (64 hex). Report JSON có `run_id`. Observation count > 0 (LEARN đã chạy)
  - [x] 3.3 `test_no_learn_skips_discovery`: `--no-learn` trên fixture mới → exit 0, output tồn tại, `observations` rỗng (0 row). Không gọi `zhvi learn`
  - [x] 3.4 `test_status_export_doctor_after_translate`: sau happy path: `status -p PROJECT` exit 0, JSON `status=="exported"` + `run_id`; `export -p PROJECT -o re.txt` exit 0, SHA khớp output gốc; `doctor --dict-dir DICT` exit 0
  - [x] 3.5 Không network/model. Skip nếu `DICT_DIR` thiếu (cùng `pytest.mark.skipif` `test_cli.py`)
- [x] Task 4 — README zhvi (AC: #2) — sửa `zhvi/README.md`, không tạo file docs mới
  - [x] 4.1 Kiến trúc 2 pha: LEARN (discover → candidate → book-auto → freeze revision) rồi TRANSLATE (chỉ đọc revision đã pin). Cập nhật mermaid/luồng; bỏ mô tả "1 lệnh = import → VP → export" nếu thiếu LEARN
  - [x] 4.2 CLI contract: bảng/lệnh `init`, `import`, `learn` (`--global`), `translate` (`--no-learn`, `--refresh-revision`, `-o`, `--json`), `terms list/accept/reject/revoke`, `dict diff/rollback`, `explain`, `status`, `export`, `doctor`. Happy path 1 lệnh. Không còn `--hachimi`/`--qwen`/profile
  - [x] 4.3 Vòng correction: sửa entry (`glossary.manual.tsv` hoặc `zhvi terms accept`) → revision mới (`--refresh-revision` / publish) → rerun affected blocks → QA → export atomic. Không sửa output text
  - [x] 4.4 Global auto-promotion **đang khóa (AD-14)**: `zhvi learn --global` fail-closed khi chưa có golden manifest `approved`; `raw_china/expect*` không tự thành golden. Cập nhật checklist trạng thái epic 2–5 cho khớp repo (không bịa "chưa làm")
- [x] Task 5 — Regression CLI cũ + suite (AC: #3)
  - [x] 5.1 Test CLI cũ trong `test_cli.py` đang gọi `translate` **không** nhằm LEARN: thêm `--no-learn` để giữ semantics cũ (usage/input/status/export/review/vp-only/happy-path-noop). `test_model_flags_removed` không đổi
  - [x] 5.2 `cd zhvi && .venv/bin/python -m pytest tests/ -q` — toàn suite pass (kỳ vọng ~291+ mới, 2 skipped)
  - [x] 5.3 Ruff sạch file đụng

## Dev Notes

### Quyết định `--no-learn` (bắt buộc, không để dev đoán)

Flag **chưa có** trên CLI. FR10 + pipeline-contract dòng 56 ghi `zhvi translate -p PROJECT --no-learn`. Map sang lệnh hiện có **sai vai trò**:

| Ứng viên | Vì sao không đủ |
|---|---|
| `zhvi learn` rồi `zhvi translate` | Hai lệnh; ngược với "1 lệnh happy path" và không phải `--no-learn` |
| `learning.enabled=false` trong toml | Config, không phải CLI flag AC yêu cầu |
| `translate_project` không đụng DB học | Đúng cho TRANSLATE, nhưng CLI happy path **phải** LEARN trước khi freeze |

**Làm:** thêm `--no-learn`. Default translate = LEARN (book only) + TRANSLATE. `--no-learn` = TRANSLATE thuần.

### AD ràng buộc

- **AD-4** — LEARN kết thúc bằng revision ready; TRANSLATE chỉ đọc freeze, không mutate candidate trong vòng lặp block. Helper LEARN chạy **trước** `translate_project`.
- **AD-11** — manifest đã có `run_id`, `dictionary_revision`, `output.sha256` (`export.write_manifest`). E2E **assert field có sẵn**, không đổi schema trừ khi thiếu.
- **AD-14** — happy path **không** gọi `run_global_promotion`. README nói rõ khóa. `learn --global` giữ nguyên 4.3.
- **AD-10** — QA fail → không export (5.1). Fixture phải dịch sạch leftover_cjk với production dict.
- **AD-13** — LEARN dưới `project_lock`; `translate_project` lấy lock riêng (flock không reentrant — **không** gọi learn bên trong `_translate_locked`). Story 3.4 đã verify publish + project_lock không deadlock.
- **AD-1** — không model/network.

### API có sẵn — REUSE, không viết lại

| Cần | Dùng | File |
|---|---|---|
| LEARN sequence | `run_discovery` / `build_candidates` / `evaluate_candidates` / `run_promotion` | đã wire trong `cli.learn` |
| Preamble LEARN | `_learn_context`, `_require_latest_source` | `cli.py` |
| Snapshot | `import_snapshot` + `State.upsert_source_revision` | `cli.import_` |
| TRANSLATE | `TranslateRequest`, `translate_project` | `pipeline.py` — **không thêm field learn** |
| Manifest | `write_manifest` → `run_id`, `dictionary_revision`, `output.sha256` | `export.py:87-104` |
| Status | `st.status_info()` | `state.py:815` |
| Export lại | `zhvi export -p` | `cli.export` |
| Doctor | `run_doctor` | `doctor.py` |
| CLI test | `CliRunner` (`test_terms.py`, `test_golden.py`) hoặc `subprocess` (`test_cli.py`) | **E2E dùng CliRunner** (test source hiện tại, không phụ thuộc binary cũ) |
| Dict production | `REPO_ROOT / "crawler/vietphrase/dicts"` | `test_cli.py` |

### Manifest shape (assert đúng key)

```json
{
  "run_id": "<uuid>",
  "dictionary_revision": "<sha256 64 hex>",
  "output": {"path": "...", "sha256": "<64 hex>"}
}
```

Đường dẫn: `<workspace>/.zhvi/runs/<run_id>/manifest.json`. Happy path không `-p` → workspace `<stem>.zhvi/` cạnh file (`workspace_for`).

### Observation assert

Không có `list_observations` public. Test: `State(db).conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]`. `--no-learn` → 0; default translate → > 0.

### Phạm vi KHÔNG làm

- Không `learn --global` trên happy path; không bật AD-14.
- Không đổi `translate_project` / fingerprint / QA gates / golden / registry.
- Không tạo file markdown ngoài `zhvi/README.md` + story này.
- Không sửa test metamorphic/dictionary/golden trừ khi regression do đổi default CLI.
- Không rename/xóa lệnh `learn` / `discover` (vẫn là lệnh tường minh).

### Previous story intelligence

- 5.1: QA chặn export leftover_cjk — fixture E2E phải cover CJK (production dict, pattern `test_cli.py` `"第一章\\n\\n凌天看着前方。\\n"` đã pass).
- 5.3: fixture tự chứa + không network; comments Việt không dấu; import module top.
- 3.5: `CliRunner` + JSON stdout; `learn` đã composite discovery→candidate→evidence→promotion.
- 1.5: README 3.0 + doctor/status — 5.4 **cập nhật** README (epic 2–5 đã có code, checklist README đang `[ ]` là stale).
- 4.3: global fail-closed — README phải nói khóa, không mô tả như đã bật.

### Git intelligence

HEAD `b168642` — 5.1 + 5.3 committed. Suite 291 passed / 2 skipped. `cli.py` đã có `learn`/`discover`/`status`/`export`/`doctor`/`terms`/`golden`/`dict`; thiếu `--no-learn`. README luồng còn pre-learner.

### File structure

| Path | Việc |
|---|---|
| `zhvi/src/zhvi/cli.py` | UPDATE: `--no-learn`, extract `_run_book_learn`, wire trước `translate_project` |
| `zhvi/README.md` | UPDATE: kiến trúc, CLI, correction, AD-14 |
| `zhvi/tests/fixtures/mini_story.txt` | NEW |
| `zhvi/tests/test_cli_e2e.py` | NEW |
| `zhvi/tests/test_cli.py` | UPDATE: `--no-learn` trên translate không phải E2E |
| `zhvi/src/zhvi/pipeline.py` | KHÔNG sửa |

## Dev Agent Record

### Agent Model Used

Grok 4.6

### Debug Log References

- Red: `--no-learn` exit 2; default translate observation count 0.
- Green E2E 4 passed (~2 min). Ruff clean.
- Review 2 trục: README `-p` khong FILE; `learning.enabled=false` van goi `_learn_context`; docstring EN.
- Fix: `_source_for_translate` dung snapshot khi thieu FILE; skip learn khi `enabled=false`; README `--no-learn -p`.
- Full suite: 295 passed / 2 skipped in 628.64s.

### Completion Notes List

- Them `--no-learn` tren `zhvi translate`. Default = LEARN (book only, khong `--global`) roi TRANSLATE. AD-4: learn o CLI, khong trong `translate_project`.
- `_run_book_learn` dung chung voi `zhvi learn`. `learning.enabled=false` skip LEARN giong `--no-learn`.
- `-p` khong FILE: dung snapshot da import (`_source_for_translate`) — khop pipeline-contract `translate -p --no-learn`.
- E2E: fixture `tests/fixtures/mini_story.txt`; manifest `run_id` + `dictionary_revision` + `output.sha256`; `--no-learn` observation=0; status/export/doctor.
- README: 2 pha LEARN/TRANSLATE, CLI contract, vong correction, AD-14 khoa.

### File List

- zhvi/src/zhvi/cli.py
- zhvi/README.md
- zhvi/tests/test_cli.py
- zhvi/tests/test_cli_e2e.py
- zhvi/tests/fixtures/mini_story.txt
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-09-06: Story created (ready-for-dev).
- 2026-09-06: Implemented CLI E2E + `--no-learn` + README (review).
- 2026-09-06: Close-out review (grok-4.5, NO BLOCK) — Status done.
