---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
inputDocuments:
  - ../specs/spec-zhvi-vietphrase-only/SPEC.md
  - ../specs/spec-zhvi-vietphrase-only/pipeline-contract.md
  - ../specs/spec-zhvi-vietphrase-only/data-model.md
  - ../specs/spec-zhvi-vietphrase-only/migration-and-milestones.md
  - architecture/architecture-NgheTruyen-2026-09-03/ARCHITECTURE-SPINE.md
---

# NgheTruyen (zhvi) - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the zhvi VietPhrase-only cutover, decomposing the requirements from the SPEC (canonical contract) and Architecture Spine into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Dịch TXT tiếng Trung sang tiếng Việt hoàn toàn offline bằng duy nhất engine VietPhrase; cùng source revision + dictionary revision + config tạo cùng output SHA-256.
FR2: Vòng đời dictionary revision: build immutable content-addressed bundle, validate, activate qua CAS, diff, rollback; mỗi run pin đúng một revision; resume/reproduce đọc bundle đã pin.
FR3: Book learning: discovery tạo observation; candidate builder chỉ dùng 6 nguồn target xác định; evidence evaluator; book-auto promotion qua hard gates; chỉ ghi `glossary.auto.tsv` (projection) và chỉ ảnh hưởng truyện đó.
FR4: Global learning: registry tại `<dict_dir>/.zhvi-registry/` sở hữu cross-book evidence; dedupe theo `(book_id, source_revision_id, candidate_id, occurrence_span)`; global promotion fail-closed — thiếu approved golden manifest hoặc cross-book evidence thì dừng ở `global_candidate`.
FR5: Correction policy: sửa entry/rule trong manual glossary → build revision mới → xác định affected blocks bằng trace/source index → dịch lại đúng các block đó → QA → export lại atomic; không lưu text đã sửa làm nguồn chân lý thứ hai.
FR6: Trace/explain: 100% output span truy về source literal hoặc versioned VietPhrase entry/rule/transformation; review hiển thị segmentation, entry/layer/revision, candidate liên quan, affected blocks.
FR7: QA structural chỉ pass hoặc chặn export, không mutate; fail chuyển run sang `needs_dictionary_fix`; run report metric riêng lẻ (coverage, unknown, CJK residue, fragmentation, regression pass/fail, output SHA-256, chars/s).
FR8: Golden corpus tooling: manifest tại `zhvi/tests/golden/manifest.json` gồm source hash, expected hash, phạm vi assertion, provenance, dấu duyệt; import `raw_china/expect*.txt` + `excpect*.txt` làm candidate; xuất diff report; chỉ case `approved` tham gia promotion gate.
FR9: Migration brownfield additive: giữ source revision/run/block/route lịch sử read-only; invalidate mọi cache chứa prompt/model/router fingerprint; runtime xóa model workers/dependencies/config/flags; run mới chỉ ghi route `VIETPHRASE`.
FR10: CLI contract đầy đủ không model flags: init (stable book_id), import, learn (--global), translate (--no-learn), terms list/accept/reject/revoke, dict diff/rollback, explain, status, export, doctor; happy path `zhvi translate FILE -o OUT` chạy snapshot → discover → book-auto learn → freeze → translate → QA → export → report.
FR11: Regression 3 lớp không model: dictionary unit tests (parse/precedence/alias/pattern/deterministic), golden corpus gate, metamorphic invariants (add-entry no-op, reorder no-op, whole == per-chapter, resume == clean, rollback restore, trad/simp alias).
FR12: Đường dịch deterministic: phồn→giản để match giữ source gốc trong trace; trie lookup; longest-match; precedence theo lớp; literal thắng pattern; tie-break theo `entry_id`.
FR13: Preprocessing view version hóa: junk stripping chỉ xóa span kèm source offsets + reason code; repetition collapse ở renderer trên ranh giới target span; cả hai có trace và tham gia fingerprint.
FR14: Layer ownership & precedence được enforce trong loader/builder: `manual book > manual global > Custom/QualityOverrides > auto book > auto global > base`; máy không bao giờ ghi file human-owned (`Custom.txt`, `QualityOverrides.txt`, `VietPhrase_*.txt`, `glossary.manual.tsv`, `.manual.*`).
FR15: `zhvi terms` management: list (candidate/evidence/trạng thái), accept (tạo manual entry), reject (audit event), revoke (thu hồi auto entry + build revision mới); mọi mutation ghi event append-only.
FR16: Config schema: style/output_policy/encoding/dict_dir/global_glossary/pattern_rules/collapse_repetitions/qa_strip_junk + [learning] + [runtime]; mọi field ảnh hưởng dictionary/segmentation/render nằm trong fingerprint.
FR17: Concurrency/recovery: một writer lock mỗi scope (project, registry qua realpath); WAL + `synchronous=FULL`; block committed chỉ khi output+trace+QA cùng transaction; startup reconciler; resume pin revision cũ, revision mới phải fork run.
FR18: Chất lượng run report: dictionary_revision_id, coverage theo ký tự/span, unknown spans, single-char ratio, fragmentation, candidate count theo trạng thái, entry auto được dùng, affected blocks, regression pass/fail, output SHA-256, elapsed + chars/s.

### NonFunctional Requirements

NFR1: Determinism — cùng fingerprint tạo cùng output SHA-256, không phụ thuộc iteration order/hash map.
NFR2: Hoàn toàn offline — không runtime dependency, network call hay process nào dành cho model dịch/edit.
NFR3: File human-owned không bao giờ bị tiến trình học tự động ghi.
NFR4: Atomicity — bundle/output dùng temp → fsync file → fsync dir → atomic rename; không yêu cầu transaction xuyên SQLite/filesystem; DB không bao giờ trỏ bundle dở dang.
NFR5: Resumability — Ctrl-C giữ block đã commit; resume == clean run.
NFR6: Một active pointer mỗi scope; activation CAS; stale writer evaluate lại.
NFR7: Mọi mutation candidate/entry/revision ghi event append-only có before/after/actor/timestamp/provenance.
NFR8: Không dùng quality score tổng hợp; metric riêng lẻ.
NFR9: Migration tự động không drop lịch sử.
NFR10: CLI foreground là sản phẩm chính; hiệu năng đo bằng chars/s trong report (không có ngưỡng cứng).

### Additional Requirements

- Brownfield: giữ CLI Typer, snapshot/import lossless, document parser + stable block identity, trie/longest-match/pattern rules/trace, dictionary fingerprint/cache, SQLite state + checkpoint/resume, structural QA, chapter audit, atomic export + manifest, manual glossaries.
- Loại bỏ: `engines/hachimi_worker.py`, `engines/ollama_qwen.py`, router bốn route + `execute_route`, model download/cache/digest, prompt schema + structured model output, model acceptability gate, masked-term round-trip, CLI/config `use_hachimi`/`use_qwen`/`qwen_*`/`hachimi_*`, route metrics `HACHIMI_CANDIDATE`/`LOCAL_PATCH`/`QWEN_POSTEDIT`, profile chỉ khác việc gọi model.
- Schema: tăng `SCHEMA_VERSION`; thêm bảng revision/evidence/promotion/regression; route cũ read-only.
- Root test collection phải khai báo đủ dependency đang import, không dựa package cài sẵn ngoài `zhvi`; Milestone 1 tạo test baseline VietPhrase-only trước khi tuyên bố cutover.
- Structural seed: `learning/`, `revisions/`, `vietphrase/`, `quality/`, `preprocessing.py`, `state.py`, `pipeline.py`.
- Ràng buộc orchestrator: không cho hai agent cùng sửa `pipeline.py`, `state.py`, `config.py`, hay cùng một test file song song.

### UX Design Requirements

N/A — CLI product, không có UX design contract.

### FR Coverage Map

FR1: Epic 1 — translate path VietPhrase-only deterministic
FR2: Epic 2 — revision bundle lifecycle + run pinning
FR3: Epic 3 — book learner pipeline
FR4: Epic 4 — global registry + fail-closed promotion
FR5: Epic 2 — correction → revision → affected-block rerun
FR6: Epic 3 — trace/explain/review display
FR7: Epic 5 — QA gates + run report
FR8: Epic 5 — golden manifest tooling + diff report
FR9: Epic 1 — additive migration cutover
FR10: Epic 1 — CLI contract (phần learning commands: Epic 3/4)
FR11: Epic 5 — regression 3 lớp
FR12: Epic 1 — deterministic matching path
FR13: Epic 2 — versioned preprocessing view
FR14: Epic 2 — loader/builder ownership enforcement (ràng buộc ghi: Epic 3/4 verify)
FR15: Epic 3 — terms CLI + audit events
FR16: Epic 1 — config schema + fingerprint membership
FR17: Epic 2 — concurrency/recovery protocol
FR18: Epic 5 — run report metrics

## Epic List

### Epic 1: VietPhrase-Only Cutover
Người dùng dịch TXT bằng một đường VietPhrase duy nhất, offline, deterministic; mọi dấu vết model-era biến mất khỏi runtime nhưng lịch sử audit còn nguyên.
**FRs covered:** FR1, FR9, FR10 (core), FR12, FR16

### Epic 2: Immutable Dictionary Revisions
Người dùng có vòng đời từ điển bất biến: revision bundle content-addressed, activate CAS, diff, rollback; run pin một revision; sửa chất lượng = sửa entry rồi dịch lại đúng block bị ảnh hưởng.
**FRs covered:** FR2, FR5, FR13, FR14, FR17

### Epic 3: Book Learner
Trong phạm vi một truyện, hệ thống tự phát hiện cụm yếu, tạo candidate xác định, tính evidence và promote book-auto an toàn; người dùng review/revoke qua terms CLI với trace đầy đủ.
**FRs covered:** FR3, FR6, FR15

### Epic 4: Global Learner & Registry
Bằng chứng tích lũy qua nhiều truyện độc lập tại registry của dictionary root; global promotion fail-closed chờ golden manifest được duyệt.
**FRs covered:** FR4

### Epic 5: QA, Golden Tooling & Regression
QA structural chặn export thay vì sửa; golden manifest + diff report so với candidate reference `raw_china`; metamorphic + dictionary unit tests chứng minh mọi invariant không cần model.
**FRs covered:** FR7, FR8, FR11, FR18

## Epic 1: VietPhrase-Only Cutover

Người dùng dịch TXT bằng một đường VietPhrase duy nhất, offline, deterministic; mọi dấu vết model-era biến mất khỏi runtime nhưng lịch sử audit còn nguyên.

### Story 1.1: Gỡ engine Hachimi/Qwen, router và post-edit khỏi đường dịch

As a người vận hành zhvi,
I want pipeline chỉ còn một đường sinh văn bản là VietPhrase engine,
So that hệ thống offline hoàn toàn, không còn model runtime hay network call.

**Acceptance Criteria:**

**Given** codebase hiện có `engines/hachimi_worker.py`, `engines/ollama_qwen.py`, router bốn route, `execute_route`, route `LOCAL_PATCH`/post-edit
**When** story hoàn tất
**Then** các module engine model, router route, prompt schema, model acceptability gate, masked-term round-trip bị xóa khỏi `zhvi/src/zhvi/`; `pipeline.py`/`executor.py` chỉ còn đường VietPhrase
**And** `grep -r "hachimi\|ollama\|qwen\|LOCAL_PATCH\|execute_route" zhvi/src zhvi/tests` không còn match ngoài comment migration
**And** toàn bộ test suite `zhvi` pass sau khi xóa test model-era tương ứng

### Story 1.2: Dọn config, CLI flags và fingerprint không còn thành phần model

As a người vận hành zhvi,
I want config và CLI không còn `use_hachimi`, `use_qwen`, `qwen_*`, `hachimi_*`, profile model, `PROMPT_SCHEMA_VERSION`,
So that cấu hình chỉ còn các field thật sự ảnh hưởng hành vi VietPhrase và learning.

**Acceptance Criteria:**

**Given** `config.py` và `cli.py` còn field/flag model-era
**When** story hoàn tất
**Then** mọi field/flag model bị loại; không còn profile chỉ khác việc gọi model; fingerprint dictionary/cache không chứa thành phần prompt/model/router
**And** config mới đúng schema SPEC (style, output_policy, encoding, dict_dir, global_glossary, pattern_rules, collapse_repetitions, qa_strip_junk, [learning], [runtime])
**And** test CLI xác nhận các flag đã biến mất và config load được từ file mẫu

### Story 1.3: Migration schema additive — giữ lịch sử, invalidate cache model-era

As a người vận hành zhvi với dữ liệu lịch sử,
I want migration tăng `SCHEMA_VERSION`, giữ source revision/run/block/route cũ read-only và vô hiệu mọi cache có fingerprint model-era,
So that audit history còn nguyên nhưng không run nào tái dùng kết quả model cũ.

**Acceptance Criteria:**

**Given** một book project có state SQLite và cache từ thiết kế 2.0
**When** chạy binary mới lần đầu trên project cũ
**Then** migration chỉ add/transform (thêm bảng revision/evidence/promotion/regression theo cần của story, không tạo trước toàn bộ); không drop hay rewrite lịch sử; route metadata cũ giữ read-only
**And** mọi block cache có fingerprint chứa prompt/model/router bị đánh dấu invalid/không tái dùng; run mới chỉ ghi route `VIETPHRASE`
**And** test tạo DB cũ (fixture) rồi migrate, xác nhận history đọc được và cache cũ không hit

### Story 1.4: Đường dịch deterministic theo AD-9

As a người dùng dịch truyện,
I want matching path xác định hoàn toàn: phồn→giản để match (giữ source gốc trong trace), trie longest-match, precedence theo lớp, literal thắng pattern, tie-break theo `entry_id`,
So that cùng input luôn ra cùng output bất kể thứ tự file/hash map.

**Acceptance Criteria:**

**Given** dictionary có nhiều entry cùng span khác lớp, entry pattern và literal cùng độ dài, phồn thể trong source
**When** dịch cùng block hai lần với thứ tự load từ điển khác nhau
**Then** output giống hệt nhau; span trúng được chọn theo precedence lớp rồi `entry_id`; literal thắng pattern cùng độ dài
**And** trace lưu source gốc (phồn thể) cho span dùng key giản thể
**And** unit test cố định các cặp ambiguity nêu trên

### Story 1.5: Test baseline VietPhrase-only + doctor/status/README cập nhật

As a người vận hành zhvi,
I want test baseline chứng minh deterministic output và resume parity, kèm doctor/status/README phản ánh kiến trúc mới,
So đó bằng chứng cutover hoàn tất (Milestone 1).

**Acceptance Criteria:**

**Given** repo sau Story 1.1–1.4
**When** chạy toàn bộ suite `zhvi`
**Then** root test collection khai báo đủ dependency đang import (không dựa package cài sẵn ngoài `zhvi`); có test deterministic (cùng fingerprint → cùng output SHA-256) và test resume parity (interrupt rồi resume == clean run)
**And** `zhvi doctor` kiểm tra dictionary, DB, disk, smoke translation không nhắc model; `zhvi status` hiển thị route VIETPHRASE; README mô tả kiến trúc VietPhrase-only
**And** suite pass toàn bộ

## Epic 2: Immutable Dictionary Revisions

Người dùng có vòng đời từ điển bất biến: revision bundle content-addressed, activate CAS, diff, rollback; run pin một revision; sửa chất lượng = sửa entry rồi dịch lại đúng block bị ảnh hưởng.

### Story 2.1: Revision bundle builder và canonical manifest

As a người vận hành zhvi,
I want revision builder đọc base/auto/manual layers, validate, tạo canonical manifest và materialize bundle content-addressed,
So đó từ điển của run là artifact bất biến, truy được và tái lập được.

**Acceptance Criteria:**

**Given** các layer từ điển (base files, auto entries từ state store, manual layers)
**When** build revision
**Then** manifest chứa hash từng layer + loader/renderer version + precedence policy; `dictionary_revision_id = SHA-256(canonical_manifest)`; bundle chứa `manifest.json`, `entries.tsv`, `patterns.jsonl`, `dictionary.bin`
**And** validate format/duplicate; hai auto entry cùng scope/lớp cùng key khác target làm build fail với conflict report
**And** cùng tập input tạo cùng revision id (test)

### Story 2.2: Publish protocol — atomic rename, transaction, CAS activation

As a người vận hành zhvi,
I want revision publish theo protocol temp → fsync → atomic rename → SQLite transaction (insert `ready` + CAS active pointer) → projection sau commit,
So đó DB không bao giờ trỏ bundle dở dang và crash không làm mất active revision hợp lệ.

**Acceptance Criteria:**

**Given** bundle đã build ở temp
**When** publish
**Then** file + directory được fsync trước atomic rename vào `revisions/<id>/`; trong một transaction: insert revision `ready` và CAS active pointer từ revision kỳ vọng sang revision mới; stale writer (active đổi giữa chừng) phải evaluate/build lại
**And** trạng thái revision đủ: `building → validating → ready → active`, `rejected`, `active → superseded/revoked`; crash giữa chừng không đổi active revision
**And** bundle rename mà chưa commit DB là orphan, có lệnh/tiện ích GC; test mô phỏng crash từng bước

### Story 2.3: Run pin revision; loader đọc bundle, resume dùng đúng bundle

As a người dùng dịch truyện,
I want run freeze `dictionary_revision_id` lúc tạo và loader chỉ nạp bundle đã pin,
So đó thay `Custom.txt`/glossary/projection sau đó không làm thay nội dung run đang chạy hoặc run resume.

**Acceptance Criteria:**

**Given** một run đang dịch với revision R
**When** file từ điển nguồn hoặc projection thay đổi giữa chừng rồi run bị interrupt và resume
**Then** resume vẫn pin R, output các block còn lại nhất quán với các block đã commit
**And** loader không đọc file mutable sau khi pin; cache key gồm source block hash + dictionary revision + parser/renderer/QA version, chỉ hit khi trùng toàn bộ
**And** run lịch sử có thể đọc bundle `ready/superseded/revoked` để reproduce; run mới chỉ pin active revision

### Story 2.4: Projection auto + startup reconciler + ownership guard

As a người vận hành zhvi,
I want `AutoVietPhrase.txt` và `glossary.auto.tsv` chỉ là projection dựng lại từ active pointer, và reconciler kiểm tra tính khớp lúc startup,
So đó hai nguồn chân lý không tồn tại và crash giữa publish tự phục hồi.

**Acceptance Criteria:**

**Given** revision active mới sau commit
**When** projection được dựng
**Then** projection materialize sau DB commit từ active pointer; crash trước khi dựng xong được startup reconciler dựng lại
**And** reconciler kiểm active pointer + bundle hash + projection; bundle thiếu/hash sai là fatal corruption với thông báo rõ
**And** code ghi file có guard: mọi đường ghi vào `Custom.txt`, `QualityOverrides.txt`, `VietPhrase_*.txt`, `glossary.manual.tsv`, `.manual.*` bị chặn (test cố gắng ghi từng file phải fail)

### Story 2.5: Diff, rollback và affected-block rerun

As a người dùng sửa chất lượng bản dịch,
I want `zhvi dict diff REV_A REV_B`, `zhvi dict rollback REV` và vòng sửa entry → revision mới → dịch lại đúng affected blocks → export lại atomic,
So đó mọi correction truy được về entry/rule và không có "bản text đã sửa" thứ hai.

**Acceptance Criteria:**

**Given** hai revision hoặc một revision an toàn trong lịch sử
**When** chạy diff/rollback
**Then** diff hiển thị entry khác nhau + affected blocks (qua trace/source index); rollback tạo revision mới có tập entry tương đương revision an toàn, không sửa revision cũ (event append-only)
**And** khi user thêm/sửa entry trong `glossary.manual.tsv`: hệ thống build revision mới, xác định affected blocks, dịch lại đúng tập đó, chạy QA, export lại atomic
**And** test: sau correction, số block thay đổi đúng tập block chứa key; block không chứa key giữ nguyên hash

### Story 2.6: Versioned preprocessing view (FR13)

As a người dùng dịch truyện bẩn (junk, lặp),
I want preprocessing view version hóa: junk stripping xóa span kèm source offsets + reason code; repetition collapse ở renderer trên ranh giới target span,
So đó transformation tái lập được, tham gia fingerprint và không đụng source snapshot.

**Acceptance Criteria:**

**Given** source chứa junk quảng cáo và cụm lặp
**When** dịch
**Then** junk chỉ bị xóa ở translation view với offsets + reason code lưu trace; source snapshot bytes không đổi; repetition collapse xảy ra ở renderer trên ranh giới hai target span và ghi trace
**And** preprocessor version + renderer version nằm trong fingerprint; đổi version tạo evaluation mới
**And** phần không dịch được giữ nguyên byte-equivalent khi export (test)

## Epic 3: Book Learner

Trong phạm vi một truyện, hệ thống tự phát hiện cụm yếu, tạo candidate xác định, tính evidence và promote book-auto an toàn; người dùng review/revoke qua terms CLI với trace đầy đủ.

### Story 3.1: Discovery toàn truyện tạo observation

As a hệ thống học theo truyện,
I want discovery chạy trước khi dịch, thu n-gram CJK 2–8 ký tự, tần suất tuyệt đối + theo chương, left/right context diversity, PMI, chuỗi bị tách thành entry một ký tự, unknown span, segmentation đa phương án, pattern tên riêng (người/địa danh/môn phái/công pháp/cảnh giới),
So đó có dữ liệu thô để sinh candidate mà không đụng engine.

**Acceptance Criteria:**

**Given** một source revision đã import
**When** chạy discovery
**Then** observation ghi vào bảng `observations` của book SQLite; discovery không nạp observation vào engine
**And** observation deterministic: cùng source revision chạy hai lần ra cùng tập observation
**And** unit test với fixture chứa tên riêng lặp và cụm bị phân đoạn mảnh

### Story 3.2: Candidate builder — target xác định hoặc unresolved

As a hệ thống học theo truyện,
I want candidate builder chỉ sinh target từ 6 nguồn xác định (lớp thấp hơn, ghép longest-match entry con, phiên âm Hán–Việt cho tên riêng, template `LuatNhan.txt`, correction/glossary người dùng, target đã accept còn provenance),
So đó máy không bao giờ bịa nghĩa để tăng coverage.

**Acceptance Criteria:**

**Given** tập observation
**When** build candidate
**Then** candidate không có target từ 6 nguồn mang trạng thái `unresolved`; candidate có target kèm provenance nguồn
**And** key chuẩn hóa NFC + giản thể để so khớp, source gốc lưu provenance; target chuẩn hóa khoảng trắng/dấu câu theo rule
**And** target mơ hồ (`a/b`, placeholder, ký tự CJK) bị loại khỏi auto-promote; candidate trùng manual entry bị loại
**And** candidate ghép entry con chỉ eligible khi mỗi entry con có đúng một target ưu tiên

### Story 3.3: Evidence evaluator

As a hệ thống học theo truyện,
I want mỗi candidate có evidence độc lập với output: độ mạnh (frequency, PMI, left/right entropy), độ ổn định (cùng segmentation + target qua occurrence), lợi ích (giảm unknown/single-char/fragmentation), rủi ro (overlap/target/manual conflict, junk likelihood), phạm vi (chương/truyện/thể loại), regression (block đổi, golden diff, invariant fail),
So đó promotion quyết trên tín hiệu kiểm chứng được chứ không phải cảm tính.

**Acceptance Criteria:**

**Given** candidate đã build
**When** evaluate
**Then** evidence lưu bảng `candidate_evidence` theo từng nhóm tín hiệu; điểm chỉ dùng xếp hạng
**And** evidence tính từ observation + trạng thái từ điển hiện tại, không phụ thuộc output cuối
**And** test: candidate tăng coverage thật có evidence benefit dương; candidate conflict manual có risk manual_conflict

### Story 3.4: Book-auto promotion qua hard gates

As a hệ thống học theo truyện,
I want candidate promote lên `book_auto` chỉ khi pass hard gates (ngưỡng occurrence/chapter, target stability 100%, không manual conflict, coverage/fragmentation cải thiện, structural invariant pass, affected-block isolation pass),
So đó auto entry an toàn cho truyện và rollback được.

**Acceptance Criteria:**

**Given** candidate có evidence
**When** đánh giá promotion
**Then** lifecycle `observed → candidate → book_auto` (kèm `unresolved`, `rejected`, `revoked`) ghi event append-only (before/after/actor/timestamp/provenance)
**And** gate fail một mục là reject, điểm cao không bù; promotion ghi `glossary.auto.tsv` (projection, qua revision builder) và chỉ ảnh hưởng truyện đó
**And** số block thay đổi đúng tập block chứa candidate (isolation test)
**And** revoke một book-auto entry build revision mới và chỉ đổi affected blocks

### Story 3.5: Terms CLI + explain/review display

As a người duyệt candidate,
I want `zhvi terms list/accept/reject/revoke` và `zhvi explain TEXT` hiển thị source span, segmentation trace, entry/layer/revision của từng target span, candidate liên quan, affected blocks,
So đó quyết định sửa gì dựa trên trace đầy đủ thay vì đoán.

**Acceptance Criteria:**

**Given** project có candidate/auto entry
**When** chạy terms list/accept/reject/revoke và explain
**Then** list hiển thị candidate/evidence/trạng thái; accept tạo manual entry (từ đó manual thắng auto); reject ghi audit event; revoke như Story 3.4
**And** explain hiển thị segmentation + provenance từng span (entry id, layer, revision) và các block khác sẽ đổi nếu đổi entry
**And** mọi lệnh có audit event; test CLI走 full vòng: list → accept → translate đổi output đúng chỗ

## Epic 4: Global Learner & Registry

Bằng chứng tích lũy qua nhiều truyện độc lập tại registry của dictionary root; global promotion fail-closed chờ golden manifest được duyệt.

### Story 4.1: Registry tại dictionary root — book_id, realpath, writer lock

As a hệ thống học toàn cục,
I want registry SQLite tại `<dict_dir>/.zhvi-registry/state.sqlite3` xác định duy nhất qua `realpath(dict_dir)`, `zhvi init` tạo stable `book_id`, một registry writer lock,
So đó chỉ một writer được mutate global state/projection và copy project không giả tạo truyện độc lập.

**Acceptance Criteria:**

**Given** dictionary root (có thể qua symlink)
**When** truy cập registry
**Then** registry resolve qua realpath; mỗi resolved root đúng một registry + một writer lock (`locks/registry.lock`)
**And** `zhvi init` tạo `book_id` một lần lưu trong `zhvi.toml`; bản copy project giữ cùng ID nên registry không tính là truyện độc lập
**And** hai writer concurrently: một bị chặn với thông báo lock rõ ràng; không giữ lock trong discovery

### Story 4.2: Cross-book evidence ingest + dedupe

As a hệ thống học toàn cục,
I want book project gửi evidence bất biến (kèm book_id, source revision, occurrence identity) vào registry, dedupe theo `(book_id, source_revision_id, candidate_id, occurrence_span)`, chỉ tính active source revision mỗi book,
So đó copy project/import lại không tăng cross-book count.

**Acceptance Criteria:**

**Given** nhiều book project submit evidence cho cùng candidate
**When** ingest
**Then** occurrence trùng key dedupe; chỉ active source revision của mỗi book vào promotion evidence; book không mutate global candidate/revision trực tiếp
**And** test: copy project + import lại cùng source không tăng cross-book count và không tăng occurrence tổng

### Story 4.3: Global promotion fail-closed + drift report

As a người quản lý từ điển chung,
I want `zhvi learn --global` đánh giá `global_candidate → global_auto` với hard gates (≥3 truyện độc lập, ≥20 occurrence, target agreement 100%, không manual conflict mọi project đã đăng ký, pass golden suite, không tăng unknown/CJK residue/structural failure, diff ngoài affected blocks bằng 0) và global auto-promotion khóa khi chưa có approved golden manifest,
So đó từ điển toàn cục chỉ đổi khi có bằng chứng không regression.

**Acceptance Criteria:**

**Given** candidate `global_candidate` có cross-book evidence
**When** đánh giá global promotion
**Then** thiếu bất kỳ hard gate (đặc biệt approved golden manifest) thì candidate dừng ở `global_candidate` với lý do từng gate; không file `expect*` nào tự thành golden
**And** khi đủ điều kiện (golden manifest approved tồn tại): promotion atomic qua registry (lock, revision build, CAS active global); global activation không đổi active book revision hiện có; `AutoVietPhrase.txt` materialize chỉ bởi registry writer
**And** xuất drift report theo revision (entry mới/đổi/revoked, affected books); revoke global auto entry append event và build revision mới
**And** test: không golden manifest thì không thể global auto-promote dù evidence đủ — fail-closed xác nhận

## Epic 5: QA, Golden Tooling & Regression

QA structural chặn export thay vì sửa; golden manifest + diff report so với candidate reference `raw_china`; metamorphic + dictionary unit tests chứng minh mọi invariant không cần model.

### Story 5.1: QA structural gates + run report metric

As a người dùng cần bản dịch đáng tin,
I want QA chỉ pass hoặc chặn export (đủ block đúng thứ tự, không duplicate/missing, structural span dựng lại được, không placeholder nội bộ, CJK residue trong policy, không artifact lặp, entity nhất quán theo revision, output hash + manifest khớp) và run report metric riêng lẻ,
So đó không có hidden repair và chất lượng đo được bằng con số kiểm chứng.

**Acceptance Criteria:**

**Given** run translate hoàn tất các block
**When** QA chạy
**Then** QA fail chuyển run sang `needs_dictionary_fix`, không export, không sửa output; QA pass mới export atomic
**And** run report xuất: dictionary_revision_id, coverage (ký tự + span), unknown spans, single-char ratio, fragmentation, candidate count theo trạng thái, entry auto dùng, affected blocks, regression pass/fail, output SHA-256, elapsed + chars/s — không có quality score tổng hợp
**And** test fixture chạy ra từng loại QA fail tương ứng

### Story 5.2: Golden manifest tooling + diff report candidate reference

As a người duyệt golden corpus,
I want công cụ tạo/sửa golden manifest (`zhvi/tests/golden/manifest.json`: source hash, expected hash, phạm vi assertion, provenance, dấu duyệt), import `raw_china/expect*.txt` + `excpect*.txt` làm candidate, và chạy pipeline xuất diff report cho toàn bộ candidate reference,
So đó quyết định golden dựa trên diff thật và global gate chỉ chạy trên case đã duyệt.

**Acceptance Criteria:**

**Given** các file `raw_china/expect.txt`, `raw_china/excpect2.txt` (và mọi file khớp `expect*`/`excpect*`)
**When** chạy lệnh golden tooling
**Then** pipeline dịch source đã pin, so sánh với expected đã pin (byte hoặc approved structural diff), xuất diff report cho từng case với trace tới candidate/entry
**And** chỉ case trạng thái `approved` (đủ source hash + expected hash + assertion scope + provenance + dấu duyệt) tham gia promotion gate; case chưa duyệt hiện trong report với nhãn candidate
**And** global auto-promotion (Story 4.3) đọc cùng manifest này; test xác nhận case không approved không thể mở global gate

### Story 5.3: Metamorphic + dictionary unit test suite

As a người bảo đảm chất lượng,
I want suite metamorphic (thêm entry không có trong source không đổi output; reorder file auto không đổi output; dịch cả truyện một lần == từng chương; resume == clean run; rollback + chạy lại khôi phục output hash; phồn/giản thể alias chọn cùng entry) và dictionary unit tests (parse mọi dòng, auto không duplicate/conflict, precedence, alias, pattern không nuốt literal dài hơn, deterministic),
So đó mọi invariant kiến trúc được kiểm liên tục không cần model.

**Acceptance Criteria:**

**Given** repo sau Epic 1–4
**When** chạy suite
**Then** cả 6 bất biến metamorphic có test riêng và pass; dictionary unit tests phủ 6 nhóm nêu trên
**And** test dùng fixture tự chứa (khai báo dependency trong root test collection), không gọi network/model
**And** suite chạy trong thời gian hợp lý cho CI local (< vài phút)

### Story 5.4: CLI integration end-to-end + documentation

As a người vận hành zhvi,
I want integration test chạy happy path đầy đủ `zhvi translate FILE -o OUT` (snapshot → discover → book-auto learn → freeze → translate → QA → export → report) trên fixture truyện nhỏ, và tài liệu cập nhật,
So đó người dùng mới chạy được toàn vòng đời bằng một lệnh.

**Acceptance Criteria:**

**Given** fixture TXT tiếng Trung nhỏ trong repo test
**When** chạy `zhvi translate fixture.txt -o out.vi.txt` (subprocess hoặc invoke Typer)
**Then** output + manifest tồn tại, manifest chứa run ID + revision ID + output SHA-256; lệnh `--no-learn`, `status`, `export`, `doctor` đều chạy đúng vai trò
**And** README/docs zhvi mô tả kiến trúc mới, CLI contract, vòng correction (entry → revision → rerun) và trạng thái khóa của global auto-promotion
**And** toàn bộ suite `zhvi` pass
