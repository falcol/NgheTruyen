# Rubric Review — Architecture Spine zhvi VietPhrase-only

## Verdict

**FAIL — chưa thể handoff cho implementation.** Hướng kiến trúc cốt lõi là đúng (VietPhrase-only, LEARN/TRANSLATE tách pha, revision bất biến, SQLite sở hữu state), nhưng artifact hiện tại bị mất nội dung ngay trong các AD và bảng conventions. Vì vậy nhiều divergence point ở tầng implementation không còn Rule có thể thi hành.

Review này đối chiếu:

- `ARCHITECTURE-SPINE.md`
- `thiet-ke-he-thong-dich-truyen-zh-vi.md`
- Good-spine checklist trong `bmad-architecture/references/reviewer-gate.md`

Deterministic lint được chạy và trả `ok: true`, `total_findings: 0`. Kết quả đó là false negative đối với lỗi ngữ nghĩa/nội dung dưới đây; lint hiện không phát hiện AD bị cắt sau khi vẫn còn token `AD-n`.

## Điểm đã đạt

- Paradigm pipes-and-filters hai pha được gọi tên và vẽ đúng trục LEARN → revision → TRANSLATE.
- AD-1 chốt rõ VietPhrase là engine duy nhất và loại model/post-edit khỏi đường sinh target text.
- Ý định revision bất biến, rollback bằng revision mới, SQLite là state authority, global promotion fail-closed và writer-lock đã xuất hiện.
- Structural seed đủ gọn ở mức initiative và capability map cho thấy các khu vực chính.
- Không có công nghệ ngoài nào được khóa version nên tiêu chí “named tech verified-current” không phát sinh vi phạm trong phạm vi artifact này.

## Findings

### R-01 — CRITICAL — Spine bị cắt/méo, nhiều AD không còn đủ Binds/Prevents/Rule

**Evidence**

- `ARCHITECTURE-SPINE.md:45-61`: AD-2 chỉ còn `Binds`, sau đó là mảnh `entry/rule`; AD-3 chỉ còn nhãn; AD-4 mất `Binds` và `Prevents`.
- `ARCHITECTURE-SPINE.md:81-97`: AD-8, AD-9 và AD-10 chỉ còn các mảnh câu, không có cấu trúc quyết định hoàn chỉnh.
- `ARCHITECTURE-SPINE.md:125-134`: bảng Consistency Conventions mất separator và phần lớn nhãn concern.
- `ARCHITECTURE-SPINE.md:172-177`: Deferred có ba dòng fragment không còn là deferred item có nghĩa.
- Heading cấp tài liệu ở dòng 20 cũng thiếu dấu `#`; AD-1 và nhiều AD khác không dùng heading nhất quán.

**Why this fails the gate**

Good spine đòi mỗi AD có Rule enforceable và thực sự ngăn divergence đã nêu. Năm AD load-bearing hiện không có contract hoàn chỉnh; reviewer và builder không thể suy ra phần bị mất từ số AD. Bảng convention/Deferred cũng không thể dùng làm boundary contract.

**Action: AUTOFIX trước handoff.** Tái tạo artifact từ nguồn/memlog, bảo đảm từng AD có đúng một `Binds`, `Prevents`, `Rule` hoàn chỉnh; phục hồi bảng và toàn bộ bullet Deferred. Sau đó chạy lại lint và thêm kiểm tra semantic cho body rỗng hoặc quá ngắn.

### R-02 — HIGH — Dictionary precedence và ownership không còn xác định

**Evidence**

- AD-5 Rule tại `ARCHITECTURE-SPINE.md:67` ghi liền `manual book manual global Custom/QualityOverrides auto book auto global base`, không có toán tử thứ tự.
- Source tại `thiet-ke-he-thong-dich-truyen-zh-vi.md:96-126` phân biệt rõ lớp, artifact, owner, scope, quyền ghi và precedence: manual book > manual global > Custom/QualityOverrides > auto book > auto global > Names/LuatNhan/VietPhrase nền/phiên âm.
- Source còn yêu cầu conflict cùng lớp làm build fail và cấm last-line-wins; convention tương ứng trong spine bị vỡ ở dòng 131.

**Impact**

Loader và revision builder có thể triển khai precedence khác nhau, đặc biệt giữa manual-global, Custom/QualityOverrides và auto-book. Đây chính là divergence point một tầng dưới mà spine phải khóa.

**Action: AUTOFIX.** Khôi phục exact precedence dưới dạng thứ tự máy đọc được hoặc danh sách đánh số; chốt conflict-same-layer = build failure; giữ ownership matrix tối thiểu cho human-owned và machine-owned artifact.

### R-03 — HIGH — Contract determinism, atomicity và recovery bị rơi

**Evidence**

- AD-3 và AD-8 bị cắt; AD-11 chỉ khóa cache key/manifest (`ARCHITECTURE-SPINE.md:99-103`).
- Source yêu cầu source revision bất biến, SHA-256 trên bytes, lưu encoding, parse lossless, giữ phần không dịch byte-equivalent và source byte-identical là no-op (`thiet-ke-he-thong-dich-truyen-zh-vi.md:146-151`).
- Source khóa SQLite WAL + `synchronous=FULL`, commit block phải bao gồm output + trace + QA metadata trong cùng transaction, temp → fsync → atomic rename, crash không đổi active revision, resume pin revision cũ và muốn revision mới phải fork run (`thiet-ke-he-thong-dich-truyen-zh-vi.md:470-476`).

**Impact**

Các implementer độc lập có thể bất đồng về transaction boundary, recovery behavior và tiêu chuẩn lossless. AD-11 không đủ ngăn mixed revision, partial commit hoặc export không thể tái lập.

**Action: AUTOFIX.** Phục hồi AD-3/AD-8 hoặc tách một AD transaction/recovery rõ ràng. Rule phải khóa source identity, transaction boundary, activation ordering, atomic materialization và resume/fork semantics; chi tiết tuning có thể ở convention nhưng không được để im lặng.

### R-04 — HIGH — Learning/promotion Rule chưa enforceable và Fast-path assumptions biến mất

**Evidence**

- AD-7 chỉ nói “mỗi bước phải pass hard gates” (`ARCHITECTURE-SPINE.md:75-79`) nhưng không định nghĩa hard gate của book-auto; AD-14 chỉ nêu bốn điều kiện khái quát cho global-auto.
- Source đặt `[ASSUMPTION]` cho ngưỡng book-auto/global-auto và nêu cụ thể occurrence/chapter, target agreement 100%, manual conflict, improvement, structural invariants, affected-block isolation, cross-book evidence và golden corpus (`thiet-ke-he-thong-dich-truyen-zh-vi.md:222-248`).
- Spine không còn bất kỳ tag `[ASSUMPTION]` hoặc Open Question nào dù run dùng Fast path.

**Impact**

Hai learner có thể chọn ngưỡng promotion khác nhau nhưng đều tự nhận là đã “pass hard gates”. Điều này làm thay đổi dictionary revision và output toàn hệ thống. Các quyết định chưa được người dùng xác nhận lại xuất hiện như settled hoặc bị bỏ trống.

**Action: DISCUSS rồi AUTOFIX.** Giữ các gate định tính bắt buộc trong AD; ghi threshold mặc định cấu hình hóa với `[ASSUMPTION]` và fingerprint, hoặc đưa chúng thành Open Questions có blocker status. Không dùng cụm “hard gates” nếu không liệt kê contract tối thiểu.

### R-05 — HIGH — Trace và affected-block correction contract bị rơi

**Evidence**

- AD-2 bị cắt sau `Binds`; AD-11 chỉ yêu cầu manifest hash, không yêu cầu trace coverage.
- Source yêu cầu trace theo source span (`thiet-ke-he-thong-dich-truyen-zh-vi.md:130-140`), review hiển thị segmentation/entry/layer/revision/candidate và các block bị ảnh hưởng, rồi chỉ rerun affected blocks (`thiet-ke-he-thong-dich-truyen-zh-vi.md:289-306`).
- Acceptance criteria yêu cầu mọi output block trace 100% tới literal source hoặc VietPhrase entry/rule và book promotion chỉ đổi affected blocks (`thiet-ke-he-thong-dich-truyen-zh-vi.md:599-607`).

**Impact**

Không có trace coverage và affected-block isolation thì nguyên tắc “sửa từ điển, không sửa output” không audit được; rerun có thể âm thầm đổi block ngoài phạm vi key.

**Action: AUTOFIX.** Phục hồi AD-2 với Rule về canonical correction, trace span 100%, affected-block index/diff isolation và rerun + QA trước atomic export.

### R-06 — HIGH — Brownfield migration/cutover chưa được ratify

**Evidence**

- AD-1 cấm model trên đường dịch mới nhưng spine không nói cách xử lý code/schema/cache lịch sử.
- Source khóa rõ phần giữ lại/bỏ đi và migration: bỏ Hachimi/Qwen/router/model flags, tăng `SCHEMA_VERSION`, giữ source/run/block và route cũ read-only, thêm revision/evidence/promotion/regression tables, invalidate cache chứa model/prompt fingerprint, không drop lịch sử tự động (`thiet-ke-he-thong-dich-truyen-zh-vi.md:525-559`).
- Structural seed tại `ARCHITECTURE-SPINE.md:136-146` đưa layout mong muốn nhưng không chỉ ra boundary nào ratify code hiện có và boundary nào là migration.

**Impact**

Đây là brownfield cutover. Các implementer có thể xóa lịch sử, tái dùng cache không tương thích, hoặc chỉ vô hiệu hóa model flags mà vẫn giữ dependency/process runtime. Good-spine checklist yêu cầu ratify, không contradict hoặc bỏ qua brownfield reality.

**Action: AUTOFIX.** Thêm một AD migration/cutover: runtime mới chỉ VIETPHRASE; history cũ read-only; schema migration non-destructive; cache model-era invalid; model dependencies/process/config bị loại khỏi runtime. Không cần chép milestone, chỉ khóa invariants.

### R-07 — HIGH — QA/regression boundary không đủ để bảo vệ promotion và export

**Evidence**

- AD-10 bị cắt (`ARCHITECTURE-SPINE.md:93-97`); capability map chỉ trỏ chung tới `quality` và AD-10/AD-14.
- Source yêu cầu QA pass-or-block với completeness/order/structural spans/placeholders/CJK/repetition/entity consistency/hash (`thiet-ke-he-thong-dich-truyen-zh-vi.md:274-285`).
- Source phân ba tầng dictionary unit, golden `raw_china/expect*.txt`, metamorphic; có các invariants reorder-auto, whole-book/chapter equivalence, resume=clean-run, rollback hash restore (`thiet-ke-he-thong-dich-truyen-zh-vi.md:478-505`).

**Impact**

AD-14 chỉ bảo vệ global promotion; book promotion và export không có minimum quality gate enforceable. Hai implementation có thể pass/reject khác nhau hoặc bỏ regression pipeline đã được yêu cầu.

**Action: AUTOFIX.** Phục hồi AD-10 và chốt ba gate tối thiểu: structural QA cho mọi export; affected-block regression cho mọi promotion; golden suite bắt buộc cho global promotion. Ghi `raw_china/expect*.txt` là acceptance substrate, không phải metric chất lượng ngôn ngữ.

### R-08 — MEDIUM — Operational/environmental envelope mới được phủ một phần

**Evidence**

- AD-13 khóa writer scopes nhưng không khóa journal/durability/commit behavior; các phần đó chỉ có trong source và đã được nêu ở R-03.
- Mục tiêu offline của source không được phát biểu như system boundary; AD-1 chỉ cấm network model call, không cấm learner/revision path phụ thuộc external service.
- Service/API/worker queue đáng lẽ deferred, nhưng Deferred hiện bị cắt (`ARCHITECTURE-SPINE.md:172-177`).

**Impact**

Một learner có thể thêm network dependency ngoài model call hoặc giả định multi-host coordination dù mục tiêu là CLI offline/single-machine. Đây là environmental divergence ở altitude initiative.

**Action: AUTOFIX.** Chốt v1 là offline CLI/single-machine filesystem + SQLite; external service/network dependency không nằm trong execution path. Khôi phục defer của web/API/worker và multi-machine sync.

## Coverage against good-spine checklist

| Checklist item | Result | Notes |
|---|---|---|
| Fixes real divergence points one level below | Fail | Precedence, promotion gates, trace, recovery và migration còn mơ hồ/mất. |
| Misses no structural dimension at its altitude | Fail | Brownfield migration và environmental envelope chưa được khóa. |
| Every AD has Binds/Prevents/Rule | Fail | AD-2/3/4/8/9/10 bị cắt. |
| Every Rule enforceable and prevents divergence | Fail | “pass hard gates” và precedence bị mất toán tử không enforceable. |
| Nothing Deferred permits silent divergence | Fail | Deferred bị fragment; boundary service/multi-machine/context ambiguity không còn đầy đủ. |
| Named tech verified-current | N/A / Pass | Không khóa external technology/version mới. SQLite là existing substrate, không có version claim. |
| Ratifies brownfield reality | Fail | Migration/cutover contract từ source bị bỏ. |
| Operational/environmental envelope addressed | Fail | Có lock intent nhưng durability/offline/deployment scope chưa đủ. |

## Recommended gate decision

Không handoff spine này cho dev. Sửa R-01 trước vì corruption làm các finding khác khó phân biệt giữa “chưa quyết định” và “nội dung bị mất”. Sau khi phục hồi, áp dụng R-02, R-03, R-05, R-06, R-07 và R-08 như clear fixes; chỉ R-04 cần người dùng xác nhận assumptions/ngưỡng hoặc chấp nhận chúng là cấu hình mặc định có fingerprint. Sau đó rerun lint và rubric review độc lập.
