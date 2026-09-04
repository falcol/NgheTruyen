# Reality Review — zhvi VietPhrase-only

## Verdict

**CONDITIONAL PASS — hướng kiến trúc phù hợp mục tiêu VietPhrase-only, nhưng chưa thể gọi là verified-current.** Spine mô tả target architecture hợp lý và đã đặt đúng các boundary revision/run/global registry. Trước handoff cần sửa một xung đột precedence có thể làm manual correction không hiệu lực, giới hạn conflict validation để không reject corpus nền hiện hữu, và coi golden/global auto-promotion là capability chưa có bằng chứng.

## Evidence đã kiểm tra

- Code graph: `pipeline._translate_locked`, `vietphrase.loader.load_dictionary`, `vietphrase.lattice.greedy_path`/`vp_plan`, `fingerprint.build_run_fingerprint`, `state.State` và CLI.
- Corpus hiện tại: khoảng 1.396 triệu dòng dictionary; riêng nhóm base-multi có 45.826 key trùng giữa `VietPhrase_*`, `LuatNhan` và `Names` (nhiều overlap là chủ ý, ví dụ cùng key ở VietPhrase và Names).
- Test VietPhrase/state chọn lọc: **40 passed, 2 skipped**.
- Full suite hiện tại **không collect được** vì `ollama_qwen.py` import `requests` nhưng `requests` không nằm trong dependency của `zhvi/pyproject.toml`.
- Chạy baseline hiện tại rồi compare: chap1 similarity `0.9532` nhưng `102/105` dòng đổi; chap2 similarity `0.9221` và `69/69` dòng đổi. Hai run vẫn route `LOCAL_PATCH` (3 và 4 block), nên đây chưa phải oracle VietPhrase-only.

## Findings

### HIGH — AD-5 “manual luôn thắng” xung đột với AD-9 longest-match

`greedy_path` hiện chọn độ dài match lớn nhất trước, rồi mới xét literal/pattern và precedence trong các match cùng độ dài. Vì vậy manual entry ngắn hơn một base phrase đang phủ cùng span sẽ không được dùng. Test hiện tại chỉ chứng minh book manual thắng global khi **cùng key/cùng độ dài**. Điều này phá hợp đồng correction của AD-2/AD-5: người dùng sửa một term nhưng output có thể không đổi.

**Cần sửa spine:** định nghĩa thứ tự quyết định rõ ràng cho overlap khác độ dài. Khuyến nghị manual “locked span” thắng mọi auto/base overlap; longest-match chỉ áp dụng bên trong cùng policy/layer sau khi manual span đã được khóa. Thêm regression cho `manual AB` đối đầu `base ABC`.

### HIGH — “Conflict cùng layer làm build fail” không tương thích corpus nền

Loader hiện cố ý cho phép nhiều target trên cùng key và phân xử bằng `(layer, trust, load_index)`; `VietPhrase_1..3`, `LuatNhan`, `Names` cùng quy về `BASE_MULTI` nhưng corpus có hàng chục nghìn overlap. Nếu revision builder áp dụng literal rule “cùng layer khác target => fail” cho toàn bundle, revision đầu tiên sẽ không build được.

**Cần sửa spine:** hard-fail conflict chỉ cho layer auto/manual do hệ thống sở hữu, hoặc tách base source thành các sublayer có precedence đã ratify. Base legacy phải được import với policy tương thích hiện tại và xuất report ambiguity, không biến toàn bộ overlap lịch sử thành build error.

### HIGH — Golden gate đúng về nguyên tắc nhưng chưa có golden suite đáng tin

Graph không tìm thấy regression runner dùng `raw_china/expect*.txt`; README đánh dấu golden corpus là M4 chưa làm. `expect.txt` từng được dùng làm few-shot cho pipeline model cũ, file chương 2 còn tên `excpect2.txt`, và baseline compare cho thấy gần như mọi dòng đều khác. Vì vậy các file này chưa chứng minh correctness cho VietPhrase-only và không nên dùng làm auto-promotion oracle chỉ vì tồn tại.

**Disposition:** giữ AD-14 fail-closed, nhưng đánh dấu global auto-promotion là disabled-until-curated. Golden case cần source hash, expected hash, approval/provenance và policy diff rõ; benchmark đầu tiên phải tạo baseline VietPhrase-only đã được người duyệt.

### MEDIUM — QA/preprocessing boundary chưa ratify hành vi brownfield

Code hiện tại gọi `sanitize_source` trước `vp_plan`, còn `collapse_repetitions` thay đổi chuỗi edge trong VietPhrase core. AD-10 nói QA chỉ pass/chặn, trong khi các transform này đang làm đổi output. Nếu chúng bị bỏ nhầm khi loại “edit stage”, output và cache parity sẽ thay đổi; nếu vẫn để dưới QA, invariant “QA không mutate” trở nên sai nghĩa.

**Cần sửa spine:** gọi chúng là deterministic preprocessor/renderer rules (không phải QA/post-edit), pin version trong revision fingerprint, và bắt buộc trace source span cho mọi phần bị drop/collapse. QA sau render vẫn pure pass/block.

### MEDIUM — Brownfield cutover chưa có baseline xanh ở cấp package

Target loại Qwen/Hachimi sẽ giải quyết dependency lỗi thời, nhưng hiện tại full suite không collect vì import model code kéo `requests` không khai báo. Pipeline thực chạy mặc định cũng còn router/`LOCAL_PATCH`, model fingerprint và schema cũ. Không thể dựa vào suite hiện hữu để tuyên bố migration giữ nguyên hành vi.

**Disposition:** tiêu chí cutover đầu tiên phải là package install sạch + full test collect/pass sau khi xóa model imports/routes; sau đó thêm e2e khẳng định mọi block có engine/route duy nhất `VIETPHRASE` và không còn model/prompt fields trong fingerprint/manifest mới.

## Kết luận gate

Không có bằng chứng phản đối paradigm LEARN → immutable revision → TRANSLATE. Hai finding đầu là contract bug cần sửa trước khi chia story; finding golden là blocker có chủ ý cho **global auto-promotion**, không phải blocker cho book-level candidate/translation.
