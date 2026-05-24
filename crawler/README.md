# Crawler

Crawl truyện từ các site về JSON tĩnh, phục vụ web đọc/nghe truyện cá nhân.

## Cài đặt

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> `lxml` là optional — code tự fallback về `html.parser` nếu không có. Cài lxml để parse HTML nhanh 2-3x.

## Sites hỗ trợ

| Site | Tên | URL |
|------|-----|-----|
| `truyenqq` | TruyenQQ | `truyenqq.vn` |
| `metruyenchu` | Mê Truyện Chữ | `metruyenchu.com.vn` |
| `metruyencv` | Mê Truyện Chữ CV | `metruyencv.xyz` |
| `truyenfullmoi` | Truyện Full Mới | `truyenfullmoi.com` |
| `sitruyencv` | Si Truyện CV | `sitruyencv.com` (JSON API) |

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

# Crawl song song (parallel) — nhanh hơn 5-6x
python -m crawler.run <site> "URL" --parallel

# Parallel với số workers tùy chỉnh (default: 3)
python -m crawler.run <site> "URL" --parallel --workers 5

# Parallel + giới hạn số chương
python -m crawler.run <site> "URL" --parallel --max 100 --workers 3

# Aggressive mode — workers=8 + parallel_delay=(0.3, 0.7) → max speed
# (auto bật --parallel; risk gặp 429 cao hơn, adaptive multiplier sẽ tự throttle)
python -m crawler.run <site> "URL" --aggressive
```

Cuối mỗi lần crawl, log sẽ in tổng thời gian + throughput:
```
[run] Total time: 7m 24s  |  4200 chapters indexed  |  9.46 ch/s
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

# Parallel: crawl metruyencv 1000 chương trong ~8 phút (thay vì ~50 phút sequential)
python -m crawler.run metruyencv \
  "https://metruyencv.xyz/truyen/ta-moi-ngay-tuy-co-mot-cai-tan-he-thong/chuong-1/" \
  --parallel --workers 3

# Benchmark thực tế: metruyenchu 4200 chương
#   --parallel (workers=3, default delay):  ~40 phút (1.75 ch/s)
#   --aggressive (workers=8, fast delay):   ~7 phút  (~9-10 ch/s) — nếu không gặp 429

# Parallel: crawl metruyenchu — tự fetch danh sách chương qua API, rồi parallel fetch
python -m crawler.run metruyenchu \
  "https://metruyenchu.com.vn/ta-moi-ngay-tuy-co-mot-cai-tan-he-thong/chuong-1-abc123/" \
  --parallel --workers 3 --max 100

# Crawl từ truyenfullmoi (URL prediction — hỗ trợ parallel)
python -m crawler.run truyenfullmoi \
  "https://truyenfullmoi.com/ho-hoa-cao-thu-tai-do-thi/chuong-1.html" \
  --parallel --workers 5

# Crawl từ sitruyencv (JSON API — React SPA, parallel mặc định)
python -m crawler.run sitruyencv \
  "https://sitruyencv.com/read/16277/1" \
  --parallel --workers 3

# Crawl toàn bộ (aggressive)
python -m crawler.run sitruyencv \
  "https://sitruyencv.com/read/16277/1" \
  --aggressive

# Hoặc dùng URL story (tự extract story ID + slug)
python -m crawler.run sitruyencv \
  "https://sitruyencv.com/story/16277-da-tu-da-phuc-con-ta-deu-co-tien-de-chi-tu-convert" \
  --parallel --max 50
```

## Tính năng

### Core
- **Lưu incremental**: Mỗi 50 chương ghi 1 volume file, không cần đợi crawl hết
- **Crash safety**: Auto-save buffer khi crash/ interrupt
- **Resume sequential**: Tiếp tục từ chương cuối qua `_progress.json`
- **Resume parallel** (mới): Tự động skip các index đã có trong vol files khi chạy lại
- **Cross-source append**: `--dest` cho phép crawl từ site này, ghi vào data site khác
- **Dedup index**: Khi rebuild index, chương trùng index sẽ lấy bản mới nhất
- **Parallel crawl** (`--parallel`): Fetch song song với ThreadPoolExecutor, nhanh 5-6x
  - metruyencv: URL prediction thuần — 0 overhead, generate URLs từ pattern
  - metruyenchu: API discovery — fetch danh sách chương qua `/get/listchap/{id}`, rồi parallel fetch
  - truyenqq: Fallback sequential với delay giảm (1.5s thay vì 3s)
  - truyenfullmoi: URL prediction — `/{slug}/chuong-{N}.html`, detect end-of-story qua homepage redirect
  - sitruyencv: JSON API — override `_request()` parse JSON, dùng `versionId` + chapter number prediction
- **Early stop** (mới): Parallel mode tự dừng khi cả chunk trả 404 (qua đoạn cuối truyện)
- **Aggressive preset** (`--aggressive`): Workers=8 + parallel_delay=(0.3, 0.7) → tốc độ tối đa, auto bật `--parallel`. Adaptive multiplier sẽ tự throttle nếu server push back.
- **Time counter**: Cuối mỗi crawl in tổng thời gian + throughput (`5m 12s | 200 chapters indexed | 0.64 ch/s`)

### Performance
- **lxml parser**: Tự fallback `html.parser` nếu chưa cài lxml (2-3x chậm hơn)
- **HTTP connection pool**: `pool_maxsize=20` cho cả main và per-thread session
- **Per-thread rate limit**: Mỗi worker có timestamp riêng, không serialize qua lock chung
- **Strict-gap delay**: Chỉ sleep phần thời gian còn thiếu để đạt gap (không sleep dư)

### Anti-block (phòng ngừa bị limit/chặn)
- **User-Agent rotation**: Pool 7 UA Chrome/Firefox/Safari/Edge, random mỗi request
- **Random Accept-Language**: 4 biến thể vi-VN dominant
- **Referer chain**: Sequential set referer = chương trước; parallel set = BASE_URL → trông như user click "Sau"
- **Cookie warm-up**: Visit homepage 1 lần đầu mỗi crawl để có session cookie hợp lệ
- **Honor `Retry-After`**: Đọc header (cả seconds + HTTP-date), sleep đúng thời gian server yêu cầu
- **429/503/403 detection**: Long backoff riêng (5×2^attempt, max 60s) thay vì retry ngay
- **Adaptive delay (AIMD-inverse)**:
  - Gặp rate-limit → multiplier × 1.5 (cap 5×) → delay base × multiplier
  - 10 success liên tiếp → multiplier × 0.9 → tự phục hồi
  - Log `Rate-limited — adaptive multiplier 1.00x -> 1.50x` khi trigger
  - Log `Adaptive recover: 1.50x -> 1.35x` khi phục hồi
- **Tor proxy** (sitruyencv): Tự động phát hiện Tor SOCKS5 proxy, route requests qua Tor.
  Khi bị 429 → gửi SIGHUP đến container → IP mới → retry. Xem phần Tor bên dưới.

### Tweak anti-block

Sửa trực tiếp trong `crawler/base.py`:
- `USER_AGENT_POOL` (top file) — thêm/bớt UA
- `ACCEPT_LANGUAGE_POOL` (top file) — thêm region
- `BaseCrawler.__init__`: `delay=(2.0, 4.0)`, `parallel_delay=(1.0, 2.0)`
- `_on_success` / `_on_rate_limited`: hằng số 0.9, 1.5, 5.0, window 10

### Compression (Vercel-friendly)

Mặc định `COMPRESS=True` → ghi `vol-*.json.gz` đã minify, **giảm ~77%** size (550K → 130K mỗi vol).

```bash
# Compress data đã có sẵn (default dry-run)
python -m crawler.compress              # Xem trước
python -m crawler.compress --apply      # Compress + xoá .json gốc
python -m crawler.compress --apply --keep-json  # Giữ .json gốc

# Tắt compression cho 1 lần crawl (debug):
# Sửa COMPRESS=False trong base.py rồi crawl
```

Reader auto-detect cả `.json` và `.json.gz` → an toàn flip qua lại, không cần migrate ngay.

**Đọc `.json.gz` từ web app:**

Cách 1 (recommended — qua Vercel headers): set `Content-Encoding: gzip` trong `vercel.json` → browser auto-decompress, frontend `fetch().json()` chạy bình thường. Xem `web/vercel.json` đã setup sẵn.

Cách 2 (manual decompress phía client): nếu không deploy Vercel hoặc muốn control:
```js
const resp = await fetch('.../vol-001-ch001-050.json.gz');
const stream = resp.body.pipeThrough(new DecompressionStream('gzip'));
const vol = await new Response(stream).json();
```

**Server-side đọc** (Next.js SSG): dùng `zlib.gunzipSync` — `web/src/lib/data.ts` đã handle.

> `.json.gz` giảm **deploy size** (repo + Vercel upload) ~77%. Bandwidth phía user khi serve thì Vercel cũng tự gzip text rồi, nên tiết kiệm chính ở deploy.

## Output

Mặc định (`COMPRESS=True`) — gzip + minify:

```
data/<site>/<story-slug>/
├── metadata.json.gz              # Tên truyện
├── chapters_index.json.gz        # Danh sách tất cả chương (index + title)
├── vol-001-ch001-050.json.gz     # Volume 1: chương 1-50
├── vol-002-ch051-100.json.gz     # Volume 2: chương 51-100
├── _progress.json                # (plain JSON, dùng để resume — không gzip)
└── ...
```

> Khi `COMPRESS=False`, output là `.json` thuần (indent=2, dễ đọc khi debug).
> Reader auto-detect cả 2 → có thể trộn lẫn `.json` và `.json.gz` trong cùng story dir.

**Format mỗi volume** (sau khi decompress):

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
2. Kế thừa `BaseCrawler`, implement 4 abstract methods: `_extract_chapter`, `_next_chapter_url`, `_extract_story_title`, `_extract_slug`
3. Set `BASE_URL` làm class attribute → dùng cho cookie warm-up + Referer mặc định:
   ```python
   class SiteMoiCrawler(BaseCrawler):
       BASE_URL = "https://site-moi.com/"
       def __init__(self, dest_dir=None):
           super().__init__(site_name="site_moi", dest_dir=dest_dir)
   ```
4. (Optional) Override `_predict_urls` nếu site có URL pattern dự đoán được hoặc API list chương → enable parallel mode
5. Thêm vào `CRAWLERS` dict trong `run.py`

**Tip**: Nếu site có rate-limit gắt, có thể tăng `delay` mặc định trong `__init__`:
```python
super().__init__(site_name="...", dest_dir=dest_dir, delay=(3.0, 6.0))
```

## Tor Proxy (sitruyencv)

`sitruyencv.com` rate-limit ~30 req/IP/min. Khi crawl nhiều chương liên tục (600+), dù workers=1 vẫn bị 429. Tor giúp xoay IP để vượt rate limit.

### Cách hoạt động

```
Crawler → Tor SOCKS5 (localhost:9050) → API (thấy IP của Tor exit node)
Gặp 429 → docker kill --signal=SIGHUP tor → Tor tạo circuit mới → IP mới → retry
```

- **Auto-detect**: Crawler tự phát hiện Tor trên port 9050. Nếu không có Tor → fallback về kết nối trực tiếp.
- **Chỉ ảnh hưởng sitruyencv**: Các crawler khác (truyenqq, metruyencv...) không dùng Tor.
- **Tự động đổi IP khi 429**: Không cần can thiệp thủ công.

### Bật Tor

```bash
# 1. Chạy Tor trong Docker (không cần sudo)
docker run -d --name tor \
  -p 9050:9150 \
  --restart unless-stopped \
  peterdavehello/tor-socks-proxy

# 2. Đợi Tor bootstrap (~5 giây)
sleep 5

# 3. Kiểm tra Tor đang chạy — trả về IP khác IP thật
curl -s --socks5-hostname localhost:9050 https://httpbin.org/ip

# 4. Crawl bình thường — Tor tự được sử dụng
python -m crawler.run sitruyencv "https://sitruyencv.com/read/16277/1" \
  --parallel --workers 3
```

> **Lưu ý port**: Image `peterdavehello/tor-socks-proxy` listen port 9150 bên trong, nên map `-p 9050:9150`.

### Tắt Tor

```bash
# Dừng container (giữ data)
docker stop tor

# Hoặc xoá hoàn toàn
docker rm -f tor
```

Khi Tor tắt, crawler tự động fallback về kết nối trực tiếp (như bình thường, không qua proxy).

### Kiểm tra trạng thái

```bash
# Xem IP hiện tại qua Tor
curl -s --socks5-hostname localhost:9050 https://httpbin.org/ip

# Xem IP thật (không qua Tor)
curl -s https://httpbin.org/ip

# Đổi IP thủ công (nếu muốn)
docker kill --signal=SIGHUP tor && sleep 3 && curl -s --socks5-hostname localhost:9050 https://httpbin.org/ip
```

### Performance với Tor

| Mode | Throughput | Ghi chú |
|------|-----------|---------|
| `--workers 1` qua Tor | ~0.6 ch/s | Không bao giờ 429 |
| `--workers 3` qua Tor | ~1.7 ch/s | 0 bị 429 trong test 20 chapters |
| `--workers 3` không Tor | ~1.7 ch/s → 429 sau ~600 ch | Bị block khi crawl sustained |

### Cài đặt dependency

```bash
# PySocks cần thiết cho SOCKS5 proxy support
pip install PySocks
```

`PySocks` đã có trong `requirements.txt`.
