---
baseline_commit: cac8aeffb7e87fa229d1125644c1404f59978ebf
---

# Story 3.1: Discovery toàn truyện tạo observation

Status: done

## Story

As a hệ thống học theo truyện,
I want discovery chạy trước khi dịch, thu n-gram CJK 2–8 ký tự, tần suất tuyệt đối + theo chương, left/right context diversity, PMI, chuỗi bị tách thành entry một ký tự, unknown span, segmentation đa phương án, pattern tên riêng (người/địa danh/môn phái/công pháp/cảnh giới),
So đó có dữ liệu thô để sinh candidate mà không đụng engine.

## Acceptance Criteria

1. **Given** một source revision đã import **When** chạy discovery **Then** observation ghi vào bảng `observations` của book SQLite; discovery không nạp observation vào engine (không ghi dictionary file, không đổi trie/fingerprint).
2. Observation deterministic: cùng source revision + cùng active dictionary revision chạy hai lần ra cùng tập observation (replace, không append).
3. Unit test với fixture chứa tên riêng lặp và cụm bị phân đoạn mảnh.

## Tasks / Subtasks

- [x] Task 1: Migration schema v3 → v4 — bảng `observations` (AC: 1)
  - [x] `state.py`: `SCHEMA_VERSION = 4`; thêm DDL vào `_SCHEMA` (CREATE TABLE IF NOT EXISTS — additive, AD-19); `_migrate` thêm nhánh `if from_version < 4` (bảng do `_SCHEMA` tạo, nhánh chỉ set version — theo pattern v2→v3 story 2.2)
  - [x] State method `replace_observations(source_revision_id, rows)` — một transaction: `DELETE FROM observations WHERE source_revision_id=?` rồi INSERT toàn bộ rows đã sort theo `ngram`
- [x] Task 2: Package `learning/` + module `learning/discovery.py` (AC: 1, 2)
  - [x] Tạo `zhvi/src/zhvi/learning/__init__.py` (docstring ngắn) + `discovery.py` — module LEARN đầu tiên theo Structural Seed
  - [x] `run_discovery(state, *, source_revision, dictionary, dictionary_revision_id) -> DiscoverySummary` thực hiện pipeline 6 bước trong Dev Notes (counting → stats → engine flags → patterns → rows → ghi DB). Đổi signature so với draft: bỏ param `project` (snapshot_path có trong SourceRevisionRow) — ghi Completion Notes.
  - [x] Constants pin: `NGRAM_MIN = 2`, `NGRAM_MAX = 8`; mọi iteration/dump JSON sort key để deterministic
- [x] Task 3: CLI `zhvi discover -p PROJECT` (AC: 1)
  - [x] Typer command `discover` theo pattern `@app.command()` trong `cli.py`; flow: open_project → guard chưa import (`State.latest_source_revision()` trả None → in lỗi + exit ≠ 0) → `ensure_active_revision(dict_dir, project)` (refresh=False mặc định) → `load_revision_dictionary(project, revision_id)` (chỉ ĐỌC) → decode snapshot → `run_discovery` dưới `project_lock(project)` (dùng default name `"translate"` — AD-13 một writer cho book state, không thêm lock name mới) → in JSON summary
  - [x] Summary JSON: `{source_revision, dictionary_revision, observations: <n>, flags: {single_char_run, unknown, alt_segmentation, repetition_unstable}, patterns: <n rows có pattern_hits>}`
  - [x] Fix gap phát hiện khi làm: `zhvi import-` giờ upsert `source_revisions` vào DB ngay lúc import (trước đó chỉ translate flow ghi — discover đọc DB sẽ không thấy revision đã import)
- [x] Task 4: Tests `tests/test_discovery.py` (AC: 2, 3)
  - [x] Fixture mini dict (theo pattern test_run_pin): entry multi-char (`玄天`) + single-char (`紫`,`霄`,`山`,`宗`,`诀`)
  - [x] Fixture text 2 chương: `李慕白` lặp cả 2 chương (không có trong dict), `紫霄山` bị tách single-char
  - [x] Assert: counts tuyệt đối + theo chương; `pattern_hits` person/place; `is_single_char_run=1` + `is_unknown=0` cho `紫霄山`; `is_unknown=1` cho `李慕白`
  - [x] Determinism: chạy `run_discovery` 2 lần → cùng rows (trừ `created_at`)
  - [x] Không đụng engine: dictionary fingerprint + entry_count không đổi
  - [x] Regression: full suite xanh — 197 passed / 2 skipped (baseline 189/2 + 8 tests mới; test_state migrate test cập nhật assert version 4 theo pattern story 2.2)

## Dev Notes

### Invariants ràng buộc (Architecture Spine)

- **AD-4** — discovery là pha LEARN, CHỈ ĐỌC dictionary active (load qua `load_revision_dictionary`); tuyệt đối không mutate trie/dictionary/candidate state.
- **AD-8** — book SQLite sở hữu observation; observation là state, không phải projection.
- **AD-13** — ghi observations dưới `project_lock` (một writer cho book state).
- **AD-18** — discovery đếm trên text giản thể + NFC (cùng không gian index với trie: `to_simplified` + `normalize_nfc` từ `vietphrase/loader.py`), source gốc giữ `ngram_original` làm provenance.
- Spec: `data-model.md` "Không giữ global lock trong discovery" — không đụng registry trong story này (registry là Epic 4).

### API hiện có cần dùng (đọc trước khi code)

| Cần gì | Dùng | Vị trí |
|---|---|---|
| Source revision | `State.latest_source_revision()` → `SourceRevisionRow` (đọc `snapshot_path`, decode theo `encoding`) | `zhvi/src/zhvi/state.py` |
| Phân chương | `parse_document(text, chapter_detection=..., chapter_regex=...)` → `Document.nodes` (mỗi `Node` có `chapter_id`, `.content()`, `.is_translatable`) | `zhvi/src/zhvi/document.py` |
| Dictionary active | `ensure_active_revision(dict_dir: Path, project: Project, *, global_glossary=None, patterns=True, refresh=False) -> str` (revision_id) + `load_revision_dictionary(project, revision_id) -> Dictionary`; xem cách `_translate_locked` gọi trong `pipeline.py` phase 3 | `zhvi/src/zhvi/revision.py:413`, `revision.py:448` |
| CJK detection | `CJK_RE` đã có — reuse, không viết regex mới | `zhvi/src/zhvi/document.py:21` |
| Simplified/NFC | `to_simplified(text, dic.trad_simp)`, `normalize_nfc(text)` | `zhvi/src/zhvi/vietphrase/loader.py` |
| Engine flags | `vp_plan(dic, text, beam=...) -> VpDraft` — có sẵn `unknown_spans`, `single_char_ratio`, `lattice_margin`, `lattice_entropy`, `collapsed_spans`, `warnings` | `zhvi/src/zhvi/vietphrase/lattice.py:358`, types trong `vietphrase/trace.py` |
| Top-K segmentation | `best_paths(dic, text, k=...)` — so 2 path đầu khác nhau → alt_segmentation | `zhvi/src/zhvi/vietphrase/lattice.py` |
| CLI pattern | Typer `@app.command()`, precede như `inspect` (open_project → State → close) | `zhvi/src/zhvi/cli.py` |
| Lock | `project_lock(project)` — giữ default name, exit code 5 khi conflict | `zhvi/src/zhvi/project.py:138` |

**Lưu ý offsets của `VpSpan`/`SourceSpan` là simplified-space** — story này CHỈ dùng flags/aggregate, KHÔNG cần map offset về source gốc. Occurrence spans chi tiết (AD-17) thuộc evidence/ingest pha sau (3.3, Epic 4) — không làm trước.

### Pipeline discovery (6 bước — thứ tự bắt buộc)

1. **Đọc source**: decode snapshot theo encoding → `parse_document` → lấy `translatable_nodes()`.
2. **Counting pass** (một lượt duy nhất, thuê từng node): với mỗi node, text = `normalize_nfc(to_simplified(node.content(), dic.trad_simp))`; tách thành các CJK run liên tiếp bằng `CJK_RE` import từ `zhvi.document` (range `[㐀-䶿一-鿿豈-﫿]` — KHÔNG định nghĩa regex mới, đã có ở `document.py:21`); trong mỗi run đếm: unigram `u`, bigram liền kề `b`, mọi n-gram n=2..8 kèm (chapter_id, left char, right char — left/right chỉ tính khi kề cùng run).
3. **Stats**: `total_count`, `chapters = {ordinal: count}`, `left/right_contexts = {char: count}`; entropy Shannon `H = -Σ p log2 p` trên phân phối context (rỗng → 0); `min_pmi` = min PMI trên các bigram liền kề bên trong n-gram với `PMI(xy) = log2(count(xy) * N / (count(x) * count(y)))`, `N` = tổng unigram CJK của toàn văn bản translatable.
4. **Engine flags** (per node, gọi `vp_plan` với cùng config render mặc định): mark n-gram `is_single_char_run` nếu nằm trọn trong đoạn liên tiếp ≥2 **entry một ký tự** (VpSpan dài 1 có entry — đúng nghĩa "chuỗi bị tách thành entry một ký tự" của epics; KHÔNG tính unknown edge, đó là flag riêng); `is_unknown` nếu n-gram **chứa** ký tự thuộc `unknown_spans` (overlap — không yêu cầu phủ tròn); `alt_segmentation` nếu `best_paths(k=2)` hai path đầu khác segmentation HOẶC warning `SEGMENTATION_INSTABILITY`; `repetition_unstable` nếu nằm trong `collapsed_spans`.
5. **Pattern tên riêng**: n-gram khớp heuristic seed (list hằng số trong `discovery.py`, match = n-gram KẾT THÚC bằng suffix của category HOẶC BẮT ĐẦU bằng token境界) → `pattern_hits` = list category name. Đây chỉ là tín hiệu observation — KHÔNG sinh target (AD-6 thuộc story 3.2). Seed lists:
   - `person`: họ phổ biến — `王李张刘陈杨黄赵周吴徐孙马朱胡郭何林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余于杜叶程魏苏吕丁任卢姚沈钟姜崔谭陆范汪廖石金韦贾夏傅方白邹熊孟秦邱江尹薛闫段雷龙黎史陶贺毛郝顾龚邵万钱严覃武戴莫孔向汤`
   - `place`: suffix `山城峰谷岛洲海江湖河潭洞穴宫殿楼阁台坊郡州县国家族`
   - `sect`: suffix `派宗门教盟阁楼谷庄堂寺观庵`
   - `technique`: suffix `功法诀经术拳剑刀掌指腿步阵图录典章谱`
   - `realm`: token đầu `炼气筑基金丹元婴化神炼虚合体大乘渡劫` HOẶC suffix `境期层重`
6. **Ghi DB**: build rows (id = sha256(`source_revision_id` + `\x00` + ngram)), gọi `state.replace_observations(...)`.

### DDL bảng observations

```sql
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    source_revision_id TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL,
    ngram TEXT NOT NULL,             /* giản thể NFC — matching key */
    ngram_original TEXT NOT NULL,    /* dạng gặp lần đầu — provenance */
    length INTEGER NOT NULL,         /* 2..8 */
    total_count INTEGER NOT NULL,
    chapter_count INTEGER NOT NULL,
    chapters_json TEXT NOT NULL,     /* {"<ordinal>": count} sort key */
    left_contexts_json TEXT NOT NULL,
    right_contexts_json TEXT NOT NULL,
    left_entropy REAL NOT NULL,
    right_entropy REAL NOT NULL,
    min_pmi REAL NOT NULL,
    is_single_char_run INTEGER NOT NULL DEFAULT 0,
    is_unknown INTEGER NOT NULL DEFAULT 0,
    alt_segmentation INTEGER NOT NULL DEFAULT 0,
    repetition_unstable INTEGER NOT NULL DEFAULT 0,
    pattern_hits_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(source_revision_id, ngram)
);
CREATE INDEX IF NOT EXISTS idx_observations_rev
    ON observations(source_revision_id, total_count DESC);
```

`dictionary_revision_id` bắt buộc — observation chỉ có nghĩa so với trạng thái từ điển đã thấy (evidence story 3.3 đọc kèm).

### Quy tắc deterministic (AC 2)

- Replace-not-append trong MỘT transaction (`replace_observations`).
- Mọi dict→JSON dump với `sort_keys=True`; rows INSERT theo thứ tự `ngram`.
- Không đưa `created_at`/random/timestamp vào nội dung quyết định tập observation.
- `ngram_original` = dạng gặp đầu theo thứ tự duyệt node cố định (ordinal tăng dần) — deterministic theo construction.

### Phạm vi KHÔNG làm (chống scope creep)

- Không build candidate, không evidence, không promotion (3.2–3.4).
- Không lệnh `zhvi learn` composite — thuộc story 3.4 khi đủ pha.
- Không config `[learning]` mới — constants trong `discovery.py`; wiring config làm ở story cần ngưỡng (Fast-path Assumption: ngưỡng là default, không phải invariant).
- Không occurrence span chi tiết, không đụng registry/global (Epic 4).
- Bảng `term_candidates` legacy tồn tại trong schema — KHÔNG đụng, KHÔNG reuse (3.2 sẽ thay thế đúng cách).

### Previous story intelligence (epic 2)

- Review 2 trục (standards + spec) từng bắt: lazy import trong function body — vi phạm CLAUDE.md, imports phải top-of-module. Đã revert ở 2.5. **Tuân thủ ở story này.**
- `[Note]` tồn tại: `make_entry` import unused ở đâu đó trong code cũ — đừng copy pattern đó.
- Suite baseline: 189 passed / 2 skipped — story phải giữ nguyên (chạy full `pytest` trước khi claim xong).
- Commit style: `feat(zhvi): ...` tiếng Anh, ngắn, nêu why.

### Project Structure Notes

- Module mới `zhvi/src/zhvi/learning/` đúng Structural Seed (`learning/` cho discovery, candidate, evidence, promotion). Flat-file precedent: các module epic 1–2 đặt flat (`revision.py`, `projection.py`) — `learning/` là package ĐẦU TIÊN sau `vietphrase/`, `quality/`. Giữ `__init__.py` trống giống `quality/__init__.py` (107B, chỉ re-export tối thiểu nếu cần).
- Test mới `zhvi/tests/test_discovery.py` — theo pattern fixture của `test_lattice.py` (mini dict qua tmp_path).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-NgheTruyen-2026-09-03/ARCHITECTURE-SPINE.md — AD-4, AD-8, AD-13, AD-18, Structural Seed, Fast-path Assumptions]
- [Source: thiet-ke-he-thong-dich-truyen-zh-vi.md#Bước-2-discovery-toàn-truyện (lines 159–173)]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/data-model.md — Phân quyền nguồn chân lý, Bảng SQLite]
- [Source: _bmad-output/specs/spec-zhvi-vietphrase-only/pipeline-contract.md — Config schema `[learning]`]
- [Source: zhvi/src/zhvi/state.py — `_SCHEMA`, `_migrate` v1→v3, `SCHEMA_VERSION = 3`]
- [Source: zhvi/src/zhvi/vietphrase/lattice.py — `vp_plan`, `best_paths`; zhvi/src/zhvi/vietphrase/trace.py — `VpDraft`, `VpSpan`, `SourceSpan`]
- [Source: zhvi/src/zhvi/project.py:138 — `project_lock`]

## Dev Agent Record

### Agent Model Used

GLM-5.3 (Claude Code session, Falcol).

### Debug Log References

- TDD: test_discovery.py viết RED trước từng task (schema fail → pass; run_discovery fail → pass).
- Lỗi giữa chừng đã sửa: `Node.content` là property không phải method; unknown intervals cần `_merge_adjacent` (chuỗi unknown liền kề phải gộp trước khi check n-gram nằm trọn); test-side: sqlite3 row mặc định tuple (dùng `cursor.description`), command CLI tên `import-` không phải `import`.

### Completion Notes List

- Signature `run_discovery(state, *, source_revision, dictionary, dictionary_revision_id)` — bỏ param `project` so với draft story vì `snapshot_path` có sẵn trong `SourceRevisionRow`; ít phụ thuộc hơn.
- `unknown_spans` và single-char edges đều qua `_merge_adjacent`; `is_unknown` dùng overlap ("chứa" theo spec bước 4), `is_single_char_run` dùng containment trên run entry một ký tự có entry.
- `alt_segmentation` là node-level signal (`SEGMENTATION_INSTABILITY` trong `vp_plan` warnings — chính là greedy vs lattice-best khác segmentation, một nhánh của OR spec) áp cho cả paragraph; không gọi `best_paths` riêng.
- Behavioral fix ngoài AC nhưng cần cho AC 1: `zhvi import-` upsert `source_revisions` ngay lúc import (trước đây chỉ translate flow ghi DB — discover đọc DB không thấy revision "đã import"). Đổi hành vi `import-`: giờ `inspect`/`discover` thấy revision ngay mà không cần translate.
- **Review fixes (2 trục, 10 findings — tất cả đã xử lý):** comments/docstring bỏ dấu theo chuẩn repo; `import-` upsert dưới `project_lock` (AD-13); guard "chưa import" chuyển trước `ensure_active_revision` + extract `_require_latest_source` dùng chung `inspect`/`discover`; `is_unknown` containment → overlap; test "không đụng engine" load fingerprint TRƯỚC discovery (hết tautological); extract `ensure_book_dictionary` (phase-3 chung translate/discover) + promote `resolve_dict_dir`/`resolve_global_glossary` public; `ObservationRow` dataclass thay `list[dict]` 19 khóa (typo lỗi lúc construct, không giữa transaction); `dd`/`gg` đổi tên `dict_dir_resolved`/biến mất qua helper.
- `[Note]` có sẵn không đụng: `loader.py:16` import `make_entry` unused (open item từ CONTEXT.md); `cli.py` còn lazy imports ở command cũ (`translate`, `dict diff`) — command mới `discover` import top-of-module theo rule; không refactor commands cũ (ngoài `status`/`inspect` dọn khi trực tiếp đụng).
- PMI pin: `PMI(xy) = log2(count(xy) * N / (count(x) * count(y)))`, `N` = tổng unigram CJK; `min_pmi` = min trên bigram liền kề trong n-gram.

### File List

- zhvi/src/zhvi/state.py (sửa: SCHEMA_VERSION 4, DDL observations + index, _OBS_COLS, ObservationRow, replace_observations, comment migrate v3→v4)
- zhvi/src/zhvi/learning/__init__.py (mới)
- zhvi/src/zhvi/learning/discovery.py (mới)
- zhvi/src/zhvi/pipeline.py (sửa: promote resolve_dict_dir/resolve_global_glossary public, extract ensure_book_dictionary — phase-3 dùng chung translate/discover)
- zhvi/src/zhvi/cli.py (sửa: command `discover`, import- upsert source_revisions dưới lock, _require_latest_source dùng chung, imports top, dọn lazy import trùng)
- zhvi/tests/test_discovery.py (mới)
- zhvi/tests/test_cli.py (sửa: test_discover_command_json)
- zhvi/tests/test_state.py (sửa: migrate test assert version 4)

## Change Log

- 2026-09-05: Story 3.1 implementation — bảng observations (schema v4), learning/discovery.py (n-gram 2–8, counts/chương, entropy, min_pmi, flags fragmentation/unknown/alt-seg/repetition, pattern seeds), CLI `zhvi discover`, fix `import-` ghi DB.
- 2026-09-05: Review fixes (2 trục, 10 findings) — AD-13 lock import-, is_unknown overlap, guard CLI sớm, ensure_book_dictionary extract, ObservationRow dataclass, test engine fingerprint trước discovery.
