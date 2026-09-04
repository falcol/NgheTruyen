# Rubric Re-check — Architecture Spine zhvi VietPhrase-only

## Verdict

**FAIL — còn 2 residual issue trước handoff.** Bản spine hiện tại đã sửa được corruption và phần lớn lỗi kiến trúc trước đó, nhưng brownfield migration vẫn chưa thành invariant và QA/promotion contract cho book-auto vẫn chưa đủ enforceable.

## Deterministic verification

- `18` AD headings.
- `18` dòng `Binds`.
- `18` dòng `Prevents`.
- `18` dòng `Rule`.
- `2` Fast-path assumptions.
- `lint_spine.py`: `ok: true`, `total_findings: 0`.

Việc re-check dựa trên count, line length/nội dung Rule thực tế và memlog/patch history; không dùng phần hiển thị `sed` bị nén để kết luận nội dung mất.

## Các nhóm đã đóng

- **Precedence/ownership: PASS.** AD-5 khóa đúng thứ tự `manual book > manual global > Custom/QualityOverrides > auto book > auto global > base`, đồng thời làm rõ span-length thắng trước precedence. AD-8 và conventions tách rõ human-owned files, book SQLite, global registry SQLite và projections có thể dựng lại.
- **Revision identity/atomicity: PASS.** AD-3 khóa content-addressed immutable bundle; AD-13 khóa registry writer/CAS; AD-15 khóa publish order `temp → fsync → atomic rename → DB ready/CAS → projection`; AD-16 khóa active-pointer cardinality và pin global revision vào book revision.
- **Fast-path assumptions: PASS có điều kiện.** Các numerical thresholds được hạ đúng thành configurable defaults, không giả làm invariant; golden inputs phải có approved manifest. Điều kiện còn thiếu của book-auto được ghi riêng ở residual R-02.
- **Global QA/promotion: PASS.** AD-14 fail-closed khi thiếu approved golden manifest, cross-book evidence, target agreement hoặc affected-block isolation; raw `expect*` không tự được coi là golden.

## Residual issues

### RR-01 — HIGH — Brownfield migration/cutover chưa được khóa trong spine

**Evidence**

- Spine chỉ có AD-1 cấm model inference/network/local patch/post-edit trên đường sinh target mới.
- Không có Rule nào khóa `SCHEMA_VERSION`, migration non-destructive, history/route cũ read-only, invalidation cache model-era, hoặc loại model dependency/process/config khỏi runtime.
- Memlog vẫn ghi rõ gap: runtime hiện tại còn hybrid và migration M1 phải lập VietPhrase-only baseline trước cutover claim.
- Source yêu cầu giữ source/run/block history, route cũ read-only, không drop history, thêm revision/evidence/promotion/regression tables và không tái dùng cache có prompt/model fingerprint.

**Why this still fails good-spine gate**

Đây là brownfield redesign, không phải greenfield. Hai implementer có thể cùng tuân AD-1 nhưng một bên drop lịch sử/cache, bên kia migrate bảo toàn; hoặc vẫn ship model dependencies dù không gọi chúng. Đây là divergence load-bearing chưa được Deferred hay AD khóa.

**Required fix:** thêm một AD cutover/migration ngắn: runtime mới chỉ `VIETPHRASE`; migration schema non-destructive; history model-era chỉ đọc; cache model/prompt-era invalid; model workers/dependencies/config bị loại khỏi runtime. Nếu migration thật sự không nằm trong scope, phải ghi rõ Deferred và điều kiện cutover — hiện tại source đặt nó trong scope.

### RR-02 — HIGH — Book-auto hard gate và trace/QA coverage tối thiểu còn mơ hồ

**Evidence**

- AD-7 nói mỗi transition phải pass “hard gates” nhưng không liệt kê hard gate tối thiểu cho `candidate → book_auto`.
- AD-14 chỉ enforce affected-block isolation và regression evidence cho global promotion.
- AD-2 yêu cầu rerun affected blocks nhưng không cấm book promotion làm đổi block ngoài affected set.
- AD-9/AD-18 yêu cầu trace cho matching/preprocessing/rendering, nhưng không khóa acceptance requirement rằng **100% output span** phải trace được tới literal source hoặc VietPhrase entry/rule.
- AD-10 khóa QA pass-or-block và không mutate output, nhưng không chỉ rõ structural QA là gate bắt buộc cho mọi export và mọi book promotion.

**Why this still fails good-spine gate**

Hai learner có thể dùng book-auto gate khác nhau, hoặc promote entry làm đổi ngoài affected set, mà vẫn tuyên bố tuân AD-7. Thiếu trace-coverage invariant cũng làm affected-block calculation và audit correction không chứng minh được.

**Required fix:** amend AD-7/AD-10 hoặc thêm một AD ngắn khóa minimum gates cho book-auto: target deterministic, không manual conflict, structural QA pass, affected-block isolation pass; mọi exported output span có trace tới source literal hoặc entry/rule. Numerical frequency/PMI/chapter thresholds vẫn giữ `[ASSUMPTION]`/config fingerprint như hiện tại.

## Gate decision

Không cần làm lại paradigm, precedence, registry hay publish protocol. Chỉ cần đóng RR-01 và RR-02, rerun deterministic lint/count rồi thực hiện một rubric re-check cuối.
