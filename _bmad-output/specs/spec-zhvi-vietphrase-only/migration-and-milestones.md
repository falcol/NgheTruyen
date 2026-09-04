# Migration & milestones — zhvi VietPhrase-only

Cutover brownfield từ thiết kế 2.0 (model-era) sang 3.0 (VietPhrase-only). Đọc cùng SPEC.md.

## Giữ lại từ 2.0

- CLI Typer và project workflow;
- snapshot/import lossless;
- document parser và stable block identity;
- trie, longest-match, pattern rules và trace;
- dictionary fingerprint/cache;
- SQLite state, checkpoint/resume;
- structural QA, chapter audit;
- atomic export và manifest;
- manual global/book glossary.

## Loại bỏ

- `engines/hachimi_worker.py`;
- `engines/ollama_qwen.py`;
- router bốn route và `execute_route`;
- model download/cache/digest;
- prompt schema và structured model output;
- model candidate acceptability gate;
- masked-term round-trip phục vụ model;
- CLI/config `use_hachimi`, `use_qwen`, `qwen_*`, `hachimi_*`;
- route metrics `HACHIMI_CANDIDATE`, `LOCAL_PATCH`, `QWEN_POSTEDIT`;
- profile chỉ khác nhau ở việc gọi model.

## Thay đổi schema

- Tăng `SCHEMA_VERSION`.
- Migration giữ source revision, run, block lịch sử; route cũ giữ read-only để audit; run mới chỉ ghi `VIETPHRASE`.
- Thêm revision/evidence/promotion/regression tables.
- Cache cũ có prompt/model/router fingerprint không được tái dùng.
- Không drop lịch sử trong migration tự động.
- Root test collection phải khai báo đủ dependency hiện đang import, thay vì dựa vào package cài sẵn ngoài `zhvi`; Milestone 1 tạo test baseline VietPhrase-only trước khi tuyên bố cutover.

## Milestones

1. **VietPhrase-only cutover**: bỏ model flags + model initialization; rút pipeline về một đường VietPhrase; đổi fingerprint/version; cập nhật doctor, status, README, tests; chứng minh output deterministic + resume parity.
2. **Revision và auto layer**: thêm `AutoVietPhrase.txt` + `glossary.auto.tsv`; dictionary revision builder; provenance/trace → affected-block index; diff + rollback.
3. **Book learner**: n-gram discovery; proper-name heuristic; deterministic target composition; evidence evaluator; book-auto hard gates; regression trước promotion.
4. **Global learner**: global evidence store; cross-book agreement; golden suite gate; atomic global promotion/revocation; báo cáo drift theo revision.

## Acceptance criteria (thiết kế 3.0 §17)

1. Không còn runtime dependency, network call hoặc process nào dành cho model dịch/edit.
2. Mọi block output có trace 100% tới literal source hoặc VietPhrase entry/rule.
3. Cùng fingerprint tạo cùng output SHA-256.
4. Auto learner không bao giờ ghi vào file human-owned.
5. Dịch không quan sát promotion giữa run.
6. Candidate không có deterministic target luôn ở `unresolved`.
7. Book promotion rollback được và chỉ làm đổi affected blocks.
8. Global promotion không chạy nếu thiếu cross-book evidence hoặc golden manifest đã duyệt.
9. QA không sửa output; fail phải dẫn tới dictionary fix và rerun.
10. Pipeline chạy và xuất diff report với toàn bộ candidate reference `raw_china/expect*.txt` + `raw_china/excpect*.txt`; chỉ case đã duyệt mới quyết định pass/fail global gate.
