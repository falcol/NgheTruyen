---
id: SPEC-zhvi-vietphrase-only
companions:
  - pipeline-contract.md
  - data-model.md
  - migration-and-milestones.md
  - ../../planning-artifacts/architecture/architecture-NgheTruyen-2026-09-03/ARCHITECTURE-SPINE.md
sources:
  - ../../thiet-ke-he-thong-dich-truyen-zh-vi.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# zhvi VietPhrase-only — translation memory compiler

## Why

`zhvi` hiện mang di tích của thiết kế 2.0: model router bốn route, engine Hachimi/Qwen qua Ollama, prompt schema, local patch và AI post-edit. Điều này làm hệ thống phụ thuộc network/model runtime, khó tái lập, và chất lượng bị phân mảnh giữa hai nguồn chân lý (text do model sửa và dictionary). Thiết kế 3.0 (final) buộc cutover: `zhvi` trở thành **translation memory compiler dựa hoàn toàn trên VietPhrase** — một đường sinh văn bản duy nhất, offline, deterministic, chất lượng đi lên qua vòng lặp kiểm chứng được: đo chỗ từ điển yếu → tạo entry/rule xác định → regression → revision mới → dịch lại. Người chịu tác động: Falcol vận hành pipeline dịch truyện Trung–Việt cho NgheTruyen.

## Capabilities

- **CAP-1**
  - **intent:** Người dùng dịch một TXT tiếng Trung sang tiếng Việt hoàn toàn offline bằng duy nhất engine VietPhrase trên một dictionary revision đã freeze.
  - **success:** Cùng source revision + dictionary revision + config tạo cùng output SHA-256; không còn runtime dependency, network call hay process nào dành cho model dịch/edit (acceptance #1, #3).

- **CAP-2**
  - **intent:** Hệ thống build, validate, activate, diff và rollback dictionary revision bất biến content-addressed; mỗi run pin đúng một revision.
  - **success:** Revision đổi sau khi run tạo không làm thay nội dung run đang chạy hoặc run được resume; resume/reproduce đọc đúng bundle đã pin; rollback tạo revision mới, bundle lịch sử chỉ đọc.

- **CAP-3**
  - **intent:** Hệ thống tự phát hiện cụm từ/tên riêng/segmentation yếu trong phạm vi một truyện và promote auto entry an toàn qua hard gates.
  - **success:** Candidate chỉ được book-auto khi có deterministic single target, không manual conflict, structural QA pass, affected-block isolation pass; ghi vào `glossary.auto.tsv` và chỉ ảnh hưởng truyện đó; candidate không dựng được target luôn ở `unresolved`.

- **CAP-4**
  - **intent:** Hệ thống tích lũy evidence qua nhiều truyện độc lập và promote entry toàn cục qua registry tại dictionary root.
  - **success:** Occurrence dedupe theo `(book_id, source_revision_id, candidate_id, occurrence_span)` nên copy/import lại không tăng cross-book count; thiếu approved golden manifest hoặc cross-book evidence thì không có candidate nào vượt `global_candidate`.

- **CAP-5**
  - **intent:** Người dùng sửa chất lượng bản dịch bằng cách tạo/cập nhật dictionary entry hoặc rule, sau đó hệ thống tự build revision mới và dịch lại đúng các block bị ảnh hưởng.
  - **success:** Số block thay đổi đúng tập block chứa candidate/key; không tồn tại "bản text đã sửa" như nguồn chân lý thứ hai; export lại atomic.

- **CAP-6**
  - **intent:** Người dùng xem được segmentation trace, entry nào tạo từng target span, lớp/revision của entry, candidate liên quan và các block khác sẽ bị ảnh hưởng.
  - **success:** 100% output span truy được tới source literal hoặc versioned VietPhrase entry/rule/transformation (acceptance #2).

- **CAP-7**
  - **intent:** QA structural kiểm mỗi run và chỉ pass hoặc chặn export.
  - **success:** QA fail chuyển run sang `needs_dictionary_fix`, không export, không sửa output; các metric (coverage, unknown, CJK residue, fragmentation, regression pass/fail) báo cáo riêng lẻ, không có quality score tổng hợp.

- **CAP-8**
  - **intent:** Người dùng import candidate reference (`raw_china/expect*.txt`, `raw_china/excpect*.txt`), xem diff report so với output pipeline, và duyệt case vào golden manifest.
  - **success:** Pipeline chạy và xuất diff report với toàn bộ candidate reference; chỉ case có source hash + expected hash + phạm vi assertion + provenance + dấu duyệt mới tham gia promotion gate.

- **CAP-9**
  - **intent:** Migration brownfield từ thiết kế 2.0 sang 3.0 mang tính cộng thêm: giữ lịch sử, vô hiệu hóa mọi artifact model-era.
  - **success:** Source revision/run/block/route lịch sử được giữ read-only; mọi cache chứa prompt/model/router fingerprint bị invalidate và không tái dùng; sau cutover runtime không còn model workers/dependencies/config/flags và run mới chỉ ghi route `VIETPHRASE`.

- **CAP-10**
  - **intent:** Người dùng vận hành toàn bộ vòng đời qua CLI Typer: init, import, learn, translate, terms, dict, explain, status, export, doctor — không còn cờ model.
  - **success:** Happy path `zhvi translate truyen.txt -o truyen.vi.txt` chạy snapshot → discover → book-auto learn → freeze revision → translate → QA → export → report; `--hachimi`, `--qwen` và profile model bị loại bỏ.

- **CAP-11**
  - **intent:** Hệ thống tự kiểm định regression không cần model: dictionary unit tests, golden corpus, metamorphic invariants.
  - **success:** Thêm entry không có trong source không đổi output; reorder file auto không đổi output; dịch cả truyện một lần == theo từng chương; resume == clean run; rollback + chạy lại khôi phục output hash tương ứng; phồn/giản thể alias chọn cùng entry.

## Constraints

- VietPhrase là đường sinh văn bản duy nhất; cấm model inference, network model call, local patch, post-edit (AD-1).
- Không sửa trực tiếp văn bản đích sau khi dịch; mọi correction phải truy được về entry/rule và revision đã tạo ra nó (AD-2, acceptance #4).
- Run đọc đúng một dictionary revision bất biến content-addressed; không đọc file nguồn/projection sau khi pin (AD-3).
- Không học hoặc promote trong vòng lặp dịch; dịch không quan sát promotion giữa run (AD-4, acceptance #5).
- Precedence khi cùng normalized key/span: `manual book > manual global > Custom/QualityOverrides > auto book > auto global > base`; span dài thắng span ngắn; máy không bao giờ ghi file human-owned (AD-5).
- Không bịa target để đạt coverage; không dựng được target đơn nghĩa thì `unresolved` (AD-6, acceptance #6).
- Mỗi bước promotion phải pass hard gate; điểm tổng hợp cao không được bù cho hard gate thất bại; promotion fail regression phải bị reject (AD-7, acceptance #7).
- SQLite sở hữu state (book + registry); `AutoVietPhrase.txt`, `glossary.auto.tsv`, trie cache chỉ là projection dựng lại được (AD-8).
- Render deterministic: longest-match → layer precedence → literal-over-pattern → tie-break theo `entry_id`, không phụ thuộc iteration order (AD-9).
- QA chỉ đọc; fail dẫn tới dictionary fix + rerun, không export (AD-10, acceptance #9).
- Cache key chứa source block hash + dictionary revision + parser/renderer/QA version; output manifest chứa run ID, revision ID, SHA-256 (AD-11).
- Rollback là revision mới; không sửa revision lịch sử (AD-12).
- Một writer lock mỗi mutation scope (project, registry); registry xác định duy nhất qua `realpath(dict_dir)`; activation dùng CAS (AD-13).
- Global promotion fail-closed: thiếu approved golden manifest, cross-book evidence, target agreement hoặc affected-block isolation thì dừng ở `global_candidate`; file tên `expect*` không tự thành golden (AD-14, acceptance #8).
- Publish revision: build temp → fsync → atomic rename → SQLite transaction insert `ready` + CAS active pointer → projection sau commit; không yêu cầu transaction xuyên DB/filesystem (AD-15).
- `active_revisions(scope_type, scope_id)` tối đa một row mỗi scope; global activation không đổi active book revision (AD-16).
- Cross-book evidence không đếm trùng book/source revision (AD-17).
- Preprocessing/rendering là transformation có version và source-offset trace; tham gia fingerprint (AD-18).
- Migration chỉ add/transform, không drop lịch sử (AD-19).
- Book-auto hard gate tối thiểu + export bắt buộc 100% trace (AD-20).
- Mọi field config ảnh hưởng dictionary/segmentation/render phải nằm trong fingerprint; đổi ngưỡng learning tạo evaluation mới, đổi tập entry active tạo revision mới.
- Ctrl-C giữ block đã commit; resume pin revision cũ; muốn revision mới phải fork run.
- SQLite WAL + `synchronous=FULL` cho mutation quan trọng; block chỉ `committed` khi output + trace + QA metadata cùng transaction.
- Promotion/candidate chỉ ghi event append-only có `before`, `after`, actor, timestamp, provenance.

## Non-goals

- Dịch bằng mô hình ngôn ngữ hoặc mô hình máy dịch; viết lại câu cho "mượt" sau khi VietPhrase sinh kết quả.
- Tự đoán nghĩa mới khi từ điển không cung cấp đủ dữ liệu; auto-promote target mơ hồ theo context.
- Ghi máy vào `Custom.txt`, `QualityOverrides.txt`, `VietPhrase_*.txt`, `glossary.manual.tsv` hoặc file `.manual.*`.
- Tối ưu văn phong bằng thông tin không thể biểu diễn thành entry/rule.
- Service/API phân tán, worker queue, web UI duyệt candidate — CLI foreground là sản phẩm chính.
- Đồng bộ revision đa máy (export/import manifest trước mắt); tokenizer ngoài VietPhrase.

## Success signal

`zhvi translate truyen.txt -o truyen.vi.txt` chạy offline, tạo output có manifest truy được 100% span về source literal hoặc entry/rule; chạy hai lần cùng fingerprint ra cùng SHA-256; toàn bộ 10 acceptance criteria của thiết kế 3.0 pass và diff report so với mọi candidate reference `raw_china/expect*.txt` + `raw_china/excpect*.txt` đã được xuất để duyệt. Global auto-promotion vẫn khóa cho tới khi có golden manifest được duyệt — đó là trạng thái đúng, không phải thiếu sót.

## Assumptions

- Các ngưỡng học tự động (occurrence/chapter/cross-book/PMI/regression budget) là default khởi tạo an toàn, không phải invariant.
- `raw_china/expect*.txt` và legacy `excpect*.txt` hiện chỉ là candidate reference chưa duyệt; global auto-promotion giữ khóa tới khi có golden manifest hợp lệ.
- Book-auto bật mặc định sau hard gates; nếu benchmark cho thấy false promotion đáng kể, default chuyển thành candidate-only mà không đổi AD-1–AD-17.

## Open Questions

- Golden manifest approval workflow: ai duyệt, dấu duyệt có định dạng gì, khi nào tạo golden corpus đại diện đầu tiên?
- File legacy viết sai tên `raw_china/excpect2.txt` giữ nguyên để audit hay chuẩn hóa tên khi import vào golden tooling?
