# Adversarial Seam Re-check — zhvi VietPhrase-only

**Verdict: PASS — năm blocker đã nêu đều được đóng ở mức architecture spine.**

Đối chiếu patch history trong `.memlog.md` với AD-3, AD-8, AD-13 và AD-15..AD-17 cho thấy:

- Split-brain global state đã đóng: `realpath(dict_dir)/.zhvi-registry/` là owner duy nhất của global state/projection; book DB không sở hữu global promotion; writer dùng expected-revision CAS và stale writer phải evaluate/build lại.
- Revision mutability đã đóng: run pin content-addressed bundle; revision ID hash canonical manifest của toàn bộ ordered layer cùng loader/renderer/precedence version; run không đọc source file hoặc projection sau khi pin.
- DB/filesystem crash windows đã đóng: bundle chỉ publish sau fsync + atomic rename; DB insert `ready` và active-pointer CAS diễn ra sau khi bundle hoàn chỉnh; projection nằm ngoài read path, orphan được GC và projection lệch được reconcile.
- `ready`/`active` ambiguity đã đóng: active pointer có cardinality theo scope; run mới chỉ pin active book composite revision, còn run lịch sử được phép đọc bundle superseded/revoked để reproduce.
- Book/global composition đã đóng: book revision pin explicit global revision ID cùng hash book-auto/manual; global activation không thay đổi ngầm active book revision.

**Residual issues trong phạm vi năm blocker: không có.**

Các concern khác trong review ban đầu — canonical entry grammar, cache/config digest, affected-block semantics, run-level QA state và stable tie-break identity — nằm ngoài năm blocker được yêu cầu re-check và không làm đổi verdict này.
