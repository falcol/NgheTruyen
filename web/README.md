# NgheTruyen Web

Web app đọc truyện tiếng Việt với TTS (text-to-speech).

## Commands

```bash
npm run dev          # Dev server (http://localhost:3000)
npm run build        # Production build (auto copy data trước)
npm run start        # Chạy production server
npm run test         # Run tests
npm run test:watch   # Tests ở watch mode
npm run lint         # ESLint
npm run data:copy    # Copy data từ crawler vào web
npm run epub:cache   # Parse EPUB → cache metadata (epub/.cache/)
```

## Import truyện đã crawl

Web app đọc dữ liệu trực tiếp từ thư mục `public/data/` — không cần database hay API.

### Cách hoạt động

- **Dev**: `public/data` là symlink → `../../crawler/data`
- **Build**: `prebuild` tự động copy `../crawler/data` → `public/data/`

### Cấu trúc data cần có

Mặc định crawler ghi `.json.gz` (gzip + minify, giảm ~77% size). Reader hỗ trợ cả 2 định dạng:

```
public/data/truyenqq/
└── <slug-truyen>/
    ├── metadata.json.gz          # { "story_title": "Tên truyện" }
    ├── chapters_index.json.gz    # [{ "index": 0, "title": "Chương 1" }, ...]
    ├── vol-001-ch001-050.json.gz # 50 chương/volume
    ├── vol-002-ch051-100.json.gz
    └── ...
```

> Có thể trộn `.json` và `.json.gz` trong cùng thư mục — `data.ts` ưu tiên `.json.gz` nếu cả 2 cùng tồn tại.

### Crawl truyện mới

```bash
# Từ thư mục crawler
cd ../crawler
python -m crawler.run truyenqq "https://truyenqq.com/..."

# Compress data đã có sẵn (one-time migration)
python -m crawler.compress --apply
```

Sau khi crawl xong, data tự động xuất hiện ở web (qua symlink). Refresh browser để thấy truyện mới.

### Build production

```bash
npm run build   # prebuild tự chạy data:copy trước
```

`data.ts` dùng `zlib.gunzipSync` để decompress `.json.gz` ở build time (Node side). SSG output chỉ là HTML thuần — browser không phải fetch JSON khi đọc trang đã pre-render.

### Vercel deploy

`vercel.json` đã cấu hình:
- `/data/*.json.gz` serve với header `Content-Encoding: gzip` → browser auto-decompress nếu có client-side fetch
- Cache `max-age=31536000, immutable` → CDN cache 1 năm (chương đã crawl không đổi)

### EPUB

- Trang `/epub` đọc metadata từ `epub/.cache/` (nhanh, không mở file .epub).
- Sau khi thêm/sửa file `.epub`, chạy `npm run epub:cache` (hoặc `npm run build` — prebuild tự warm).
- Lần đầu mở một cuốn (chưa cache) vẫn parse EPUB một lần rồi ghi cache.

### Lưu ý

- Data layer (`src/lib/data.ts`) tự động quét tất cả nguồn trong `public/data/` (truyenqq, metruyenchu, metruyencv, ...)
- Thêm thư mục nguồn mới vào `crawler/data/` → web tự nhận
- Reader API nhất quán bất kể file là `.json` hay `.json.gz` (transparent qua `readJsonAny`)
