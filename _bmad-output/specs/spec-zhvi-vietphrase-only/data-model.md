# Data model — zhvi VietPhrase-only

Sở hữu dữ liệu, entity, bảng, layout, protocol publish. Đọc cùng SPEC.md.

## Phân quyền nguồn chân lý

- Base/manual files: do người sở hữu (human-owned).
- Book SQLite (`.zhvi/state.sqlite3`): observation, candidate, evidence, promotion theo truyện.
- Registry SQLite (`<dict_dir>/.zhvi-registry/state.sqlite3`): evidence, entry, active revision toàn cục.
- Content-addressed revision bundle: input bất biến mà run thực sự nạp.
- `AutoVietPhrase.txt`, `glossary.auto.tsv`, trie cache: projection dựng lại được, không phải artifact run pin.

Book project gửi evidence bất biến kèm `book_id`, source revision, occurrence identity vào global registry; không mutate global candidate/revision trực tiếp. `book_id` tạo một lần khi `zhvi init`. Copy project giữ ID nên không được tính là truyện độc lập.

## Bảng SQLite

`source_revisions`, `dictionary_revisions`, `entry_versions`, `observations`, `term_candidates`, `candidate_evidence`, `promotion_events`, `regression_suites`, `regression_results`, `runs`, `blocks`, `trace_spans`, `block_cache`, `feedback_events`, `active_revisions(scope_type, scope_id, revision_id)` với unique key `(scope_type, scope_id)`.

Mọi mutation candidate/entry/revision ghi event append-only gồm `before`, `after`, actor, timestamp, provenance.

- Entry identity = hash của canonical tuple `(scope, normalized_source, kind)`.
- Entry version identity = entry identity + target + policy + provenance hash.
- `dictionary_revision_id = SHA-256(canonical_manifest)` với canonical manifest gồm hash từng layer + loader/renderer version + precedence policy.

## Trạng thái revision

```text
building → validating → ready → active
                    ↘ rejected
active → superseded
active → revoked
```

- `ready` = bundle tồn tại, fsync, hash-pass, có row đã commit.
- Mỗi scope đúng một active pointer; activation dùng compare-and-swap; stale writer phải build/evaluate lại trên active mới.
- Bundle superseded/revoked giữ để reproduce run lịch sử; run mới chỉ pin active revision.
- Rollback không sửa revision cũ — tạo revision mới có tập entry tương đương revision an toàn đã chọn.

## Publish protocol (10 bước)

1. Đọc immutable base files.
2. Đọc auto entry đã promote từ book/global state store.
3. Đọc manual layers.
4. Validate format, duplicate, conflict (auto conflict cùng scope/lớp làm build fail).
5. Tạo canonical manifest (hash từng layer, loader/renderer version, precedence policy).
6. Tính `dictionary_revision_id`.
7. Materialize merged entries + pattern index + trace metadata vào bundle tạm.
8. Chạy smoke corpus, xác minh lại mọi hash.
9. Fsync bundle rồi atomic rename thành `revisions/<dictionary_revision_id>/`.
10. Một SQLite transaction: insert revision `ready` + CAS active pointer; sau commit mới cập nhật projection (`AutoVietPhrase.txt`) — crash ở bước này được reconciler dựng lại từ active pointer.

Bundle đã rename nhưng chưa ghi DB là orphan vô hại, garbage-collect được. DB commit không bao giờ trỏ bundle dở dang. Translation không đọc projection mutable.

## Layout

```text
book-project/
  zhvi.toml                 # chứa stable book_id
  glossary.manual.tsv
  glossary.auto.tsv
  dist/
    book.vi.txt
    book.vi.manifest.json
  .zhvi/
    state.sqlite3
    sources/
    revisions/<dictionary_revision_id>/
      manifest.json
      entries.tsv
      patterns.jsonl
      dictionary.bin
    runs/
    cache/
    reports/
    locks/

crawler/vietphrase/dicts/           # dictionary root
  ChinesePhienAmWords.txt
  VietPhrase_1.txt … VietPhrase_3.txt
  LuatNhan.txt
  Names.txt
  AutoVietPhrase.txt               # machine-owned, generated
  QualityOverrides.txt
  Custom.txt                       # human-owned
  trad-simp.txt
  .zhvi-registry/
    state.sqlite3
    revisions/<sha256>/
    locks/registry.lock
```

## Layer & precedence

| Lớp | Artifact | Chủ sở hữu | Phạm vi | Máy ghi? |
|---|---|---|---|---|
| Phiên âm | `ChinesePhienAmWords.txt` | dữ liệu nền | toàn cục | không |
| VietPhrase nền | `VietPhrase_1..3.txt` | dữ liệu nền | toàn cục | không |
| Luật nhân | `LuatNhan.txt` | dữ liệu nền | toàn cục | không |
| Tên nền | `Names.txt` | dữ liệu nền | toàn cục | không |
| Auto toàn cục | `AutoVietPhrase.txt` | learner (qua registry) | toàn cục | có |
| Auto theo truyện | `glossary.auto.tsv` | learner (qua revision builder) | một truyện | có |
| Quality override | `QualityOverrides.txt` | người dùng | toàn cục | không |
| Custom | `Custom.txt` | người dùng | toàn cục | không |
| Glossary thủ công toàn cục | `~/.config/zhvi/glossary.manual.tsv` | người dùng | toàn cục | không |
| Glossary thủ công theo truyện | `glossary.manual.tsv` | người dùng | một truyện | không |

Precedence cùng normalized key/span: `manual book > manual global > Custom/QualityOverrides > auto book > auto global > base`. Matcher vẫn chọn span dài nhất trước — manual entry ngắn không tự bẻ base phrase dài hơn; muốn override segmentation phải thêm manual entry cho toàn bộ key dài.

## Concurrency, recovery, atomicity

- Một project một writer lock; nhiều reader dùng revision `ready`.
- `dict_dir` resolve symlink/realpath trước khi xác định registry; mỗi resolved root đúng một registry + một writer lock.
- Chỉ global registry được promote global entry hoặc materialize `AutoVietPhrase.txt`.
- Không giữ global lock trong discovery; chỉ lock khi build/activate revision.
- SQLite WAL + `synchronous=FULL` cho mutation quan trọng.
- Block chỉ `committed` khi output + trace + QA metadata cùng transaction.
- Bundle và output: temp → fsync file → fsync directory → atomic rename.
- Active pointer CAS sau khi immutable bundle hoàn chỉnh; crash trước DB commit để orphan, crash sau DB commit chỉ có thể để projection cũ.
- Startup reconciler kiểm active pointer, bundle hash, projection; projection cũ dựng lại; bundle thiếu/hash sai là fatal corruption.
- Crash khi `building`/`validating` không đổi active revision.
- Resume pin revision cũ; muốn revision mới phải fork run.

## ID conventions

- SHA-256 cho content/revision; UUID cho event/run; ID đã phát hành không tái sử dụng.
- Entry format `source=target`, UTF-8, NFC; source giản thể để index, source gốc giữ trong provenance.
- File `.manual.*` = human-owned; `.auto.*` + `AutoVietPhrase.txt` = machine-owned.
