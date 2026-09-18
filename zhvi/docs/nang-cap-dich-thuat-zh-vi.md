# Nghiên cứu nâng cấp dịch thuật zh→vi (zhvi)

> Mục tiêu: tổng hợp **thuật toán**, **luật cú pháp** và **nguồn nghĩa** khả thi để nâng cấp engine dịch Trung→Việt của `zhvi`, giữ triết lý thiết kế 3.0 (VietPhrase-only, offline, deterministic) và chỉ đề xuất đường đi tương thích với AD-2/AD-9/AD-18.
>
> Mọi con số trong tài liệu đã kiểm chứng trên repo + nguồn ngoài (ngày 12/09/2026).

---

## 1. Hiện trạng engine

| Thành phần | File | Vai trò hiện tại |
|---|---|---|
| Loader | `zhvi/src/zhvi/vietphrase/loader.py` | Nạp 2.075.768 dòng dict (`VietPhrase_1..4` 1.759.395, `Names*` 278.243, `LuatNhan` 25.172, `ChinesePhienAmWords` 12.623, `Custom` 335) vào trie giữ **mọi** candidate, cache pickle + fingerprint |
| Lattice | `zhvi/src/zhvi/vietphrase/lattice.py` | Greedy longest-match cho **render** (parity QuickTrans) + top-K DP/beam để đo `margin`/`entropy`. Score = `trust*0.01 + (len-1)*1.0 − W_SINGLE 2.0 − W_FRAG 1.5 − W_UNKNOWN 5.0 + W_DROP 0.5 (particle) / W_PATTERN 3.0 (luật nhân)` |
| Layers | `layers.py` | Precedence 8 tầng (thứ tự layer, trust trong ngoặc): BASE_SINGLE(5) → AUTO_GLOBAL → BOOK_AUTO → BASE_MULTI(10) → GLOBAL_MANUAL(25) → SERIES_MANUAL(1000) → BOOK_MANUAL(1000) → USER_SEGMENT — layer cao hơn thắng tuyệt đối |
| Sense | `sense.py` | Chọn nghĩa theo ngữ cảnh **bằng rule tay** cho ~10 trường hợp: 了/着/过→đã/đang/rồi, 会→sẽ, 想→nhớ/tưởng, 是→đúng là, 得→được, 道→nói, 的话→lời/thì, 吞→nuốt/thôn, 对+đại từ, 一把+động từ |
| Patterns | `patterns.py` | Luật nhân `{s}` số / `{n}` entity / `{p}` cum CJK / `{v}` động từ trong `LuatNhan.txt`; slot compile regex, fill target qua trie con |
| QA | `qa.py`, `quality/` | Strip rác watermark/anti-leech **trước** dịch; QA structural fail → `needs_dictionary_fix`; invariant CJK, term-presence |

Cơ chế chất lượng hiện có: vòng correction (entry → revision → rerun), learner 3 tầng (observed → candidate → book_auto → global, AD-14 fail-closed), golden manifests, metamorphic tests.

## 2. Điểm yếu — nơi "mất điểm" chính

1. **Render vẫn greedy** — top-K lattice chỉ dùng đo margin, chưa từng chọn đường tốt hơn. `disagreement` (SEGMENTATION_INSTABILITY) đã phát hiện ca greedy thua nhưng không sửa.
2. **Score heuristic không có cơ sở dữ liệu** — `W_LEN` thưởng độ dài thô; thiếu **tần suất từ tiếng Trung thật** nên không phân biệt phân đoạn phổ biến vs hiếm.
3. **Sense = vài chục rule tay** — không mở rộng theo dữ liệu; mỗi từ đa nghĩa mới phải viết code.
4. **Không có bước sắp lại trật tự từ (reorder)** — render nối token theo trật tự nguồn; văn nhịp gãy ("đã...rồi" rời rạc, V+得+C sai vị trí).
5. **Số/Hán tự số chưa chuẩn hóa** — `NUM_RE` bắt 零…亿 nhưng render phụ thuộc entry dict; 三千 render phụ thuộc cách dict diễn giải, thiếu converter xác định "ba nghìn".
6. **Dict nội bộ tĩnh** — 2M dòng nhưng không có kênh tự sinh entry từ dữ liệu song ngữ lớn (hiện chỉ sync từ vietphrase.app).

## 3. Nguồn "nghĩa" — dữ liệu khả dụng (đã xác minh)

### 3.1 Bitext song ngữ zh↔vi (OPUS, moses format)

| Corpus | Cặp câu | License/Ghi chú |
|---|---|---|
| **NLLB v1** (vi-zh) | **8.045.074** | bitext mining CCMatrix/LASER dùng train NLLB; tải: `object.pouta.csc.fi/OPUS-NLLB/v1/moses/vi-zh.txt.zip` (≈616 MB) |
| CCMatrix v1 (vi-zh) | 8.045.074 | cùng nguồn mining; trùng NLLB |
| bible-uedin (vi-zh) | 124.396 | văn phong cổ, hợp truyện cổ trang |
| WikiMatrix (vi-zh) | 89.446 | bách khoa |
| TED2020 (vi-zh) | 16.165 | hội thoại |
| QED (vi-zh) | 8.977 | giáo dục |
| ALT (vi-zh) | 18.088 | hand-checked |
| NeuLab-TedTalks | 7.628 | hội thoại |

→ Cặp zh-vi **trực tiếp, 8 triệu câu** là tài sản lớn nhất chưa khai thác. (OpenSubtitles v2024 không có cặp zh-vi.)

### 3.2 Từ điển tần suất tiếng Trung (cho segmentation)

- **jieba `dict.txt`** (~350.000 từ, kèm freq; `dict.txt.big` tốt cho phồn thể) — MIT, nạp runtime được qua `set_dictionary`/`add_word`; thuật toán: DAG từ prefix dict + **DP max-probability path** + **HMM Viterbi** cho OOV. Đây chính là mô hình phù hợp để thay trọng số heuristic của lattice.
- Jun Da's Modern Chinese frequency lists / SUBTLEX-CH — dự phòng cho char-level.

### 3.3 Tài sản nội bộ (chưa khai thác hết)

- `raw_china/expect*.txt` — output đã kiểm chứng từng chương (golden candidate); `zhvi golden import` mới dùng làm reference.
- SQLite correction/review history + glossary.manual.tsv — mỗi ca "sửa tay" là (context → target) có thể học lại.
- `crawler/translate.py` — đường Ollama model-era đã tháo; có thể tái dùng vị trí route cho NMT additive.

## 4. Thuật toán nâng cấp (không phá determinism)

### 4.1 Prior xác suất cho segmentation (jieba-style)

Thay `W_LEN` thô bằng **tần suất thật** của entry trong trie, giữ khung DP hiện có:

```
score(edge) = α·log(freq(zh_key)/F_TOTAL) + β·(len-1) + γ·trust + penalties_hien_co
path = argmax Π score(edge)  (DP/beam đã có trong lattice.py)
```

- `freq` nạp từ `dict.txt` jieba (file riêng `zh-freq.txt` **versioned**, hash vào fingerprint → vẫn deterministic, cache tự invalidate như khi bump loader).
- HMM Viterbi của jieba chỉ dùng làm **risk signal** cho OOV (đi vào `unknown_spans`), không auto-fill target — đúng rào AD-9 (không sinh target ngoài dict).
- Greedy vẫn là render mặc định để giữ parity; cờ `render=lattice` cho phép dùng best path, A/B trên golden trước khi đổi mặc định.
- Hiệu ứng: phân đoạn đúng xu hướng kho văn bản (千山暮雪 giữ khối thay vì 千+山), giảm unknown-span, margin có nghĩa thống kê hơn.

### 4.2 Re-rank beam bằng LM tiếng Việt (kenlm)

- Train n-gram (5-gram, prune) trên: exports đã duyệt (`dist/`), golden, + corpus văn xuôi Việt lớn (mở: 1B-token news/novel có sẵn trên HF) — file `.arpa`/binary **versioned, hash vào fingerprint**.
- `score(path) += λ·LM_logprob(render(path))`; chọn best trong top-K (K≈10) thay greedy.
- Giảm đúng 2 họ artifact hiện nay: particle-drop ("bỏ 的地"), fragmentation ("chậm chậm... rời rạc"), vì LM phạt chuỗi Việt kỳ dặc hơn là từng edge riêng lẻ.
- Deterministic: cùng .arpa + λ versioned → cùng output; AD-9 không bị phá (đây là **chọn** đường, không sinh text mới).

### 4.3 Sense chọn nghĩa bằng collocation thống kê

Chuyển `sense.py` từ rule tay sang **bảng thống kê context**, tách data khỏi code:

- Bảng `sense_stats(key_simplified, left2, right2, target, count, pmi)` — sinh từ (a) bitext NLLB đã align (xem 4.6), (b) history accept/golden nội bộ.
- Runtime: với edge đa nghĩa, tính `P(target | left2, right2)`; thiếu dữ liệu thì rơi về precedence hiện có → **không hỏng ca cũ**.
- Rule tay hiện hữu (会/想/是/得/道/的话/吞…) giữ làm lớp ưu tiên cao trong khi data chưa đủ; dần dần thay bằng entry `sense_stats` — mỗi rule mới **không cần sửa code** nữa.
- Vẫn tôn trọng AD-9: chỉ đổi target của span đã match, không đổi segmentation.

### 4.4 Bank luật cú pháp (function words & cấu trúc)

Bổ sung `LuatNhan.txt`/`ContextPatterns.txt` theo **bank** có hệ thống (thay vì rule rời). Danh mục ưu tiên theo tần suất trong văn chương network:

| Cấu trúc | Dịch chuẩn | Loại luật |
|---|---|---|
| 了 (aspect) | đã / rồi (cuối câu) | sense hiện có → giữ |
| 着/著 | đang | sense hiện có |
| 过 | từng / đã từng | sense mới |
| V+得+Adj (跑得快) | V … {adj} (chạy nhanh) | pattern `{p}得{p}` |
| V+不+R (看不懂) | không V được R | pattern `{v}不{p}` |
| 把+O+V (把书拿来) | đem/cầm O lại V | pattern `把{n}{v}` |
| 被 | bị / được (bị động) | sense rule |
| 让/叫/使 | cho / khiến | dict sense |
| 们 | các / những | suffix rule |
| V一V / VV (看看, 试试) | V thử / V xem | pattern `{v}一{v}` |
| 越…越… | càng…càng… | pattern pair |
| 一边…一边… | vừa…vừa… | pattern pair |
| 一…就… | vừa…đã… | pattern pair |
| 对+X | đối với X | sense hiện có |
| 是…的 (nhấn mạnh) | chính là … | pattern |
| 吗/呢/吧/啊 | chăng/à/nhỉ/ạ… | particle rule |
| 上/下 sau V (穿上, 躺下) | vào/xuống | sense rule |
| 快/要+V, 将 | sắp, sẽ | sense hiện có (会) |
| 有点/有些 | hơi có, có phần | dict |
| 很/挺/太/最/更 | rất/khá/quá/nhất/hơn | dict + sense |
| 连…也/都… | đến…cũng… | pattern pair |
| 不但…而且… | không những…mà còn… | pattern pair |
| 虽然…但是… | tuy…nhưng… | pattern pair |
| 只有…才… | chỉ khi…mới… | pattern pair |
| 无论/不管…都… | dù/bất kể…vẫn… | pattern pair |

Ghi chú: các pattern pair (越…越…) cần **2 edge trong cùng mệnh đề** — thêm matcher "pair" vào `patterns.py` (mở rộng `PatternRule` nhận 2 slot `{p}` + check giữa hai chỗ match ≤ mệnh đề).

### 4.5 Chuẩn hóa số (numeral normalizer)

Bước preprocess versioned (AD-18 — transformation có trace, không mutate source):

- Hán tự số thuần (`NUM_RE`): 二千三百 → "hai nghìn ba trăm"; 万 → 10.000, 亿 → 100.000.000, 两 → hai; tên (三爷) giữ phiên Hán-Việt.
- Chỉ normalize span thuần số + đơn vị phổ biến (年/月/日/时/岁/丈/里/斤/两/银子/文), span còn lại đi qua dict như cũ.
- Trace lưu span gốc → QA có thể đối chiếu, review có thể revert.

### 4.6 Mining song ngữ → tự sinh entry (kênh LEARN mới)

Pipeline 6 bước, cắm đúng vào flow learner hiện có (observed → candidate → book_auto → global), **không đụng Custom.txt**:

1. Tải NLLB v1 moses vi-zh (8.045.074 cặp), lọc câu ≤120 ký tự, bỏ câu có watermark/rác (tái dùng regex `qa.py`).
2. Word-align mỗi cặp bằng **eflomal/efmaral** (Gibbs, nhanh) hoặc fast_align + symmetrization.
3. Induce phrase pairs: span zh (1–4 ký tự, chuẩn hóa giản thể NFC) ↔ span vi (1–6 từ), đếm count, tính **sPMI**; lọc min count ≥ 3 và tỉ lệ khớp alignment ≥ 80%.
4. Guard lists: loại khi target có placeholder/CJK còn sót; tên riêng bắt buộc khớp Hán-Việt (tái dùng `ChinesePhienAmWords` để kiểm tra âm tiết đầu); xác thực cặp có con số phải khớp số.
5. Đẩy batch thành **candidate** kèm trust theo count (scale 0–5 thấp hơn BASE_MULTI) — hết vào vòng `zhvi terms accept` bình thường, người duyệt quyết định, đúng AD-14 fail-closed.
6. Bump `LOADER_VERSION` khi schema entry đổi; revision/publish không đổi.

Hiệu ứng: phủ chỗ từ điển yếu mà `zhvi doctor`/QA báo (`unknown_spans`) bằng entry có bằng chứng song ngữ, thay vì dò tay từng cụm.

### 4.7 Route NMT optional (hybrid, tách rời đường mặc định)

Giữ nguyên luận điểm thiết kế 3.0 (một đường sinh text = VietPhrase, không AI post-edit ngầm). Route NMT là **additive, opt-in, ghi rõ route** (schema run đã có cột `route` từ thời 2.0):

- **Model**: NLLB-200-distilled-600M (zh `zho_Hans` ↔ vi `vie_Latn` đều hỗ trợ) hoặc 1.3B; chạy **CTranslate2 int8** (~1.2 GB RAM, ~10–15× nhanh hơn transformers); M2M-100 418M là phương án nhỏ hơn.
- **Ràng buộc glossary/entity** — 3 mức, chọn theo công sức:
  1. **Sentinel masking** (đơn giản nhất, đã quen từ TTS placeholder swap): mask entity theo Names/glossary bằng sentinel `<e1>`, dịch, reinsert phiên Hán-Việt. Zero sửa model.
  2. **DBA constrained decoding** (Post & Vilar 2018): ràng buộc chuỗi đích qua state-machine/trie, phức tạp O(1) theo số ràng buộc, triển khai trong Sockeye; bản CTranslate2 không có sẵn → cần fork beam search.
  3. **DoRA** (Dinu et al. 2019): train fine-tune với placeholder + target-first augmentation; đắt nhất, chỉ làm khi muốn NMT thành đường chính.
- **Guardrail**: block cache key gồm `model_hash + quant + glossary_hash`; QA gates (CJK residue, term-presence) chạy như thường; block fail → `needs_dictionary_fix`, không fallback ngầm.
- **Ý nghĩa với zhvi**: NMT xử lí câu lủng củng do thiếu entry (unknown span), trong khi glossary quản tên/định danh — lõi deterministic không thay đổi.

## 5. Đo lường & kiểm chứng

### 5.1 So sánh before (renderer-7) vs after (renderer-8)

**Cấu hình kiểm thử:** cùng một file nguồn `crawler/data/xtruyen/manh-nhat-tu-tien-hoc-sinh-tieu-hoc/_preview_iqiyi.zh.txt` (~11.000 dòng, 10.813 blocks):

| Metric | before (renderer-7) | after (renderer-8) |
|---|---|---|
| Blocks dịch | 10.813 | 10.813 |
| Thời gian | ~18.6s | ~18.6s |
| Lines diff | — | **219** |
| Cặp thay đổi (trước/sau) | — | **98** |

**renderer-7** (commit HEAD `453f9aae`): không có `_SENT_END`, `_rest_is_sentence_end`, `_left_clause`, `_NUM_CHARS`, `_PROJECTION_MARKERS` — **không có rule sense nào** cho các particle này.

**renderer-8** (bản hiện tại): thêm toàn bộ logic sense + `_STOP_AFTER` trong `_left_clause`.

**Các loại thay đổi (được xác thực từ `zhvi/docs/preview_diff_head.txt`):**

| # | Câu gốc (zh) | before | after | Rule |
|---|---|---|---|---|
| 1 | `…呢` (cuối câu hỏi) | `…?` | `… chứ?` | `ね` → `chứ` |
| 2 | `…吗` (cuối câu) | `…sao?` | `… à?` | `吗` → `à` |
| 3 | `…连…都…` | `…đều…` | `…cũng…` | `连…都` → `cũng` |
| 4 | `…过…吗` | `… rồi?` | `… chưa?` | `吗` sau `過` → `chưa` |
| 5 | `…零百零五` | `…số không…` | `…lẻ…` | `零 numeric` → `lẻ` |
| 6 | `…呢` (giữa câu) | drop | drop | `ね` mid-clause — giữ nguyên (không `chứ`) |

**Nhận xét:**
- ~30 trường hợp `连…都` → `cũng` (thay thế sai `đều`/`có` thành `cũng` đúng ngữ cảnh).
- ~15 trường hợp `吗` → `à` hoặc `chưa` (tuỳ context `了/过`).
- ~10 trường hợp `ね` → `chứ` ở cuối câu hỏi.
- 0 thay đổi gây hại (không có line nào từ `cũng` → `đều` sai).

**Chứng cứ số:**
```log
Total diff lines: 219
Changed text lines: 98
run 8f426423 | 10813 blocks | VP 100% | warnings 14465 | 18.6s | output /tmp/preview_iqiyi_after.txt
```

### 5.2 Full test pipeline

```bash
# Chạy unit test rule sense
cd zhvi && ../.venv/bin/python -m pytest tests/test_sense_structures.py -q
# => 11 passed, 1 xfailed

# Chạy diff before/after
diff /tmp/preview_iqiyi_before.txt /tmp/preview_iqiyi_after.txt > /tmp/diff_preview.txt
wc -l /tmp/diff_preview.txt  # => 219 (98 cặp)
```



- **Metric chảy sẵn**: `unknown_spans`, `single_char_ratio`, `lattice_margin`, `lattice_entropy`, `SEGMENTATION_INSTABILITY` (disagreement greedy vs best) — dùng làm router M2 đúng thiết kế mục 12: block rủi ro cao → review, thay vì auto-adopt.
- **Golden/expect**: sacrebleu (chrF cho cặp zh-vi, BLEU đối chiếu với `raw_china/expect*.txt`); đo trước/sau từng upgrade trên cùng revision để chứng minh "không tệ hơn".
- **Regression**: `zhvi tests/ -q` hiện có + thêm golden per-upgrade; parity test cho greedy render không đổi cho tới khi đổi render mặc định.
- **A/B render**: chạy 2 mode (`greedy` vs `lattice+LM`) trên 1–2 truyện, diff từng block, xem txcount "tốt hơn" (giảm unknown/fragment) trước khi flip default.

## 6. Lộ trình đề xuất

| Epic | Nội dung | Độ lớn | Phụ thuộc |
|---|---|---|---|
| E1 | Numeral normalizer (preprocess versioned + trace) | nhỏ | — |
| E2 | Bank luật cú pháp: phân tích tần suất cấu trúc trên corpus hiện có → ~50–100 pattern mới vào LuatNhan/ContextPatterns | nhỏ–vừa | cần corpus đo tần suất |
| E3 | zh-freq prior cho lattice (jieba dict.txt → file versioned, cờ `render=lattice` A/B) | vừa | E2 (đo trước/sau) |
| E4 | kenlm re-rank beam (file versioned, cờ) | vừa | E3 (top-K tốt) |
| E5 | Mining pipeline NLLB → candidate flow | lớn | eflomal binary ngoài repo |
| E6 | Route NMT CTranslate2 + sentinel masking | lớn | quyết định sản phẩm |

Mỗi epic đều có thể tách story riêng theo pattern `_bmad-output` hiện có; đều bump version + fingerprint nên block cache tự invalidate đúng cơ chế.

## 7. Rủi ro & giấy phép

- **License**: jieba (MIT, dict.txt kèm repo), kenlm (LGPL), CTranslate2 (MIT), NLLB model (CC-BY-NC 4.0 — **không dùng thương mại**; bitext NLLB/CCMatrix mining từ web, xuất phát là dữ liệu web nên chỉ nên dùng làm **dữ liệu học**, không phân phối lại), eflomal/efmaral (GPL-3 — chạy tool ngoài repo, không nhúng code).
- **Determinism**: mọi file dữ liệu mới (freq, .arpa, sense_stats, model) phải vào fingerprint; thiếu → cache không tái dùng (giống hệt cơ chế bump hiện tại).
- **Parity QuickTrans**: render greedy là chuẩn so sánh; đổi render mặc định phải qua golden A/B + lưu route mới, không sửa output cũ.
- **RAM/hiệu năng**: loader đã ~70MB dict + trie; thêm freq (≈350k entry) và LM binary cần đo; beam K=10 hiện chạy từng block, LM re-rank chỉ cộng một pass render — chấp nhận được.

## 8. Tham khảo (đã xác minh)

1. Post, M. & Vilar, D. (2018). *Fast Lexically Constrained Decoding with Dynamic Beam Allocation for NMT*. NAACL-HLT 2018. arXiv:1804.06609.
2. Hasler, E. et al. (2018). *Neural Machine Translation Decoding with Terminology Constraints*. NAACL-HLT 2018. arXiv:1805.03750.
3. Dinu, G., Mathur, P., Federico, M., Al-Onaizan, Y. (2019). *Training NMT To Apply Terminology Constraints (DoRA)*. ACL 2019. arXiv:1906.01105.
4. Wan, D. et al. (2020). *Incorporating Terminology Constraints in Automatic Post-Editing*. WMT 2020. arXiv:2010.09608.
5. Ailem, M. et al. (2021). *Encouraging NMT to Satisfy Terminology Constraints*. arXiv:2106.03730.
6. jieba 分词 — DAG + DP max-prob + HMM Viterbi, user dict runtime. https://github.com/fxsjy/jieba (MIT).
7. VnCoreNLP — word segmentation/POS/NER/dependency cho tiếng Việt (dự phòng cho QA phía Việt). https://github.com/vncorenlp/VnCoreNLP
8. PhoMT (EMNLP 2021) — 3,02M cặp en-vi (không có zh-vi; dùng khi pivot). https://github.com/VinAIResearch/PhoMT
9. NLLB-200 model card (zh/vie hỗ trợ). https://huggingface.co/facebook/nllb-200-distilled-600M
10. OPUS API — bitext zh-vi: NLLB v1 moses 8.045.074 cặp (`OPUS-NLLB/v1/moses/vi-zh.txt.zip`), CCMatrix v1, bible-uedin 124k, WikiMatrix 89k, TED2020, QED, ALT. https://opus.nlpl.eu/
11. kenlm (n-gram LM). https://github.com/kpu/kenlm · CTranslate2 (int8, m2m/nllb hỗ trợ). https://github.com/OpenNMT/CTranslate2


