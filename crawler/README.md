# Crawler

Crawl truyện từ các site về JSON tĩnh, phục vụ web đọc/nghe truyện cá nhân.

## Cài đặt

```bash
pip3 install -r requirements.txt --break-system-packages
```

## Chạy

```bash
# Crawl tất cả chương (từ chương đầu)
python3 -m crawler.run truyenqq "URL_CHƯƠNG_ĐẦU"

# Crawl tối đa N chương (test nhanh)
python3 -m crawler.run truyenqq "URL" --max 5

# Bắt đầu từ chương thứ N
python3 -m crawler.run truyenqq "URL_CHƯƠNG_N" --start N
```

## Ví dụ

```bash
# Crawl truyện "Thất Nghiệp Về Sau" từ đầu
python3 -m crawler.run truyenqq \
  "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/12992985-0/"

# Resume từ chương 262
python3 -m crawler.run truyenqq \
  "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/13235752-262/" \
  --start 262
```

## Output

```
data/<site>/<story-slug>/
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
2. Kế thừa `BaseCrawler`, implement `crawl()`
3. Thêm vào `CRAWLERS` dict trong `run.py`
