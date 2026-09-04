# Pipeline contract — zhvi VietPhrase-only

Chi tiết thực thi của pipeline; đọc cùng SPEC.md. Số bước và tên khóa trỏ về thiết kế 3.0.

## Hai pha độc lập

- **LEARN**: đọc corpus, tạo candidate, chạy mô phỏng, tạo dictionary revision mới. Không tạo bản dịch cuối.
- **TRANSLATE**: chỉ đọc source snapshot + dictionary revision đã freeze. Không học, không promote, không đổi file từ điển.

Ranh giới ngăn cùng một run dịch chương đầu và chương cuối bằng hai phiên bản từ điển khác nhau.

## 9 bước pipeline

1. **Snapshot nguồn**: import TXT thành source revision bất biến; SHA-256 trên bytes; lưu encoding; parse lossless (phần không dịch được giữ nguyên byte-equivalent khi export); source byte-identical là no-op.
2. **Discovery toàn truyện** (chạy trước khi dịch): CJK n-gram 2–8 ký tự; tần suất tuyệt đối + theo chương; left/right context diversity; PMI/association; chuỗi bị tách thành nhiều entry một ký tự; unknown span; segmentation đa phương án gần điểm; pattern tên người/địa danh/môn phái/công pháp/cảnh giới; cụm lặp render không ổn định. Discovery chỉ tạo observation — không nạp vào engine.
3. **Sinh target không dùng AI** — chỉ từ: (1) target có sẵn ở lớp VietPhrase thấp hơn; (2) ghép longest-match từ entry con đã biết; (3) phiên âm Hán–Việt từ `ChinesePhienAmWords.txt` cho candidate là tên riêng; (4) template trong `LuatNhan.txt`; (5) correction/glossary người dùng nhập; (6) target đã accept ở truyện khác còn đủ provenance. Không có target từ nguồn trên thì `unresolved`.
4. **Chuẩn hóa candidate**: key NFC + giản thể để so khớp; source gốc lưu để audit; target chuẩn hóa khoảng trắng/dấu câu theo rule xác định; candidate ghép từ entry con chỉ auto-promote khi mỗi entry con có đúng một target ưu tiên; target có `a/b`, placeholder hoặc ký tự CJK bị loại khỏi auto-promote; candidate trùng manual entry bị loại.
5. **Tính evidence** (độc lập với output cuối): độ mạnh cụm (frequency, PMI, left/right entropy); độ ổn định (cùng segmentation + target qua các occurrence); lợi ích (giảm unknown, giảm single-character span, giảm fragmentation); rủi ro (overlap conflict, target ambiguity, manual conflict, junk likelihood); phạm vi (số chương/truyện/thể loại); regression (số block đổi, golden diff, invariant failures). Điểm chỉ để xếp hạng; hard gate không được bù.
6. **Promotion theo tầng**: lifecycle `observed → candidate → book_auto → global_candidate → global_auto`; nhánh `unresolved`, `rejected`, `revoked`; `revoked → candidate` khi sửa evidence/target.
7. **Build dictionary revision**: 10 bước build (xem data-model.md §Publish protocol).
8. **Dịch**: freeze `dictionary_revision_id` khi tạo run; cache key = source block hash + dictionary revision + parser version + renderer version + QA version; block cache cũ chỉ dùng khi toàn bộ key trùng; Ctrl-C giữ block đã commit.
9. **QA và export**: QA không sửa văn bản — pass hoặc chặn: đủ block đúng thứ tự; không duplicate/missing; structural span dựng lại được; không placeholder nội bộ; CJK residue không vượt policy; không artifact lặp do ghép span; entity nhất quán theo revision; output hash + manifest khớp. Fail thì run `needs_dictionary_fix`.

## Book-auto hard gates (default khởi tạo)

- Tên riêng: ≥ 3 occurrence ở ≥ 2 chương; cụm thông thường: ≥ 5 occurrence ở ≥ 2 chương.
- Target stability = 100%; không conflict với manual; coverage hoặc fragmentation phải cải thiện; mọi structural invariant pass; số block thay đổi đúng tập block chứa candidate.

## Global-auto hard gates (default khởi tạo)

- ≥ 3 truyện độc lập; ≥ 20 occurrence tổng; target agreement = 100%; không manual conflict ở mọi project đã đăng ký; pass toàn bộ golden corpus; không tăng unknown/CJK residue/structural failure; diff ngoài các block chứa key bằng 0.
- Chưa có golden corpus đại diện: chỉ auto-promote tới `book_auto`; `global_candidate` chờ duyệt hoặc đủ regression evidence.

## Đường dịch chính (deterministic)

1. Chuẩn hóa phồn thể → giản thể để match, giữ source gốc trong trace.
2. Trie lookup → 3. longest-match → 4. precedence theo lớp → 5. literal thắng pattern khi cùng độ dài → 6. tie-break cố định theo `entry_id` → 7. render target, dựng lại structural span.

Lattice/top-K nếu tồn tại chỉ phục vụ LEARN (tìm segmentation không ổn định), không quyết định route.

Preprocessing trước matcher: deterministic, version hóa; junk stripping chỉ xóa span khi rule trả về source offsets + reason code; source snapshot không đổi; repetition collapse là quy tắc renderer trên ranh giới hai target span; cả hai xuất trace.

## Correction policy

CLI không có editor sửa từng block. Review hiển thị: source span; segmentation trace; entry tạo từng target span; lớp + revision của entry; candidate liên quan; các block khác bị ảnh hưởng nếu đổi entry. Người dùng sửa cụm = tạo/cập nhật entry trong `glossary.manual.tsv`, rồi hệ thống: build revision mới → xác định affected blocks bằng trace/source index → dịch lại → chạy QA → export lại atomic. Không lưu "bản text đã sửa" làm nguồn chân lý thứ hai.

## CLI contract

| Command | Mục đích |
|---|---|
| `zhvi init PROJECT` | tạo book project (stable `book_id`) |
| `zhvi import FILE -p PROJECT` | tạo source revision |
| `zhvi learn -p PROJECT` | discovery, candidate, evaluate, book promotion |
| `zhvi learn -p PROJECT --global` | đánh giá cross-book/global promotion |
| `zhvi translate FILE` | happy path VietPhrase-only |
| `zhvi translate -p PROJECT --no-learn` | dịch bằng revision active hiện tại |
| `zhvi terms list -p PROJECT` | xem candidate/evidence/trạng thái |
| `zhvi terms accept ID -p PROJECT` | tạo manual entry từ candidate |
| `zhvi terms reject ID -p PROJECT` | reject candidate có audit event |
| `zhvi terms revoke ID -p PROJECT` | thu hồi auto entry, build revision mới |
| `zhvi dict diff REV_A REV_B` | xem entry + affected-block diff |
| `zhvi dict rollback REV -p PROJECT` | tạo revision mới từ revision an toàn |
| `zhvi explain TEXT -p PROJECT` | xem segmentation + provenance |
| `zhvi status -p PROJECT` | run/revision/candidate/regression status |
| `zhvi export -p PROJECT` | dựng lại TXT từ run hoàn tất |
| `zhvi doctor` | kiểm tra dictionary, DB, disk, smoke translation |

Cờ `--hachimi`, `--qwen`, profile `fast|balanced|quality` bị loại bỏ.

## Config schema đề xuất

```toml
style = "convert-qt"
output_policy = "strict-final"
encoding = "utf-8"
dict_dir = "crawler/vietphrase/dicts"
global_glossary = "~/.config/zhvi/glossary.manual.tsv"
pattern_rules = true
collapse_repetitions = true
qa_strip_junk = true

[learning]
enabled = true
auto_scope = "book"
max_phrase_chars = 8
min_name_occurrences = 3
min_term_occurrences = 5
min_chapters = 2
require_unambiguous_target = true
require_affected_block_isolation = true
global_min_books = 3
global_min_occurrences = 20
global_require_golden_suite = true

[runtime]
checkpoint_blocks = 50
```

## Regression 3 lớp (không cần model)

- **Dictionary unit tests**: parse mọi dòng; auto entry không duplicate/conflict cùng scope/lớp (conflict legacy dùng tie-break đã freeze + diagnostic); precedence đúng; traditional/simplified alias đúng; rule pattern không nuốt literal dài hơn; output deterministic.
- **Golden corpus**: manifest tại `zhvi/tests/golden/manifest.json`; nhập `raw_china/expect*.txt` + `excpect*.txt` làm candidate rồi tạo diff report để duyệt; chỉ case có source/expected hash + trạng thái `approved` tham gia promotion gate; so sánh byte hoặc approved structural diff; mỗi diff truy được tới candidate/entry; global promotion không tạo unreviewed diff ngoài affected blocks.
- **Metamorphic**: thêm entry không có trong source không đổi output; reorder file auto không đổi output; dịch cả truyện một lần == từng chương; resume == clean run; rollback + chạy lại khôi phục output hash; phồn/giản thể alias chọn cùng entry.

## Báo cáo chất lượng mỗi run

`dictionary_revision_id`; coverage theo ký tự và source span; unknown spans; single-character span ratio; fragmentation ratio; candidate count theo trạng thái; số entry book-auto/global-auto được dùng; affected blocks do revision mới; regression pass/fail; output SHA-256; elapsed time + chars/s. Không có quality score tổng hợp.
