# Reality Re-check — zhvi VietPhrase-only

## Verdict

**PASS** — cả năm finding brownfield/reality trước đã được xử lý đủ để handoff. Không còn residual issue mức HIGH. Hai điểm nhỏ dưới đây chỉ cần cleanup để tài liệu tự nhất quán.

## Finding re-check

1. **Manual vs longest-match — RESOLVED.** AD-5 giờ giới hạn manual precedence ở cùng normalized key/span; AD-9 chốt span dài nhất trước. Full design nói rõ muốn bẻ segmentation phải thêm manual entry cho toàn key dài. Đây là contract nhất quán với `greedy_path` hiện tại.
2. **Legacy same-layer conflicts — RESOLVED.** Spine chỉ hard-fail auto conflict cùng scope/layer; base/human legacy giữ source/file/load order đã freeze và phát diagnostic. Điều này tương thích corpus nền có nhiều overlap và loader hiện tại.
3. **Unapproved expect files — RESOLVED.** AD-14 yêu cầu approved golden manifest và nói rõ tên `expect*` không tự tạo golden. Full design định nghĩa hash, provenance, approval; global auto-promotion bị khóa khi chưa có manifest.
4. **Preprocessing/QA boundary — RESOLVED.** AD-18 tách deterministic preprocessor/renderer khỏi read-only QA, yêu cầu version trong fingerprint và source-offset/target-span trace. Structural seed đã có `preprocessing.py`.
5. **Brownfield migration status — RESOLVED.** Full design tuyên bố rõ đây là target architecture, ghi nhận router/`LOCAL_PATCH`/model config vẫn tồn tại và yêu cầu baseline/package test xanh trước khi tuyên bố cutover.

## Residual issues

### LOW — Dictionary unit-test bullet còn viết quá rộng

Full design phần Dictionary unit tests vẫn ghi “không duplicate/conflict cùng lớp”, trong khi policy mới cho phép conflict legacy base/human và chỉ hard-fail auto conflict. Nên đổi bullet thành “không auto conflict cùng scope/layer; legacy conflict phát diagnostic theo precedence đã freeze”.

### LOW — Glob `expect*.txt` bỏ sót file chap2 hiện có

Repo đang có `raw_china/excpect2.txt` (sai chính tả), nên các câu “toàn bộ `raw_china/expect*.txt`” không bao phủ case chap2. Rename file hoặc để golden candidate importer dùng manifest/path tường minh; không nên dựa vào glob này làm tuyên bố coverage.

## Gate conclusion

Hai residual trên không làm yếu architecture invariants và không chặn handoff. Sau cleanup câu chữ/dữ liệu, reality lens không còn objection.
