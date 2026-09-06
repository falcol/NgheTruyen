# zhvi

CLI dịch truyện **Trung → Việt** — **VietPhrase-only, offline, deterministic** theo thiết kế 3.0 (`_bmad-output/specs/spec-zhvi-vietphrase-only/`).

Không còn model dịch/AI post-edit: một đường sinh văn bản duy nhất là engine VietPhrase. Chất lượng đi lên qua vòng lặp kiểm chứng được: đo chỗ từ điển yếu → tạo entry/rule xác định → regression → revision mới → dịch lại.

- Snapshot nguồn **lossless** (dựng lại được 100% văn bản gốc).
- Parser document giữ nguyên cấu trúc (paragraph, quote, ellipse…).
- **VietPhrase lattice + trace** — render deterministic theo AD-9 (longest-match → layer precedence → literal-over-pattern → tie-break `entry_id`).
- **SQLite checkpoint** cho từng block — Ctrl-C giữa chừng tự resume.
- **Atomic export** (ghi temp → rename, kèm `sha256`); cùng fingerprint → cùng output SHA-256.
- Đọc trực tiếp `crawler/vietphrase/dicts/` (không copy), hash fingerprint cho từng run.
- Run mới chỉ ghi route `VIETPHRASE`; lịch sử model-era (thiết kế 2.0) giữ read-only, cache cũ bị invalidate.

---

## Luồng hoạt động

Hai pha độc lập (AD-4): **LEARN** được quyền đề xuất/tạo dictionary revision; **TRANSLATE** chỉ đọc snapshot + revision đã freeze.

```mermaid
flowchart TD
    src[TXT nguồn .txt] --> snap
    snap[Snapshot lossless] --> learn
    learn[Discover → candidate → book-auto] --> freeze
    freeze[Freeze dictionary revision] --> vp
    vp[VietPhrase translate từng block] --> qa
    qa{QA structural}
    qa -->|fail| fix[needs_dictionary_fix — không export]
    qa -->|pass| export[Atomic export + manifest]
    export --> out[out.txt + SHA-256]
```

Happy path 1 lệnh: `zhvi translate FILE -o OUT` chạy `snapshot → discover → book-auto learn → freeze → translate → QA → export → report`.

`--no-learn` bỏ pha LEARN, dịch bằng revision active hiện tại.

---

## Cài đặt

```bash
# Từ repo root, với .venv sẵn có
.venv/bin/pip install -e zhvi/
```

Sau khi cài đặt, binary `zhvi` nằm trong `.venv/bin/`. Chạy từ **repo root** để đường dẫn mặc định `crawler/vietphrase/dicts` và `~/.config/zhvi/glossary.manual.tsv` resolve đúng.

> **Cần từ điển?** `zhvi doctor` sẽ báo thiếu. Đường dẫn mặc định:
> `crawler/vietphrase/dicts/` (đã có sẵn trong repo, không cần copy).

---

## Nhanh chóng (Happy path)

### 1 lệnh, tự tạo workspace cạnh file

```bash
# truyen.txt → truyen.zhvi/ (workspace auto) → truyen.vi.txt
zhvi translate truyen.txt -o truyen.vi.txt
```

Nếu muốn chỉ rõ thư mục từ điển:

```bash
zhvi translate truyen.txt -o truyen.vi.txt --dict-dir ../crawler/vietphrase/dicts
```

> Chạy lại cùng file + cùng config = **no-op** (in lại output hiện có). Ctrl-C giữa
> chừng giữ toàn bộ block đã commit; chạy lại tự **resume**.

---

## Các lệnh

### `zhvi init <project>`
Tạo project mới cho một truyện (layout `.zhvi/`, `zhvi.toml`, `glossary.manual.tsv`). Idempotent — project đã tồn tại không bị ghi đè.

```bash
zhvi init ./books/my-book
```

### `zhvi import <file> --project|-p <project>`
**Snapshot an toàn** file TXT nguồn vào project (freeze bản gốc, sinh `revision id`).

| Option | Mặc định | Ý nghĩa |
|---|---|---|
| `--project`, `-p` | — | Project đích (nếu thiếu, tự workspace `<file>.zhvi/`) |
| `--encoding` | `utf-8` | Mã hoá file nguồn |
| `--update` | off | Nhận file này làm source mới của project |

```bash
zhvi import ./crawl/chap1.txt -p ./books/my-book
```

### `zhvi inspect [--project|-p <project>] [--source <file>]`
Báo cáo cấu trúc document (số block, loại block, mất mát…).

```bash
zhvi inspect -p ./books/my-book
zhvi inspect --source ./crawl/chap1.txt --sample 50
```

### `zhvi translate [<file>] [options]`
Happy path: snapshot → discover → book-auto learn → freeze revision → VP → QA → atomic export. File trực tiếp **hoặc** `--project`.

| Option | Mặc định | Ý nghĩa |
|---|---|---|
| `-o`, `--output` | — | File đích (TXT đã dịch) |
| `--project`, `-p` | — | Project (có sẵn source) |
| `--style` | `convert-qt` | Style dịch |
| `--encoding` | `utf-8` | Mã hoá nguồn |
| `--dict-dir` | `crawler/vietphrase/dicts` | Thư mục từ điển |
| `--no-learn` | off | Bỏ LEARN; dịch bằng revision active hiện tại |
| `--refresh-revision` | off | Correction: glossary đổi → revision mới + dịch lại affected blocks |
| `--json` | off | In báo cáo JSON ra stdout (máy đọc được) |

```bash
# 1 lệnh happy path (có LEARN)
zhvi translate truyen.txt -o truyen.vi.txt
# chỉ dịch, không học
zhvi translate truyen.txt -o truyen.vi.txt --no-learn
# project da import: dung snapshot, khong LEARN
zhvi translate -p ./books/my-book -o ./books/my-book/dist/vi.txt --no-learn
# FILE + project + JSON
zhvi translate truyen.txt -p ./books/my-book -o ./books/my-book/dist/vi.txt --json
```

Manifest mỗi run (`.zhvi/runs/<run_id>/manifest.json`) chứa `run_id`, `dictionary_revision`, `output.sha256`.

### `zhvi status --project|-p <project>`
Tiến độ run, route, cache, lỗi, review dưới dạng JSON.

```bash
zhvi status -p ./books/my-book
# thoát code 7 nếu run chưa exported
zhvi status -p ./books/my-book --require-complete
```

### `zhvi export --project|-p <project> [-o <output>]`
Dựng lại TXT từ một run **đã COMMITTED đầy đủ**.

| Option | Mặc định | Ý nghĩa |
|---|---|---|
| `-o`, `--output` | — | File đích |
| `--run` | run hoàn tất gần nhất | Run ID cụ thể |
| `--replace` | off | Cho phép ghi đè output đã tồn tại |

```bash
zhvi export -p ./books/my-book -o ./books/my-book/dist/vi.txt
```

### `zhvi doctor [--project|-p <project>] [--dict-dir <dir>]`
Kiểm tra từ điển, SQLite/disk, smoke-test convert. Thoát code 4 nếu có vấn đề.

```bash
zhvi doctor --dict-dir ../crawler/vietphrase/dicts
```

### `zhvi learn --project|-p <project> [--global] [--manifest PATH]`
LEARN tường minh: discovery → candidate → evidence → book-auto promotion. `--global` đánh giá global promotion (fail-closed — xem AD-14 bên dưới).

### `zhvi terms list|accept|reject|revoke --project|-p <project>`
Vòng đời candidate/auto entry của truyện. `accept` ghi manual glossary rồi publish revision mới; `revoke` thu hồi book-auto.

### `zhvi dict diff <REV_A> <REV_B> --project|-p <project>`
### `zhvi dict rollback <REV> --project|-p <project>`
Diff entry + affected blocks; rollback CAS về revision an toàn (revision mới, không sửa bundle cũ).

### `zhvi explain <TEXT> --project|-p <project>`
Segmentation + provenance từng span (entry, layer, revision) và affected blocks nếu đổi entry.

### `zhvi review --project|-p <project> [--list | --output <jsonl>]`
Liệt kê / xuất các block cần người xem (invariant fail — block giữ draft VP + NEEDS_REVIEW).

```bash
zhvi review -p ./books/my-book --list          # đếm + tóm tắt JSON
zhvi review -p ./books/my-book -o review.jsonl # xuất JSONL từng block
```

Không còn cờ `--hachimi`, `--qwen`, hay profile `fast|balanced|quality`.

---

## Cách dùng project (workflow đầy đủ)

```bash
# 1. Tạo vùng làm việc cho truyện
zhvi init ./books/my-book

# 2. Snapshot nguồn
zhvi import ./crawl/my-book.txt -p ./books/my-book

# 3. Xem cấu trúc (tuỳ chọn)
zhvi inspect -p ./books/my-book

# 4. Dich (snapshot da import; --no-learn neu chi muon dich)
zhvi translate -p ./books/my-book -o ./books/my-book/dist/vi.txt
zhvi translate -p ./books/my-book -o ./books/my-book/dist/vi.txt --no-learn

# 5. Kiểm tra tiến độ
zhvi status -p ./books/my-book

# 6. Export lại từ run committed (tuỳ chọn)
zhvi export -p ./books/my-book -o ./books/my-book/dist/vi.txt
```

---

## Cấu trúc project

```
books/my-book/
├── zhvi.toml                  # config project (style, pipeline, glossary...)
├── glossary.manual.tsv        # term khoá riêng cho truyện (book manual)
├── dist/                      # output đã dịch
└── .zhvi/                     # state (gitignore)
    ├── state.sqlite3          # DB: revision, run, block, route, review
    ├── sources/               # snapshot lossless nguồn (mỗi revision)
    ├── dictionaries/          # fingerprint từ điển
    ├── runs/                  # kết quả run
    ├── logs/
    ├── cache/                 # dict-<fingerprint>.pkl
    └── locks/                 # khoá chống ghi trùng (flock)
```

---

## Từ điển & Glossary

Đọc trực tiếp `crawler/vietphrase/dicts/` (không copy). Override bằng `--dict-dir` hoặc env `ZHVI_DICT_DIR`.

**Thứ tự load** (từ điển cơ sở, tăng dần độ ưu tiên):

```
ChinesePhienAmWords.txt
VietPhrase_1.txt
VietPhrase_2.txt
VietPhrase_3.txt
LuatNhan.txt
Names.txt
QualityOverrides.txt
Custom.txt           # thư viện term chuẩn, dùng chung mọi truyện
```

**Glossary (term khoá) — 3 tầng, ưu tiên tăng dần:**

| Tầng | Đường dẫn | Phạm vi |
|---|---|---|
| Cơ sở dict | `crawler/vietphrase/dicts/*.txt` | Toàn hệ thống |
| Global | `~/.config/zhvi/glossary.manual.tsv` | Mọi project trên máy |
| Book | `<project>/glossary.manual.tsv` | Riêng từng truyện |

Định dạng glossary: `zh=Từ gốc<TAB>vi=Từ dịch`, mỗi dòng một mục.

- **Book manual** override **global**, global override **dict cơ sở**.
- Term chuẩn xuyên truyện (vd `小胖 → Tiểu Bàn`) nên đưa vào `Custom.txt` hoặc
  `~/.config/zhvi/glossary.manual.tsv`, tránh lặp lại trong từng book.
- Đổi glossary / dict → fingerprint đổi → chỉ block liên quan được dịch lại.

> Env bổ trợ: `ZHVI_DICT_DIR`, `ZHVI_GLOBAL_GLOSSARY`.

---

## Kiến trúc VietPhrase-only (3.0)

Một đường dịch duy nhất — không model runtime, không network call:

```
LEARN:  snapshot → discover n-gram → candidate/evidence → book-auto (hard gates)
        → publish immutable dictionary revision
TRANSLATE: pin revision → vp_plan từng block → QA structural (không sửa text)
        → atomic export + manifest (run_id, revision_id, SHA-256)
```

- **Route duy nhất**: `VIETPHRASE` — mọi block đi qua VietPhrase; block fail
  invariant được giữ nguyên draft và đưa vào `zhvi review` (không fallback ngầm).
- **Deterministic (AD-9)**: longest-match → layer precedence → literal-over-pattern
  → tie-break `entry_id` — không phụ thuộc thứ tự nap từ điển.
- **QA gates** (`quality/`): fail → `needs_dictionary_fix`, không export, không hidden repair.
- Migration từ thiết kế 2.0 mang tính cộng thêm: lịch sử run/block/route model-era
  giữ read-only; mọi block cache model-era bị đánh dấu invalid, không tái dùng.

### Vòng correction (entry → revision → rerun)

CLI không sửa text đích. Muốn đổi cụm:

1. Sửa/thêm entry: `glossary.manual.tsv` hoặc `zhvi terms accept SOURCE`
2. Hệ thống build revision mới (`zhvi translate --refresh-revision`, hoặc accept/revoke tự publish)
3. Affected blocks (trace/source index) được dịch lại; block không đụng được adopt
4. QA → export atomic lại

Không lưu "bản text đã sửa" làm nguồn chân lý thứ hai (AD-2).

### Global auto-promotion đang khóa (AD-14)

`zhvi learn --global` **fail-closed**: thiếu golden manifest `approved`, cross-book evidence, target agreement hoặc affected-block isolation thì candidate không vượt `global_candidate`. File `raw_china/expect*` / `excpect*` không tự thành golden — chỉ là candidate reference cho `zhvi golden import`.

---

## Config (`zhvi.toml`)

`zhvi init` sinh sẵn một template với comment giải thích. Schema 3.0 — các cờ chính:

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `style` | `convert-qt` | Style dịch |
| `output_policy` | `strict-final` | Chính sách output |
| `collapse_repetitions` | `true` | Loại bỏ lặp artifact (`có chút có chút`) giữa 2 span khác nhau; giữ reduplication gốc (慢慢 → chậm chậm) |
| `qa_strip_junk` | `true` | Strip rác truyện web (watermark ⓣⓣⓚ, bookmark, anti-leech) trên source **trước** khi dịch |
| `pattern_rules` | `true` | Bật luật nhân `{s}` (số) / `{n}` (danh từ) trong `LuatNhan.txt` — match regex + điền capture |
| `global_glossary` | `~/.config/...` | Đường dẫn glossary toàn cục |

Section `[learning]` (ngưỡng learner — epic 3/4 dùng) và `[runtime]`
(`checkpoint_blocks`) cũng nằm trong template.

**Precedence (từ cao → thấp):** CLI flag → env → `zhvi.toml` → mặc định.

---

## Exit codes

| Code | Ý nghĩa |
|---|---|
| `0` | OK |
| `2` | Usage (thiếu/ sai tham số) |
| `3` | Input / snapshot lỗi |
| `4` | Preflight fail (doctor, từ điển thiếu) |
| `5` | State (project không có source, lock conflict) |
| `6` | Run failed |
| `7` | Review / chưa exported |
| `8` | Export (ghi file lỗi, PermissionError…) |
| `9` | Integrity (sha256 không khớp) |
| `130` | KeyboardInterrupt |

---

## Test

```bash
cd zhvi && ../.venv/bin/python -m pytest tests/ -q
```

---

## Trạng thái (thiết kế 3.0)

- [x] **Epic 1 — VietPhrase-only cutover**: gỡ engine model/router/post-edit,
      config schema 3.0, migration additive, đường dịch deterministic AD-9.
- [x] **Epic 2**: immutable dictionary revisions (bundle, publish, pin, projection,
      diff/rollback, versioned preprocess).
- [x] **Epic 3**: book learner (discovery, candidate, evidence, book-auto, terms CLI).
- [x] **Epic 4**: global registry + ingest; global auto-promotion **fail-closed (AD-14)**
      cho tới khi có golden manifest approved.
- [x] **Epic 5**: QA structural gates, golden tooling, metamorphic tests, CLI E2E.
