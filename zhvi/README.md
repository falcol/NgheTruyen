# zhvi

CLI dịch truyện Trung → Việt theo thiết kế v2.0 (`../thiet-ke-he-thong-dich-truyen-zh-vi.md`).
Milestone 1: deterministic, VP-only, có state, resumable, reproducible.

## Cài đặt

```bash
# từ repo root, với .venv sẵn có
.venv/bin/pip install -e zhvi/
```

## Dùng nhanh

```bash
# Happy path 1 lệnh — tự tạo workspace <tên>.zhvi/ cạnh file input
zhvi translate truyen.txt -o truyen.vi.txt --dict-dir ../crawler/vietphrase/dicts

# Project workflow
zhvi init ./books/my-book --source ./crawl/my-book.txt   # (init tạo layout)
zhvi import ./crawl/my-book.txt -p ./books/my-book
zhvi inspect -p ./books/my-book
zhvi translate -p ./books/my-book -o ./books/my-book/dist/vi.txt
zhvi status -p ./books/my-book
zhvi export -p ./books/my-book -o out.txt

# Kiểm tra môi trường
zhvi doctor --dict-dir ../crawler/vietphrase/dicts
```

Chạy lại cùng file + cùng config = no-op (in lại output hiện có). Ctrl-C giữa
chừng giữ toàn bộ block đã commit; chạy lại tự resume.

## Từ điển

Mặc định đọc trực tiếp `crawler/vietphrase/dicts/` (không copy). Override bằng
`--dict-dir` hoặc `ZHVI_DICT_DIR`. Term khóa theo truyện: sửa
`glossary.manual.tsv` trong project rồi chạy lại — chỉ block liên quan đổi
dictionary fingerprint mới được dịch lại.

## Test

```bash
cd zhvi && ../.venv/bin/python -m pytest tests/ -q
```

## Trạng thái

- [x] M1: snapshot lossless, parser, lattice VietPhrase + trace, SQLite checkpoint,
      VP-only translate, atomic export, crash/resume.
- [ ] M2: Hachimi CTranslate2 worker, Ollama/Qwen, router 4 route, QA, review.
- [ ] M3: learning safe, entity ledger, revisions/rollback.
- [ ] M4: calibration, golden corpus, runtime benchmark.
