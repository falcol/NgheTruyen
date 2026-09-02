# Thiết kế CLI dịch truyện Trung → Việt

## VietPhrase-first, HachimiMT fallback, Qwen selective repair

> **[Suy luận]** Đây là thiết kế kiến trúc CLI được tối ưu cho luồng: crawler tạo TXT → chạy CLI → nhận TXT tiếng Việt. Tôi không thể xác minh đây là phương án tốt nhất tuyệt đối nếu chưa benchmark trên bộ từ điển, model Qwen và corpus truyện thực tế của bạn. Các ngưỡng trong tài liệu là cấu hình khởi tạo, không phải chất lượng đã được kiểm định.

Phiên bản thiết kế: 2.0 — CLI-first.

## 1. Quyết định kiến trúc cuối cùng

CLI được xây như một **translation project engine có state**, không phải script đọc từng dòng rồi gọi model.

Luồng chuẩn:

~~~text
TXT snapshot
→ parse lossless
→ quét toàn truyện
→ phát hiện entity/cụm chưa biết
→ tạo và đóng băng book glossary
→ dựng VietPhrase lattice
→ router chọn block cần hỗ trợ
→ Hachimi hoặc Qwen chỉ xử lý block yếu
→ QA theo block và toàn chương
→ commit checkpoint
→ export TXT atomic
→ lưu observation/candidate cho revision sau
~~~

Các nguyên tắc bất biến:

1. VietPhrase là nền tảng dịch mặc định.
2. AI không chạy trên block VietPhrase được xác định là đủ tin cậy, trừ audit sampling được bật rõ ràng.
3. Mỗi run dùng một source revision, dictionary snapshot, model và config bất biến.
4. Không cập nhật dictionary giữa một final pass.
5. Tên và thuật ngữ được khóa theo **từng occurrence**, không replace chuỗi mù.
6. Output cuối chỉ được publish sau khi hoàn tất kiểm tra.
7. Chạy lại cùng input/config không dịch lại.
8. Crash hoặc Ctrl-C không làm mất các block đã commit.
9. AI output không phải ground truth và không tự động trở thành dictionary.
10. Từ tự học mặc định chỉ có scope một truyện.

## 2. Điểm thay đổi so với thiết kế trước

### Giữ lại

- VietPhrase → Hachimi → Qwen.
- SQLite cho state và audit.
- structured output từ Ollama.
- glossary guard, QA và rollback.
- book-level learning, global manual.

### Thay đổi

| Thiết kế cũ | Thiết kế CLI-first |
|---|---|
| Route từng câu độc lập | Route block ngữ nghĩa có context |
| Longest-match greedy | Lattice + top-K path |
| Coverage là tín hiệu chính | Risk nhiều feature + lattice margin |
| Học và promote trong lúc dịch | Discovery trước, snapshot bất biến |
| Một dictionary entry luôn bị khóa | HARD, PREFERRED hoặc CONTEXTUAL theo occurrence |
| Replace term hậu kỳ | Alignment-safe patch hoặc reject |
| Queue/worker kiểu service | Một foreground controller có checkpoint |
| FastAPI từ đầu | Hoãn; CLI là sản phẩm chính |
| DB chứa toàn bộ dictionary nền | Base dictionary là file; DB lưu state/revision/cache |
| Export nối chuỗi trực tiếp | Rebuild từ structural spans rồi atomic replace |

### Loại khỏi MVP

- FastAPI.
- Redis, Celery hoặc server job queue.
- EPUB/HTML adapters.
- nhiều Qwen request đồng thời.
- online fine-tune.
- auto-promote global.
- summary tự do do LLM sinh làm bộ nhớ chuẩn.

## 3. Trải nghiệm CLI

### 3.1. Happy path: một lệnh

~~~bash
zhvi translate ./crawl/truyen.txt \
  --output ./dist/truyen.vi.txt \
  --profile balanced \
  --style convert-qt
~~~

Nếu chưa có project, CLI tự tạo workspace cạnh input:

~~~text
truyen.txt
truyen.zhvi/
└── ...
~~~

Lệnh translate tự thực hiện:

1. preflight;
2. snapshot TXT;
3. inspect cấu trúc;
4. analyze toàn truyện;
5. freeze glossary;
6. resume run trùng fingerprint nếu có;
7. dịch/checkpoint;
8. QA;
9. export atomic;
10. in báo cáo.

Nếu cùng fingerprint đã hoàn thành, lệnh là no-op và trả lại thông tin output hiện có.

### 3.2. Project workflow cho truyện cập nhật nhiều lần

~~~bash
zhvi init ./books/pham-nhan --source ./crawl/pham-nhan.txt
zhvi inspect --project ./books/pham-nhan
zhvi translate --project ./books/pham-nhan
zhvi status --project ./books/pham-nhan
zhvi review --project ./books/pham-nhan
zhvi export --project ./books/pham-nhan -o ./dist/pham-nhan.vi.txt
~~~

Khi crawler thêm chương:

~~~bash
zhvi import ./crawl/pham-nhan.txt --project ./books/pham-nhan --update
zhvi translate --project ./books/pham-nhan
~~~

- Source byte-identical: no-op.
- Chỉ append chương: tạo source revision mới và tái dùng block cũ hợp lệ.
- Nội dung cũ bị sửa/xóa: hiển thị diff summary và yêu cầu cờ xác nhận rõ ràng.
- Không trộn checkpoint của source revision cũ vào run mới mà không kiểm tra cache key.

## 4. Bộ lệnh chính thức

### Lệnh dùng thường xuyên

| Command | Mục đích |
|---|---|
| zhvi doctor | kiểm tra dictionary, Hachimi, Ollama/Qwen, disk và smoke test |
| zhvi translate | happy path; analyze, resume, dịch và export |
| zhvi status | tiến độ, route, cache, lỗi, review |
| zhvi review | xem/sửa block không chắc chắn |
| zhvi terms | xem, accept, reject, edit và rollback term |
| zhvi export | dựng lại TXT từ một run cụ thể |

### Lệnh nâng cao

~~~bash
zhvi init PROJECT --source FILE
zhvi import FILE --project PROJECT --update
zhvi inspect --project PROJECT --sample 200
zhvi config show --resolved
zhvi config validate
zhvi runs list
zhvi runs show RUN_ID
zhvi logs RUN_ID --follow
zhvi verify RUN_ID
zhvi benchmark runtime --input representative.txt --write-profile
zhvi rerun RUN_ID --affected
~~~

### Resume

- Có đúng một run chưa hoàn thành và fingerprint trùng hoàn toàn: translate tự resume.
- Có nhiều candidate run hoặc người dùng chỉ định run: dùng resume RUN_ID.
- Config/model/dictionary/source khác: tạo run mới; không âm thầm dùng checkpoint cũ.
- Muốn thử model/profile mới: tạo child run bằng cờ rõ ràng.

~~~bash
zhvi resume RUN_ID
zhvi resume RUN_ID --retry-transient
zhvi translate --project PROJECT --fork-run --profile quality
~~~

## 5. Project layout

~~~text
book-project/
├── zhvi.toml
├── glossary.manual.tsv
├── dist/
│   ├── book.vi.txt
│   └── book.vi.manifest.json
└── .zhvi/
    ├── state.sqlite3
    ├── sources/
    │   └── <source-revision>.txt
    ├── dictionaries/
    │   └── <dictionary-snapshot>.tsv
    ├── runs/
    │   └── <run-id>/
    │       ├── manifest.json
    │       ├── report.json
    │       └── review.jsonl
    ├── logs/
    │   └── <run-id>.jsonl
    ├── cache/
    └── locks/
~~~

- zhvi.toml: cấu hình project do người dùng quản lý.
- glossary.manual.tsv: term người dùng khóa cho truyện.
- sources: snapshot TXT bất biến.
- dictionaries: glossary snapshot chính xác của từng run.
- state.sqlite3: run, block, attempt, candidate, feedback và revision.
- cache: compiled trie/lattice và model result có thể tạo lại.
- logs: event có cấu trúc.
- dist: artifact được publish.

Không ghi runtime state vào source TXT.

## 6. Hợp đồng với crawler

CLI chỉ cần TXT, nhưng crawler nên:

1. xuất UTF-8 mặc định;
2. giữ heading chương trên dòng riêng;
3. giữ paragraph/newline cần thiết;
4. ghi file tạm rồi rename;
5. tùy chọn tạo sidecar JSON gồm source URL, crawl time, chapter count và hash.

CLI không phụ thuộc sidecar.

### Snapshot an toàn

Khi import:

1. đọc stat trước;
2. copy bytes vào snapshot tạm;
3. tính SHA-256 trong lúc copy;
4. đọc stat lại;
5. nếu file thay đổi, bỏ snapshot và retry hữu hạn hoặc fail;
6. fsync và atomic rename snapshot.

Không auto-detect encoding âm thầm. Default UTF-8; encoding khác phải chỉ định:

~~~bash
zhvi import book.txt --encoding gb18030
~~~

Nếu decode lỗi, lệnh dừng và báo byte offset.

## 7. Parse TXT lossless

Parser lưu:

~~~text
StructuralNode:
  heading, newline, whitespace, separator, metadata

TranslatableNode:
  paragraph, dialogue, narration
~~~

Mỗi node có:

~~~text
source_revision
byte_start / byte_end
char_start / char_end
ordinal
raw_text
normalized_text
node_type
chapter_id
~~~

Output được dựng lại từ structural nodes và final translation của translatable nodes. Paragraph, heading, blank line và dấu thoại không bị mất do split/join tùy tiện.

### Chapter detection

Parser hỗ trợ:

- regex cấu hình;
- preset cho 第...章, 第...回, 第...节;
- fallback theo paragraph nếu không có heading.

Inspect báo:

- số heading;
- heading nghi ngờ;
- đoạn quá dài;
- dấu ngoặc/quote không cân bằng;
- tỷ lệ Hán tự;
- newline style.

Nếu chapter detection mơ hồ vượt policy, strict mode dừng trước khi gọi model.

## 8. Stable identity, fingerprint và cache

Không dùng một ID cho cả vị trí tài liệu và cache.

### Document identity

~~~text
segment_id = source_revision + chapter_ordinal + block_ordinal
~~~

Hai câu giống nhau ở hai vị trí vẫn có segment_id khác.

### Run fingerprint

~~~text
SHA256(
  source_revision_hash
  + encoding
  + parser_version
  + resolved_config_hash
  + base_dictionary_hash
  + book_glossary_snapshot_hash
  + style_profile_hash
  + router_version
  + qa_version
  + prompt_schema_hash
  + Hachimi_model_digest
  + Qwen_model_digest
  + pipeline_version
)
~~~

### Model-result cache

~~~text
SHA256(
  normalized_source
  + context_fingerprint
  + occurrence_constraints
  + relevant_terms_fingerprint
  + style
  + engine/model digest
  + tokenizer revision
  + generation options
  + prompt/schema version
)
~~~

Manifest ghi full dictionary revision để audit, nhưng cache chỉ phụ thuộc term có thể ảnh hưởng block. Một term không liên quan không nên làm vô hiệu toàn bộ cache.

## 9. Pipeline hai pha

~~~mermaid
flowchart TD
    A["TXT snapshot"] --> B["Book pre-scan"]
    B --> C["Entity & unknown discovery"]
    C --> D["Book glossary snapshot"]
    D --> E["Chapter/block planning"]
    E --> F["VietPhrase lattice"]
    F --> G{"Baseline risk"}
    G -->|thấp| H["DIRECT_VP"]
    G -->|cục bộ| I["LOCAL_PATCH"]
    G -->|trung bình| J["Hachimi candidate"]
    G -->|cao| K["Qwen post-edit"]
    J --> L{"Candidate gate"}
    L -->|đạt| M["Chapter QA"]
    L -->|trượt| K
    H --> M
    I --> M
    K --> M
    M --> N["Checkpoint"]
    N --> O["Atomic export"]
    N --> P["Observation cho revision sau"]
~~~

### Phase A — discovery/bootstrap

Quét toàn TXT theo stream và index vào SQLite:

- unknown span lặp;
- tên người/địa danh/môn phái/cảnh giới/vật phẩm;
- alias;
- dictionary collision;
- occurrence và context hash.

Với learning safe:

1. candidate đủ recurrence mới được phân tích;
2. Hachimi và Qwen induction chạy độc lập;
3. Qwen blind induction không nhìn Hachimi output;
4. hard gate và replay;
5. chỉ entity book-local đạt policy mới active;
6. commit dictionary revision;
7. freeze snapshot cho final pass.

### Phase B — final translation

- Snapshot không đổi trong toàn run.
- Candidate mới chỉ được observe.
- Muốn áp dụng candidate sau run: tạo revision và affected rerun.
- Không có output chứa block dịch bằng nhiều dictionary revision.

## 10. Semantic block thay cho sentence đơn

Quy tắc:

1. Heading là block riêng.
2. Không cắt trong quote/ngoặc lồng.
3. Một lượt thoại ngắn giữ cùng câu dẫn.
4. Đoạn dài cắt tại clause boundary ngoài quote.
5. Adjacent risky sentences có thể gom thành một target unit.
6. Kích thước cuối dựa trên tokenizer và context budget.

Qwen nhận:

- target block;
- source block lân cận;
- final translation đã commit ở phía trước;
- entity ledger có evidence;
- occurrence constraints;
- style profile.

Context chỉ để tham khảo. Structured response phải trả đúng target block IDs. Không gửi toàn chương vào Qwen.

## 11. VietPhrase Core tốt hơn longest-match

### 11.1. Dictionary layers

| Layer | Vai trò |
|---|---|
| user segment override | block người dùng khóa |
| book manual | term người dùng khóa trong truyện |
| series manual | term dùng cho một series |
| global manual | term toàn cục đã duyệt |
| base multi-char | phrase/name từ bộ nền |
| book auto fill-only | entity tự học, không đè manual/base multi-char |
| base single-char | Hán-Việt fallback |

Không dùng một priority integer tùy ý để phá policy. Precedence được mã hóa theo loại, scope và trust.

### 11.2. Lattice

Matcher giữ mọi match chồng lấn:

~~~text
source position
→ candidate entries
→ edges tới end position
→ top-K paths bằng dynamic programming/beam
~~~

Path score dùng:

- scope/trust;
- phrase length;
- learned weight;
- penalty single-character fallback;
- penalty segmentation phân mảnh;
- correction history;
- sense constraint theo occurrence.

Risk features:

- margin top-1/top-2;
- path entropy;
- bất đồng forward/reverse/best-path;
- số contextual entry chưa giải quyết.

Longest-match có thể là baseline, không phải confidence duy nhất.

### 11.3. Trace

~~~python
@dataclass(frozen=True)
class VpSpan:
    occurrence_id: str
    source_start: int
    source_end: int
    source: str
    target: str
    alternatives: tuple[str, ...]
    entry_version_id: str | None
    policy: Literal["HARD", "PREFERRED", "CONTEXTUAL"]
    path_score: float

@dataclass(frozen=True)
class VpDraft:
    text: str
    spans: tuple[VpSpan, ...]
    unknown_spans: tuple[SourceSpan, ...]
    single_char_ratio: float
    lattice_margin: float
    lattice_entropy: float
    warnings: tuple[str, ...]
~~~

## 12. Router: selective prediction

Không có detector rule-only nào biết hoàn hảo bản VietPhrase có đúng nghĩa. Router phải có nhánh abstain và được hiệu chỉnh từ feedback.

### Baseline risk features

- unknown span theo độ dài/độ hiếm;
- tỷ lệ single-character fallback;
- lattice margin/entropy;
- segmentation instability;
- unresolved entity/alias;
- contextual/đa nghĩa;
- phủ định hoặc phủ định kép;
- 把/被, văn ngôn, thành ngữ;
- số lượng–đơn vị, tiền, cấp bậc;
- câu nhiều mệnh đề;
- đổi lượt thoại/đại từ;
- history correction;
- known bad pattern.

### Bốn route

| Route | Khi dùng | Engine |
|---|---|---|
| DIRECT_VP | risk thấp và invariant gate đạt | không gọi model |
| LOCAL_PATCH | chỉ vài source span yếu | deterministic hoặc structured patch |
| HACHIMI_CANDIDATE | VP khó đọc/risk trung bình | HachimiMT |
| QWEN_POSTEDIT | cấu trúc khó, Hachimi trượt/bất đồng lớn | Qwen |

Mỗi decision lưu reason code, không chỉ một score:

~~~text
UNKNOWN_LONG_SPAN
LOW_LATTICE_MARGIN
ENTITY_UNRESOLVED
CONTEXTUAL_SENSE
NEGATION_RISK
LONG_MULTI_CLAUSE
HACHIMI_GATE_FAILED
USER_HISTORY_RISK
~~~

### Hiệu chỉnh

Ban đầu dùng weighted rules. Khi có corpus review:

- train logistic regression hoặc boosted tree nhỏ;
- label là user accepted/edited/hard-failed;
- calibrate DIRECT_VP cho precision cao;
- giữ hard rules ngoài model;
- version router.

Audit sampling là tùy chọn, mặc định tắt:

~~~toml
[routing]
audit_direct_vp_rate = 0.0
~~~

## 13. LOCAL_PATCH

Nếu VP đúng phần lớn block, không yêu cầu Qwen viết lại toàn bộ.

Response mẫu:

~~~json
{
  "patches": [
    {
      "span_id": "s4",
      "source_start": 18,
      "source_end": 26,
      "replacement": "..."
    }
  ]
}
~~~

Composer chỉ thay token range tương ứng source occurrence. Nếu patch cần thay thứ tự ngoài vùng hoặc phá syntax, nâng lên QWEN_POSTEDIT. Không replace chuỗi target tùy tiện.

## 14. Occurrence constraints

~~~python
class OccurrenceConstraint(BaseModel):
    occurrence_id: str
    source_start: int
    source_end: int
    entry_version_id: str
    entity_id: str | None
    canonical_target: str
    allowed_aliases: list[str]
    policy: Literal["HARD", "PREFERRED", "CONTEXTUAL"]
~~~

- HARD: tên đã xác nhận, số, cảnh giới/vật phẩm cố định.
- PREFERRED: term ưu tiên nhưng cho phép biến thể ngữ pháp.
- CONTEXTUAL: source có nhiều sense; không ép một target mọi nơi.

Guard kiểm tra số occurrence và alignment, không chỉ tìm target substring. Placeholder chỉ bật sau khi test tokenizer/model.

## 15. HachimiMT

Hachimi là candidate engine cho block risk trung bình:

- CTranslate2 INT8 trên CPU;
- model load một lần trong resident subprocess;
- batch theo token budget;
- output qua candidate gate;
- không replace term mù;
- fail gate thì đưa Qwen.

Model card cung cấp ví dụ Transformers và CTranslate2 INT8, đồng thời mô tả model hướng tới giọng convert: [HachimiMT-60-QT](https://huggingface.co/ngocdang83/HachimiMT-60-QT).

## 16. Qwen qua Ollama

Hai mode:

1. LOCAL_PATCH: trả patch theo source offsets.
2. POSTEDIT: trả target blocks với ID giữ nguyên.

Payload gồm source target, read-only context, VP draft, Hachimi candidate nếu có, occurrence constraints, entity ledger, style profile và output JSON Schema.

Ollama Generate API hỗ trợ JSON/JSON Schema qua trường format: [Ollama Generate API](https://docs.ollama.com/api/generate).

Qwen term proposal chỉ là observation, không tự sửa dictionary.

## 17. QA ba lớp

### Invariant gate

Hard error:

- output rỗng/truncated;
- invalid structured output;
- mất/thêm số, tiền, đơn vị, cấp bậc;
- mất phủ định/modal;
- entity hoặc HARD occurrence sai;
- quote/bracket/tag/heading hỏng;
- Hán tự sót ngoài allowlist;
- lặp block;
- prompt leakage;
- block ID thiếu/thừa.

### Candidate acceptability

- source-target alignment coverage;
- semantic anchors thiếu/thừa;
- candidate disagreement;
- robust length deviation;
- untranslated/repetition/language ratio;
- PREFERRED term consistency;
- correction history.

Embedding, back-translation và Qwen self-score chỉ là tín hiệu phụ.

### Chapter consistency audit

- entity có nhiều target;
- alias/xưng hô đổi bất thường;
- cảnh giới/chức danh/vật phẩm không nhất quán;
- speaker/pronoun bất thường;
- duplicated/missing block.

Chỉ auto-fix deterministic khi alignment một-một. Fallback hữu hạn:

~~~text
VP → Hachimi → Qwen → một constrained repair → NEEDS_REVIEW
~~~

## 18. Context và Entity Ledger

~~~text
entity_id
source_forms[]
canonical_target
entity_type
aliases[]
gender/status nếu có bằng chứng
evidence_occurrence_ids[]
state = observed | confirmed | conflicted
~~~

Qwen chỉ đề xuất. Luồng cập nhật:

~~~text
proposal → validator → evidence store → ledger revision
~~~

Gender, quan hệ và speaker không active từ một suy đoán duy nhất.

## 19. Tách ba loại bộ nhớ

1. Dictionary: source → target có thể dùng lặp lại.
2. Entity memory: tên/alias/hệ thống trong một truyện.
3. Translation memory: source + context + glossary + model/prompt → translation.

Không promote translation memory thành dictionary chỉ vì output lặp. Style/xưng hô là profile hoặc memory riêng.

## 20. Learning modes

~~~text
--learn off
--learn observe
--learn safe
~~~

Default đề xuất: safe.

- off: không tạo candidate.
- observe: tạo candidate nhưng không active.
- safe: bootstrap và auto-active entity book-local vượt hard gates.

Không có aggressive mode trong MVP.

## 21. Auto-learning hard gates

Whitelist:

- person;
- place;
- organization/sect;
- realm;
- skill;
- item;
- coined entity book-local.

Manual-only:

- common phrase/idiom;
- verb/adjective/function word;
- single character;
- pronoun/kinship/xưng hô;
- gender inference;
- sentence hoàn chỉnh;
- source đã có manual/base multi-char;
- source có nhiều sense.

Candidate book-auto chỉ qua nếu đồng thời:

1. source là substring thật trong TXT;
2. đủ distinct occurrence/context/chapter;
3. duplicate crawl/rerun bị collapse;
4. normalized target support thống nhất;
5. có ít nhất hai provenance chain độc lập;
6. Qwen evidence độc lập không nhìn Hachimi output;
7. không uncertain, hard fail hoặc truncation;
8. target pass sanitizer;
9. không collision manual/base multi-char;
10. không user reject/tombstone;
11. replay không tăng hard error;
12. không thay block user-approved;
13. chỉ fill unknown/single-char fallback;
14. mọi occurrence ảnh hưởng được index.

Các baseline như 5 occurrence, 2 chapter, 3 context và 90% target support chỉ là config khởi tạo cần calibrate.

## 22. Learning lifecycle

~~~text
OBSERVED → CANDIDATE → SHADOW → VALIDATED → ACTIVE_BOOK_AUTO
             └──────→ REJECTED
ACTIVE_BOOK_AUTO → QUARANTINED
manual edit → SUPERSEDED + ACTIVE_BOOK_MANUAL
~~~

- Reject tạo tombstone.
- Đổi model/prompt/base dictionary buộc evidence revalidate.
- Không expire chỉ dựa trên số ngày.
- Explicit user correction thắng auto evidence.

## 23. Feedback semantics

~~~bash
zhvi review export RUN_ID --format jsonl
zhvi segment accept SEGMENT_ID
zhvi segment correct SEGMENT_ID --file corrected.txt
zhvi term accept CANDIDATE_ID --target "..." --scope book
zhvi term reject CANDIDATE_ID --reason "..."
zhvi term edit ENTRY_ID --target "..."
zhvi feedback apply feedback.jsonl --dry-run
zhvi feedback apply feedback.jsonl --retranslate-affected
~~~

- segment correct khóa final block, không tự tạo term mapping.
- term accept/edit mới là explicit mapping evidence.
- extraction từ sentence diff chỉ tạo shadow proposal.
- không học từ NEEDS_REVIEW, truncated, hard-failed hoặc rejected.
- dry-run hiện dictionary diff, collision và affected blocks.

## 24. Revision và rollback

~~~text
dictionary_revision:
  id, parent_id, status, actor, reason, run_id, checksum

dictionary_event:
  revision_id, action, entry_id, before_json, after_json

term_usage:
  entry_version_id, segment_id, source_start, source_end
~~~

Rollback tạo revision mới chứa inverse events, không xóa lịch sử.

~~~bash
zhvi terms revisions
zhvi terms diff REV_A REV_B
zhvi terms rollback --to REV_A --dry-run
zhvi terms rollback --to REV_A --retranslate-affected
~~~

Affected rerun dùng term_usage + overlap index, stage result, QA rồi mới publish revision/output mới.

## 25. Runtime cho máy 12 GB VRAM

~~~text
CLI controller — một process, SQLite writer duy nhất
Hachimi worker — một resident subprocess CPU
Ollama/Qwen — daemon GPU, concurrency 1
Metrics sampler — một thread nhẹ tùy chọn
~~~

Tôi không thể xác minh Qwen nằm hoàn toàn trong 12 GB VRAM vì chưa có model name, quantization, context và kết quả ollama ps.

Scheduler:

~~~text
bounded planning window
→ VietPhrase/router
→ Hachimi token batches
→ Qwen priority queue
→ ordinal reorder buffer
→ chapter audit
→ checkpoint
~~~

- Không giữ cả cuốn trong RAM.
- Qwen concurrency 1.
- Hachimi batch theo token budget.
- Backpressure khi queue/buffer đầy.
- Ưu tiên ordinal thấp.
- Chỉ overlap CPU/GPU sau benchmark.

Ollama có endpoint liệt kê model đang chạy và runtime info: [Ollama PS API](https://docs.ollama.com/api/ps).

Hachimi subprocess dùng multiprocessing spawn; controller là DB writer; watchdog restart hữu hạn; không truncation input âm thầm.

## 26. Timeout, retry và circuit breaker

Tách preload timeout, warm request timeout, Hachimi batch timeout và export error.

Retry hữu hạn cho connection error, timeout, 429, 5xx.

Không retry vô hạn config error, model not found, OOM cùng payload, invalid source hoặc dictionary corruption.

Invalid JSON: một structured-repair attempt, sau đó NEEDS_REVIEW.

Khi AI lane bắt buộc nhưng unavailable, default pause/fail có state; không âm thầm lấy VP/Hachimi làm final.

## 27. State machine

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> RUNNING
    RUNNING --> PAUSED
    PAUSED --> RUNNING
    RUNNING --> NEEDS_REVIEW
    NEEDS_REVIEW --> RUNNING
    RUNNING --> FAILED
    RUNNING --> COMPLETED
    COMPLETED --> EXPORTED
~~~

Block:

~~~text
PENDING → VP_READY → ROUTED → CANDIDATE_READY → VALIDATED → COMMITTED
nhánh: RETRY_WAIT | NEEDS_REVIEW | FAILED | STALE
~~~

Block chỉ COMMITTED khi output, trace, route, QA và attempt metadata vào cùng transaction.

## 28. SQLite schema tối thiểu

~~~sql
CREATE TABLE source_revisions (
    id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    encoding TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    snapshot_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    source_revision_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL,
    resolved_config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(fingerprint)
);

CREATE TABLE blocks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    chapter_ordinal INTEGER NOT NULL,
    block_ordinal INTEGER NOT NULL,
    source_start INTEGER NOT NULL,
    source_end INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    final_text TEXT,
    qa_json TEXT
);

CREATE TABLE attempts (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    model_digest TEXT,
    prompt_hash TEXT,
    input_hash TEXT NOT NULL,
    output_json TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE route_decisions (
    block_id TEXT PRIMARY KEY,
    route TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    features_json TEXT NOT NULL,
    router_version TEXT NOT NULL
);

CREATE TABLE term_candidates (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    source TEXT NOT NULL,
    proposed_target TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE feedback_events (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    segment_id TEXT,
    candidate_id TEXT,
    entry_id TEXT,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);
~~~

Production bổ sung chapter/structural nodes, evidence typed, revisions/events, term usage, tombstones, manifests và cache.

SQLite WAL cho phép reader tiếp tục trong khi writer append WAL; thiết kế vẫn giữ một controller writer: [SQLite WAL](https://sqlite.org/wal.html).

## 29. Checkpoint và crash recovery

- Transaction theo committed block hoặc batch nhỏ.
- Attempt hoàn tất được cache trước engine tiếp theo.
- Ctrl-C lần 1: ngừng block mới, checkpoint, PAUSED, exit 130.
- Ctrl-C lần 2: thoát ngay; attempt chưa commit chạy lại.
- Khi resume, block RUNNING chưa commit về PENDING.
- Project lock ngăn hai translate process cùng ghi.
- Disk/DB error là fatal; output cũ không bị thay.

Không cần distributed lease cho một foreground CLI.

## 30. Atomic export

Chỉ export final khi mọi block COMMITTED, không hard fail, không review bắt buộc, count/order khớp source và không còn placeholder.

~~~python
def atomic_export(destination: Path, content: bytes) -> str:
    tmp = destination.with_name(destination.name + ".tmp")
    with tmp.open("wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    digest = sha256(content).hexdigest()
    os.replace(tmp, destination)
    fsync_directory(destination.parent)
    return digest
~~~

Temp file phải ở cùng filesystem với destination.

Output ngoài project đã tồn tại cần cờ replace rõ ràng. Partial output phải có tên .partial.txt và sidecar review.

## 31. Progress, stdout và logs

TTY:

~~~text
Ch 38/420 | block 12,480/93,201 | VP 72% H 21% Q 7%
41.2 char/s | ETA 34m | review 6 | retries 1
~~~

- progress/log người đọc ở stderr;
- stdout dành cho JSON;
- non-TTY không animation;
- tôn trọng NO_COLOR;
- --json và --json-events.

Typer hỗ trợ command/subcommand theo type hints: [Typer commands](https://typer.tiangolo.com/tutorial/commands/). Rich hỗ trợ progress nhiều task: [Rich Progress](https://rich.readthedocs.io/en/stable/progress.html).

Log mặc định không ghi toàn source/prompt/raw output. Bật bằng cờ debug-content.

## 32. Manifest

Manifest lưu:

- tool/pipeline/schema version;
- source revision/path/hash/encoding;
- parser version;
- dictionary revision/checksum;
- resolved config/style/profile;
- Qwen name/digest/quantization/context nếu có;
- Hachimi snapshot/tokenizer/CTranslate2;
- prompt/schema/router/QA versions;
- route/cache/retry/review totals;
- time và output hash;
- fallback/degraded events;
- segment-to-run trace reference.

Không lấy được digest thì ghi null/unavailable, không suy đoán.

## 33. Profiles và config

~~~toml
style = "convert-qt"
pipeline = "balanced"
output_policy = "strict-final"
learning = "safe"
~~~

Pipeline:

- fast: ưu tiên VP, fallback hạn chế.
- balanced: VP → patch/Hachimi → Qwen.
- quality: route bảo thủ hơn, fallback nhiều hơn.

Output:

- strict-final: không publish khi hard fail/review bắt buộc.
- best-effort: best candidate + review sidecar.

Precedence:

~~~text
CLI → environment endpoint/runtime → project config
→ named runtime profile → user config → defaults
~~~

config show --resolved hiển thị effective config. Resume dùng config snapshot cũ.

## 34. Exit codes

| Code | Nghĩa |
|---:|---|
| 0 | hoàn tất và final output hợp lệ |
| 2 | CLI usage/config |
| 3 | input/import/parse |
| 4 | dependency/model preflight |
| 5 | lock/state/resume conflict |
| 6 | run failed |
| 7 | review required/partial |
| 8 | export/write error |
| 9 | integrity/verify error |
| 130 | Ctrl-C |
| 143 | SIGTERM |

status mặc định trả 0 nếu query thành công; --require-complete trả code theo state.

## 35. Doctor và benchmark

Doctor kiểm tra dictionary, chapter regex, encoding, SQLite/disk, Hachimi load, Ollama/Qwen, JSON Schema và context admission.

~~~bash
zhvi doctor --project PROJECT
zhvi benchmark runtime --input representative.txt --write-profile workstation-12gb
~~~

Benchmark đo cold/warm Qwen, Hachimi token-batch/beam, end-to-end routes, latency, chars/s, RAM/VRAM, queue, QA fail, crash/resume và reproducibility.

Runtime profile pin theo hardware, Ollama version, Qwen digest/quantization, Hachimi snapshot/CTranslate2 và prompt/schema.

Không chọn batch/thread chỉ theo tốc độ; loại cấu hình vi phạm quality/memory trước.

## 36. Code layout

~~~text
src/zhvi/
├── cli.py
├── config.py
├── project.py
├── document.py
├── pipeline.py
├── scheduler.py
├── state.py
├── export.py
├── vietphrase/
│   ├── importer.py
│   ├── trie.py
│   ├── lattice.py
│   ├── renderer.py
│   └── trace.py
├── routing/
│   ├── features.py
│   ├── rules.py
│   └── model.py
├── engines/
│   ├── hachimi_worker.py
│   └── ollama_qwen.py
├── quality/
│   ├── invariants.py
│   ├── acceptability.py
│   └── chapter_audit.py
├── memory/
│   ├── entities.py
│   ├── terms.py
│   ├── translation.py
│   └── revisions.py
└── review.py
~~~

Chỉ giữ interface ở boundary thay thế được: translation engine, dictionary compiler, state store và exporter.

## 37. Core orchestration

~~~python
def translate_project(project: Project, request: TranslateRequest) -> RunResult:
    preflight(project, request)
    source = import_snapshot(request.source)
    config = resolve_config(project, request)
    book_index = analyze_book(source, config.parser)
    glossary = bootstrap_and_freeze(book_index, config.learning)

    fingerprint = build_run_fingerprint(source, config, glossary)
    run = state.resume_or_create(fingerprint)
    run.pin(glossary=glossary, config=config)

    for chapter in book_index.pending_chapters(run):
        blocks = semantic_segment(chapter, config.segmenter)
        vp_plans = vietphrase.plan_many(blocks, glossary)

        for block, vp in bounded_schedule(blocks, vp_plans):
            decision = router.decide(block, vp, run.context)
            candidate = execute_route(decision, block, vp, run.context)
            accepted = quality.bounded_validate_repair(candidate)
            state.stage_block(run, block, accepted)

        audited = quality.audit_chapter(state.staged_chapter(run, chapter))
        state.commit_chapter(run, audited)
        state.checkpoint_observations(run, chapter)

    final_report = quality.audit_book(run)
    if final_report.publishable:
        output = exporter.atomic_publish(run, request.output)
        state.mark_exported(run, output)
    else:
        state.mark_needs_review(run, final_report)

    return state.result(run)
~~~

## 38. Failure policy

Transient: timeout, reset, Ollama 429/5xx, Hachimi crash lần đầu. Retry hữu hạn + backoff/jitter.

Content failure: invalid JSON, QA hard fail, alignment fail, context overflow, repetition. Một repair rồi NEEDS_REVIEW.

Fatal: snapshot hỏng, DB/disk lỗi, dictionary corruption, model/config thiếu, export integrity fail.

Không silent fallback hoặc tự đổi model. Degraded behavior phải là policy rõ và ghi manifest.

## 39. Test bắt buộc

### Document

- encoding, CRLF/LF, blank line, heading;
- quote/ngoặc lồng, đoạn dài;
- lossless structural round-trip.

### VietPhrase

- overlapping phrase/top-K lattice;
- scope/trust precedence;
- HARD/PREFERRED/CONTEXTUAL;
- book auto fill-only;
- single-char fallback/collision.

### Pipeline

- DIRECT_VP không gọi model;
- patch chỉ đổi allowed span;
- Hachimi fail gọi Qwen;
- Qwen fail → một repair → review;
- snapshot bất biến;
- chapter consistency.

### Recovery/cache/export

- kill tại mọi transition;
- Ctrl-C, restart Ollama, Hachimi crash, disk full, OOM;
- resume không gọi lại attempt đã commit;
- same fingerprint no-op;
- append chương tái dùng phần cũ;
- relevant term invalid đúng block;
- output cũ không hỏng khi run mới fail;
- không publish partial như final;
- block không thiếu/nhân đôi/reorder.

### Learning

- duplicate evidence không bơm support;
- Qwen nhìn Hachimi không tính independent;
- reject tạo tombstone;
- sentence correction không auto tạo term;
- rollback tạo inverse revision;
- affected rerun đúng.

### Golden corpus

Bao phủ tiên hiệp/huyền huyễn, đô thị, hội thoại, tỉnh lược, phủ định, 把/被, thành ngữ, tên hiếm, cảnh giới/pháp bảo, số/tiền/đơn vị và câu nhiều mệnh đề.

Metric chính: số ký tự user sửa/1.000 ký tự, accept rate theo route, entity consistency, locked violation, DIRECT_VP false-negative, route ratio, chars/s và time/chapter.

## 40. Thứ tự triển khai

### Milestone 1 — CLI deterministic

- project/import/snapshot;
- lossless parser;
- dictionary importer;
- VietPhrase lattice/trace;
- SQLite/checkpoint;
- VP-only;
- atomic export;
- crash/resume tests.

### Milestone 2 — Hybrid

- Hachimi resident worker;
- Ollama structured client;
- router bốn route;
- occurrence constraints;
- QA block/chapter;
- review JSONL.

### Milestone 3 — Learning safe

- tách entity/term/translation memory;
- discovery/bootstrap;
- book auto fill-only;
- evidence/revision/tombstone/rollback;
- affected rerun.

### Milestone 4 — Calibration

- review CLI;
- golden corpus;
- router model nhỏ;
- runtime benchmark/profile;
- hiệu chỉnh threshold.

## 41. Default đề xuất

~~~toml
style = "convert-qt"
pipeline = "balanced"
output_policy = "strict-final"
learning = "safe"

[input]
encoding = "utf-8"
chapter_detection = "auto"

[routing]
audit_direct_vp_rate = 0.0

[runtime]
qwen_concurrency = 1
hachimi_device = "cpu"
hachimi_compute_type = "int8_float32"
overlap = "auto"

[failure]
engine_unavailable = "pause"
content_failure = "review"
max_content_repair = 1
~~~

Token budget, Hachimi batch tokens, timeout và context không gắn cứng trước benchmark.

## 42. Cần cung cấp trước khi viết code

1. Output ollama list và ollama ps.
2. Dictionary files và 5–10 dòng mẫu mỗi loại.
3. Một TXT thật khoảng 2–5 chương.
4. Heading chương crawler giữ lại.
5. Python/Ubuntu version.
6. CPU, RAM và GPU chính xác.
7. Chỉ convert hay thêm profile hiện đại.

## 43. Kết luận

Thiết kế phù hợp nhất cho yêu cầu hiện tại là:

**một CLI project-oriented, two-pass, lossless, resumable và reproducible; VietPhrase tạo lattice/trace, Hachimi làm candidate, Qwen chỉ patch/post-edit block rủi ro; dictionary được đóng băng theo run và tự học chỉ tạo book-local revision có hard gates.**

Giới hạn: không thể phát hiện hoàn hảo mọi câu VietPhrase sai nghĩa chỉ bằng rule và coverage. Cơ chế thực tế là selective routing + abstain + QA + feedback calibration + audit sampling tùy chọn.

## 44. Nguồn công nghệ đã kiểm tra

- [Ollama Generate API](https://docs.ollama.com/api/generate)
- [Ollama running models API](https://docs.ollama.com/api/ps)
- [HachimiMT-60-QT model card](https://huggingface.co/ngocdang83/HachimiMT-60-QT)
- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html)
- [Typer commands](https://typer.tiangolo.com/tutorial/commands/)
- [Rich progress display](https://rich.readthedocs.io/en/stable/progress.html)
