# vp

Dịch file truyện Trung → Việt theo tab File của vietphrase.app, và ghi hai danh sách Novel Scan để sửa tay rồi dùng lại.

Cần Python 3.10 trở lên. Lệnh `scan` còn cần Node.

Chạy từ thư mục gốc repo:

```bash
PYTHONPATH=vp/src python -m vp --help
```

Từ điển mặc định là `crawler/vietphrase/dicts`. Muốn đúng bộ trên site thì thêm `--dict manifest`.

## Dịch một file

```bash
PYTHONPATH=vp/src python -m vp file truyen.zh.txt -o truyen.vi.txt
```

Mặc định: chế độ `vietphrase`, luật nhân cấp 2, đổi phồn thể sang giản thể. File ra mặc định là `<tên>.vi.txt`.

| Cờ | Việc |
|---|---|
| `--mode hanviet` | Chỉ phiên âm Hán Việt |
| `--luat-nhan 0\|1\|2\|3` | Cấp luật nhân. Mặc định 2 |
| `--no-simplified` | Giữ phồn thể |
| `--custom file.txt` | Từ riêng `zh=vi`, ưu tiên 999 |
| `--overlay file.txt` | Tên và cụm của truyện, xem bên dưới |
| `--dict manifest` | Tải từ điển vietphrase.app vào `~/.cache/vp-dicts` |
| `--deep-scan` | Quét tên bằng NER trên GPU, gắn tên đã duyệt rồi dịch luôn. Ghi thêm `<tên>.ner.txt` |

`--deep-scan` chỉ chốt tên người lặp lại. Không ghi file cần xem / bỏ.

## Quét, sửa, rồi dịch

```bash
PYTHONPATH=vp/src python -m vp scan truyen.zh.txt
```

Với file `truyen.zh.txt`, lệnh ghi cạnh nó:

- `truyen.novel-review.txt` — cần xem
- `truyen.novel-reject.txt` — bỏ

Tên đã có sẵn trong `Names.txt` không vào hai file này. Lần quét sau ghi đè đúng hai file đó. File `*.novel-review.cleaned.txt` không bị đụng.

Mỗi dòng:

```text
# zh=vi	loại	số_lần	điểm	luật
逍遥神宗=Tiêu Dao Thần Tông	sect_org	54	0.9865
```

Sửa cột tiếng Việt. Giữ các cột sau nếu còn muốn `--overlay` nhận đúng loại. Xóa dòng nào không dùng.

Rồi dịch:

```bash
PYTHONPATH=vp/src python -m vp file truyen.zh.txt -o truyen.vi.txt \
  --overlay truyen.novel-review.txt
```

Ưu tiên khi đọc file quét:

| Loại | Ưu tiên |
|---|---|
| `character` | 30, như Book Names |
| `location`, `sect_org`, `title_alias`, `item`, `technique`, `other` | 25, như Book VietPhrase |

File overlay thường, không có cột loại:

- `zh=vi` — ưu tiên 30
- `zh=vi`, tab, rồi `phrase` — ưu tiên 25

Cụm dài hơn thắng cụm ngắn hơn. Cùng độ dài thì ưu tiên cao hơn thắng. `Custom.txt` và `--custom` vẫn ở 999.

`--refresh` tải lại script và model Novel Scan. Cache nằm ở `~/.cache/vp-dicts/novel-scan`.

## Test

```bash
PYTHONPATH=vp/src python -m pytest vp/tests -q
```
