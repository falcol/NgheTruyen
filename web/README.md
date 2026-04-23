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
```

## Import truyện đã crawl

Web app đọc dữ liệu trực tiếp từ thư mục `public/data/` — không cần database hay API.

### Cách hoạt động

- **Dev**: `public/data` là symlink → `../../crawler/data`
- **Build**: `prebuild` tự động copy `../crawler/data` → `public/data/`

### Cấu trúc data cần có

```
public/data/truyenqq/
└── <slug-truyen>/
    ├── metadata.json           # { "story_title": "Tên truyện" }
    ├── chapters_index.json     # [{ "index": 0, "title": "Chương 1" }, ...]
    ├── vol-001-ch001-050.json  # 50 chương/volume
    ├── vol-002-ch051-100.json
    └── ...
```

### Crawl truyện mới

```bash
# Từ thư mục crawler
cd ../crawler
python -m crawler.run truyenqq "https://truyenqq.com/..."
```

Sau khi crawl xong, data tự động xuất hiện ở web (qua symlink). Refresh browser để thấy truyện mới.

### Build production

```bash
npm run build   # prebuild tự chạy data:copy trước
```

### Lưu ý

- Data layer (`src/lib/data.ts`) tự động quét tất cả nguồn trong `public/data/` (truyenqq, metruyenchu, metruyencv, ...)
- Thêm thư mục nguồn mới vào `crawler/data/` → web tự nhận
