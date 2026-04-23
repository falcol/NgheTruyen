# Crawler

Crawl truyện từ các site về JSON tĩnh, phục vụ web đọc/nghe truyện cá nhân.

## Cài đặt

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Sites hỗ trợ

| Site | Tên | URL |
|------|-----|-----|
| `truyenqq` | TruyenQQ | `truyenqq.vn` |
| `metruyenchu` | Mê Truyện Chữ | `metruyenchu.com.vn` |
| `metruyencv` | Mê Truyện Chữ CV | `metruyencv.xyz` |

## Chạy

```bash
# Crawl tất cả chương (từ chương đầu)
python -m crawler.run <site> "URL_CHƯƠNG_ĐẦU"

# Crawl tối đa N chương (test nhanh)
python -m crawler.run <site> "URL" --max 5

# Bắt đầu từ chương thứ N (index bắt đầu từ 0)
python -m crawler.run <site> "URL_CHƯƠNG_N" --start N

# Cross-source append: crawl từ site A, ghi vào thư mục data của site B
python -m crawler.run <site_A> "URL" --start N --dest <site_B>
```

## Ví dụ

```bash
# Crawl truyện "Thất Nghiệp Về Sau" từ truyenqq
python -m crawler.run truyenqq \
  "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/12992985-0/"

# Resume từ chương 262
python -m crawler.run truyenqq \
  "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/13235752-262/" \
  --start 262

# Crawl từ metruyenchu
python -m crawler.run metruyenchu \
  "https://metruyenchu.com.vn/cao-vo-vo-han-phan-than-bat-dau-cho-an-be-bung-s-di-thu/chuong-1-abc123/"

# Cross-source: metruyenchu bị 404 ở chương 699, tiếp tục crawl từ metruyencv
# Ghi đè data vào cùng thư mục metruyenchu, bắt đầu từ chương 696 (index 695)
python -m crawler.run metruyencv \
  "https://metruyencv.xyz/truyen/cao-vo-vo-han-phan-than-bat-dau-cho-an-be-bung-s-di-thu/chuong-696-lao-bang-huu/" \
  --start 695 --dest metruyenchu
```

## Tính năng

- **Lưu incremental**: Mỗi 50 chương ghi 1 volume file, không cần đợi crawl hết
- **Crash safety**: Auto-save buffer khi crash/ interrupt
- **Resume**: Tự động tiếp tục từ chương cuối cùng qua `_progress.json`
- **Cross-source append**: `--dest` cho phép crawl từ site này, ghi vào data site khác
- **Dedup index**: Khi rebuild index, chương trùng index sẽ lấy bản mới nhất

## Output

```
data/<site>/<story-slug>/
├── metadata.json                # Tên truyện
├── chapters_index.json          # Danh sách tất cả chương (index + title)
├── vol-001-ch001-050.json       # Volume 1: chương 1-50
├── vol-002-ch051-100.json       # Volume 2: chương 51-100
└── ...
```

**Format mỗi volume:**

```json
{
  "volume": 1,
  "chapterRange": [1, 50],
  "chapters": [
    {
      "index": 0,
      "title": "Chương 01: Đêm mưa",
      "paragraphs": ["Đoạn văn 1", "Đoạn văn 2", "..."]
    }
  ]
}
```

`paragraphs` là array từng đoạn văn — tối ưu cho Web Speech TTS đọc từng đoạn không bị nghẽn.

## Thêm site mới

1. Tạo file mới (VD: `crawler/site_moi.py`)
2. Kế thừa `BaseCrawler`, implement `crawl()` + các method `_extract_chapter`, `_next_chapter_url`, `_extract_story_title`, `_extract_slug`
3. Constructor nhận `dest_dir: str | None = None`, truyền lên `super().__init__(site_name="...", dest_dir=dest_dir)`
4. Thêm vào `CRAWLERS` dict trong `run.py`
