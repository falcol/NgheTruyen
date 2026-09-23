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

## Đổ Mạnh nhất lên reader, từ chương 1012

Chạy từ thư mục gốc repo. `vp` cần Python 3.10.

File:

- Trung: `zhvi/workspace/manh-nhat-from-1012.zh.txt`
- Glossary, điểm trên 0.5: `zhvi/workspace/manh-nhat-from-1012.novel-review.gt05.txt`
- Việt: `zhvi/workspace/manh-nhat-from-1012.zh.vi.gt05.txt`

Dịch:

```bash
PYTHONPATH=vp/src python -m vp file \
  zhvi/workspace/manh-nhat-from-1012.zh.txt \
  -o zhvi/workspace/manh-nhat-from-1012.zh.vi.gt05.txt \
  --overlay zhvi/workspace/manh-nhat-from-1012.novel-review.gt05.txt
```

Hai bản phải cùng số dòng. Rồi đổ lên JSON reader. Script `crawler/overlay_manh_nhat_1012.py` mặc định đọc `manh-nhat-from-1012.zh.vi.txt`. Không sửa dòng `VI` trong script. Gán đường dẫn rồi chạy:

```bash
python3 -c 'import crawler.overlay_manh_nhat_1012 as o; o.VI = o.ROOT / "zhvi/workspace/manh-nhat-from-1012.zh.vi.gt05.txt"; raise SystemExit(o.main())'
```

Script làm các việc này:

- Khớp chương theo số in trên tiêu đề Hán và tiêu đề «Chương N», không theo index trong JSON.
- Chỉ ghi từ chương 1012. Chương 1–1011 giữ nguyên.
- Bỏ chương có số in bị trùng, chương không có đoạn, và chương lệch số đoạn. Những chương lệch giữ nguyên chữ cũ. Lần đổ gt05 bỏ 1174, 1473, 1477, 1575, 1637, 1661, 1663, 1664, 2311.
- Ghi `crawler/data/xtruyen/manh-nhat-tu-tien-hoc-sinh-tieu-hoc/vol-*.json.gz`, rồi copy các volume vừa đổi sang `web/public/data/xtruyen/manh-nhat-tu-tien-hoc-sinh-tieu-hoc/`.
- Trên reader đang mở, bấm Ctrl+Shift+R.

## Test

```bash
PYTHONPATH=vp/src python -m pytest vp/tests -q
```
