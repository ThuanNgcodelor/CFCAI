# Kế hoạch đưa CFC FAQ tới trạng thái PASS

Ngày lập kế hoạch: 26/10/2026  
Phạm vi: `CFC_Co_Bay_FAQ.md`, pipeline CFC, conversation state, retrieval,
workflow và kiểm thử trước khi bật production.

## 1. Kết luận ngắn gọn

Hệ thống chưa thất bại vì model “không đủ thông minh”. Nguyên nhân chính là dữ
liệu và pipeline chưa có một hợp đồng chung:

1. File FAQ đang trộn câu trả lời tĩnh, quy tắc nghiệp vụ và hướng dẫn nông học.
2. Toàn bộ bản ghi Markdown mặc định mang `category=faq`, trong khi pipeline lại
   tìm theo các nhánh `product`, `dealer`, `agronomy`, `price` khác nhau.
3. FAQ hiện chưa được publish vào read model production: **0 bản ghi active**.
4. Intent sai khiến câu hỏi không đi tới FAQ, dù retrieval có thể tìm thấy nó.
5. Câu trả lời trong nguồn còn xung đột persona `anh/chị`: 36/47 dòng.
6. Có 3 dòng chưa có câu trả lời và 18 dòng chứa tuyên bố nông học mạnh cần
   người có chuyên môn duyệt.

Vì vậy không nên sửa bằng `if câu hỏi == ...`. Hướng xử lý là đưa routing và
policy thành metadata cấu hình, giữ Python làm bộ quyết định nghiệp vụ, còn model
chỉ hiểu ngôn ngữ và diễn đạt từ dữ liệu đã duyệt.

## 2. Baseline đang có

| Hạng mục | Hiện tại | Mục tiêu cuối |
|---|---:|---:|
| Dòng FAQ nguồn | 47 | 47 được phân loại rõ |
| Dòng có đáp án | 44 | 47 hoặc dòng thiếu được disable có lý do |
| Biến thể câu hỏi có đáp án | 119 | 100% có expected route/result |
| Retrieval Top-1 | 109/119 | 119/119 trên câu mẫu nguồn |
| Retrieval Top-3 | 118/119 | 119/119 trên câu mẫu nguồn |
| Cách ly ZEO | 119/119 | luôn 100% |
| FAQ được publish | 0 | chỉ bản ghi đã review và APPROVED |
| Runtime pass toàn diện | 0/44 | 44/44 hoặc số bản ghi APPROVED tương ứng |
| Dòng xung đột persona | 36 | 0 |
| Dòng thiếu đáp án | 3 | 0 active |

Lưu ý: “runtime pass” không đồng nghĩa mọi câu phải giống nguyên văn. Câu tĩnh có
thể so exact/semantic; câu giá, đại lý, đặt hàng và tư vấn phải được chấm theo kết
quả nghiệp vụ và policy.

## 3. Kiến trúc đích

```text
Tin nhắn + lịch sử hội thoại
    -> Safety rule ưu tiên (giá, người thật, takeover)
    -> Intent/slot JSON có evidence
    -> Intent transition + merge state
    -> Chọn answer mode từ metadata
       ├── DIRECT_FAQ       -> approved FAQ
       ├── PRODUCT_LOOKUP   -> approved catalog
       ├── DEALER_LOOKUP    -> CRM dealer resolver
       ├── PRICE_HANDOFF    -> handoff, tuyệt đối không báo giá
       └── AGRI_ADVICE      -> approved agronomy + required slots
    -> Composer
    -> Output policy validator
    -> Durable outbox + final ownership guard
```

Không nhánh nào được phép bỏ qua `page_id`, trạng thái `APPROVED`, output guard
hoặc final ownership guard.

### 3.1. Hiện tại dữ liệu đi vào hệ thống như thế nào

| Nguồn | Vị trí/đầu vào hiện tại | Cách nạp hiện tại | Nơi runtime đọc |
|---|---|---|---|
| CFC Markdown FAQ | `CFC_Co_Bay_FAQ.md` ở root repository | Gọi thủ công `POST /admin/catalog/import-markdown` | PostgreSQL `knowledge_records` sau approve/publish |
| CFC Excel | `docs/CfcCoBayN8n.xlsx` | Gọi thủ công `POST /admin/catalog/import-excel` | PostgreSQL read model đã publish |
| ZEO Excel | `docs/ZeoN8n.xlsx` | Cùng endpoint import Excel | PostgreSQL, lọc `page_id=ZEO` |
| Khu vực hành chính | `config/normalization/administrative_areas.json` | Đọc khi process khởi động | Bộ phân giải địa danh trong worker |
| Danh bạ hỗ trợ | `config/business/support_contacts.json` | Đọc khi process khởi động | Composer/workflow |
| CRM AMIS | API MISA AMIS | Gọi thủ công `POST /admin/misa/sync` | Redis `cfc:dealers:*`, `cfc:products:*`, `cfc:orders:*` |

Các giới hạn hiện tại phải được xử lý trong phase dữ liệu:

- API container chỉ mount riêng file Markdown ở root; worker không mount file
  này vì worker chỉ nên đọc read model đã publish.
- Build/start Docker **không tự import** Markdown hoặc Excel.
- Endpoint Markdown chỉ stage dữ liệu vào `QUARANTINED`, không tự publish.
- CRM warmer hiện chỉ chạy khi có lệnh gọi API; chưa có scheduler một giờ thực sự.
- CRM đang ghi đè một số Redis key trực tiếp, chưa có current-version pointer,
  TTL/freshness policy và last-known-good swap đầy đủ.
- `GET /admin/misa/status` dựa một phần vào bộ nhớ process nên có thể trở lại
  `pending` sau khi API restart dù Redis vẫn còn snapshot.

### 3.2. Cấu trúc thư mục dữ liệu (đã triển khai ở F2)

Đưa file nguồn ra khỏi root và gom vào một cây thư mục có ý nghĩa rõ ràng:

```text
data/
└── sources/
    ├── manifest.yaml
    ├── cfc/
    │   ├── faq/
    │   │   └── CFC_Co_Bay_FAQ.md
    │   └── catalog/
    │       └── CfcCoBayN8n.xlsx
    └── zeo/
        ├── faq/
        └── catalog/
            └── ZeoN8n.xlsx
```

Quy ước:

- `data/sources` chỉ chứa nguồn đầu vào do người quản trị cập nhật.
- `manifest.yaml` khai báo `source_id`, `page_id`, loại importer, path/glob,
  mapping version và chính sách review; thêm nguồn mới bằng cấu hình, không sửa
  application code.
- Các file test sinh ra vẫn nằm trong `tests/fixtures`; report vẫn nằm trong
  `reports`; tuyệt đối không dùng hai thư mục này làm dữ liệu production.
- File nguồn được mount read-only vào một service loader. API/worker production
  không cần đọc file nguồn trên mỗi tin nhắn.
- Không để secret, dump CRM, dữ liệu khách hoặc bảng giá trong `data/sources`.

Manifest hiện được triển khai theo cấu trúc:

```yaml
version: 1
sources:
  - id: cfc-faq
    page_id: CFC
    kind: markdown_faq
    path: data/sources/cfc/faq/CFC_Co_Bay_FAQ.md
    mapping: config/data_sources/markdown_mapping.json
    auto_stage: true
    auto_publish: false
  - id: cfc-excel
    page_id: CFC
    kind: excel_catalog
    path: data/sources/cfc/catalog/CfcCoBayN8n.xlsx
    auto_stage: true
    auto_publish: false
  - id: zeo-excel
    page_id: ZEO
    kind: excel_catalog
    path: data/sources/zeo/catalog/ZeoN8n.xlsx
    auto_stage: true
    auto_publish: false
```

`auto_stage=true` chỉ có nghĩa là tự tạo batch kiểm duyệt khi checksum thay đổi.
Nó **không** đồng nghĩa tự approve hoặc tự publish.

### 3.3. Data bootstrap khi build/start

Không import dữ liệu trong bước `docker build`: lúc build chưa có PostgreSQL,
không có transaction/review và cùng một image có thể chạy ở nhiều môi trường.
Thay vào đó cần một one-shot service `data-loader` chạy sau khi PostgreSQL healthy:

```text
docker build
    -> start PostgreSQL/Redis
    -> data-loader validate manifest + source files
    -> compare checksum với import_batches
    -> stage CHỈ nguồn mới/thay đổi vào QUARANTINED
    -> exit 0
    -> API/worker start và chỉ đọc publication đang ACTIVE
```

Chính sách theo môi trường:

| Môi trường | Validate | Auto-stage | Auto-approve | Auto-publish |
|---|---:|---:|---:|---:|
| Test | Có | Fixture tạm | Có trong DB test | Có trong DB test |
| Development | Có | Có thể bật | Không | Không |
| Staging | Có | Có | Không | Không |
| Production | Có | Chỉ qua deploy job có log | Không | Không |

Nếu loader lỗi, publication đang active vẫn được giữ nguyên. Không được xóa hoặc
thay read model đang chạy chỉ vì file mới bị lỗi.

### 3.4. Giao diện lệnh vận hành

Các endpoint dưới đây **đã tồn tại** và có thể dùng ở thời điểm hiện tại:

```bash
# Stage các nguồn Markdown đã cấu hình; chưa publish
curl -sS -X POST http://localhost:8000/admin/catalog/import-markdown

# Warm CRM AMIS vào Redis bằng token nội bộ
curl -sS -X POST \
  -H "X-Internal-Token: <AMIS_SYNC_INTERNAL_TOKEN>" \
  http://localhost:8000/admin/misa/sync

# Xem trạng thái warmer trong process API hiện tại
curl -sS http://localhost:8000/admin/misa/status
```

Các endpoint catalog hiện chưa phải giao diện vận hành production hoàn chỉnh;
chỉ gọi trong mạng nội bộ/local cho tới khi có auth/RBAC và audit. Không public
chúng ra Internet chỉ vì đường dẫn bắt đầu bằng `/admin`.

Các lệnh dưới đây đã được triển khai trong Phase F2:

```bash
# Kiểm tra manifest, schema, checksum và policy; không ghi DB
docker compose --profile data run --rm data-loader validate --all

# Tự tìm file mới/thay đổi và stage vào QUARANTINED
docker compose --profile data run --rm data-loader stage --changed

# Xem batch/diff cần người duyệt
docker compose --profile data run --rm data-loader status --page CFC

# Approve và publish phải là hai lệnh riêng, có actor/audit
docker compose --profile data run --rm data-loader approve \
  --page CFC --batch <batch_id> --actor <admin>
docker compose --profile data run --rm data-loader publish \
  --page CFC --batch <batch_id> --actor <admin>

# CRM là job riêng, không trộn với file import
docker compose --profile data run --rm crm-warmer sync
docker compose --profile data run --rm crm-warmer status
```

Có thể bọc các lệnh trên bằng `make data-validate`, `make data-stage` và
`make crm-warm`, nhưng CLI/service bên dưới mới là contract chính để CI/CD dùng.

### 3.5. Luồng CRM warm đích

CRM không cần thả file vào thư mục. Nó phải được pull bằng job riêng:

```text
MISA API
  -> fetch vào snapshot tạm theo sync_id
  -> validate count/schema/page/GPS
  -> ghi toàn bộ version mới
  -> atomic switch current pointer
  -> lưu sync metadata + freshness
  -> dọn version cũ sau retention
```

Yêu cầu vận hành:

- Manual command để warm ngay khi cần.
- Scheduler cấu hình được, ví dụ mỗi 60 phút; dùng distributed lock để không có
  hai job warm đồng thời.
- Không xóa last-known-good snapshot nếu AMIS timeout, trả rỗng hoặc validation
  fail.
- Status phải đọc từ Redis/PostgreSQL, không chỉ từ memory của API process.
- Có `synced_at`, record counts, checksum, duration, source version và error cuối.
- Có freshness threshold/alert; dữ liệu stale vẫn phải được ghi rõ trong log và
  workflow không được gọi đại lý là “gần nhất” nếu bằng chứng không đủ.
- Không đưa raw CRM payload, giá hoặc PII dư thừa vào prompt.

### 3.6. Trải nghiệm cập nhật dữ liệu sau khi hoàn thành F2

Quy trình mong muốn cho anh/chị sẽ chỉ còn:

1. Chép/sửa file ở đúng `data/sources/<page>/<type>/`.
2. Chạy `data-loader validate --all`.
3. Chạy `data-loader stage --changed`; file không đổi sẽ tự bỏ qua theo checksum.
4. Xem diff/report và duyệt batch.
5. Publish; API/worker nhận read model mới mà không cần rebuild image.
6. Nếu sai, rollback publication trước; sửa file và tạo batch mới sau.

CRM là quy trình tách biệt: chạy `crm-warmer sync` hoặc để scheduler chạy; không
copy dữ liệu CRM thành file Markdown/Excel và không rebuild image.

## 4. Phân loại dữ liệu đề xuất

Việc phân loại phải nằm trong Markdown/mapping hoặc record metadata, không nằm
trong chuỗi `if/elif` theo câu hỏi.

| Nhóm | Ví dụ dòng | Answer mode | Nguồn sự thật chính |
|---|---|---|---|
| Thông tin tĩnh | 1, 7, 8, 19 | `DIRECT_FAQ` | FAQ đã duyệt |
| Danh mục/sản phẩm | 2, 9, 10, 34, 43 | `PRODUCT_LOOKUP` hoặc `DIRECT_FAQ` | Catalog + FAQ |
| Giao nhận/mua hàng/hỗ trợ | 3–6, 13–18 | workflow tương ứng | Quy tắc nghiệp vụ + state |
| Giá/công nợ | 11, 30–33 | `PRICE_HANDOFF` | Không đưa giá vào model |
| Đại lý | 12 | `DEALER_LOOKUP` | CRM/address/GPS |
| Tư vấn nông học | 20–29, 35–47 | `AGRI_ADVICE` | Nội dung chuyên môn đã duyệt |

Danh sách trên là phân loại khởi đầu để review, chưa phải phê duyệt chuyên môn.

## 5. Các phase triển khai

### Phase F0 — Đóng baseline và hợp đồng chấm điểm

**Mục tiêu:** Có một mốc đo cố định để mọi thay đổi sau này được so sánh công
bằng.

**Công việc**

- Giữ fixture sinh tự động từ Markdown; cấm sửa tay JSON fixture.
- Mỗi case phải có: `case_id`, câu hỏi mẫu, answer mode dự kiến, expected intent,
  expected source/result và policy bắt buộc.
- Tách ba kiểu assertion:
  - `EXACT`: giờ mở cửa, địa chỉ, website sau khi được xác nhận.
  - `SEMANTIC_GROUNDED`: nội dung sản phẩm/tư vấn được phép diễn đạt lại nhưng
    không được thêm fact.
  - `WORKFLOW_OUTCOME`: giá, đại lý, handoff, order; kiểm tra state và hành động,
    không ép câu văn nguyên bản.
- Lưu baseline JSON/Markdown sau mỗi lần chạy, có timestamp và commit SHA nếu có.

**Gate PASS**

- 47/47 dòng nguồn có test case.
- 129/129 câu hỏi, kể cả dòng thiếu đáp án, được ghi nhận rõ.
- Chạy lặp lại cùng commit cho kết quả xác định ở phần deterministic.
- Không gửi Messenger và không ghi production trong evaluator.

**Ánh xạ ROADMAP:** nền kiểm thử cho Phase 4, 5, 6 và 8.

---

### Phase F1 — Làm sạch và quản trị nguồn FAQ

**Trạng thái 26/10/2026: PASS trong phạm vi an toàn.** Đủ 47/47 governance
record; 44 đáp án đã chuẩn hóa persona; 3 dòng thiếu và các claim chưa duyệt bị
`source_active=false`. Chỉ 8 workflow record an toàn đủ điều kiện active, nhưng
batch Markdown vẫn đang `QUARANTINED` và chưa được publish.

**Mục tiêu:** Biến Markdown từ tài liệu tham khảo thành nguồn dữ liệu có thể
publish an toàn.

**Công việc**

- Bổ sung metadata theo từng dòng, tối thiểu:
  - `Intent`
  - `Category`
  - `Response mode`
  - `Risk level`
  - `Profile slots`/required slots
  - `Audience`
  - `Active`
  - nguồn kiểm chứng, người duyệt, ngày duyệt nếu là khuyến nghị nông học.
- Chuẩn hóa persona trong đáp án:
  - bot: `em` hoặc `bên em`;
  - khách: chỉ `anh/chị`;
  - cấm `bạn`, `chị/em`, `chị/chú`, `cô/bác`, `Anh/chị ơi` và đảo vai nói.
- Hoàn thiện hoặc disable có lý do các dòng 4, 17, 19.
- 18 dòng có số liệu/tuyên bố mạnh phải được chuyên gia duyệt. Khi chưa duyệt,
  giữ `QUARANTINED` hoặc `Active=false`.
- Xóa hoặc sửa các khẳng định tuyệt đối không có căn cứ như “100%”, “hoàn toàn”,
  thời gian/liều lượng chắc chắn nếu không có tài liệu chứng minh.
- Không lưu bảng giá hoặc con số giá trong FAQ customer-facing.

**Gate PASS**

- 0 dòng active thiếu đáp án.
- 0 vi phạm persona trong nguồn active.
- 0 placeholder kỹ thuật.
- 0 tuyên bố nông học rủi ro cao được active khi chưa có review metadata.
- Mọi dòng active có stable ID và provenance.

**Điểm cần con người ký duyệt:** nội dung nông học, địa chỉ/giờ làm việc/website,
chính sách giao nhận và câu trả lời cho 3 dòng đang thiếu.

**Ánh xạ ROADMAP:** Phase 3 và Phase 6.

---

### Phase F2 — Import, review, publish và rollback

**Trạng thái 26/10/2026: PASS kỹ thuật.** Manifest/loader/CLI/audit/idempotency,
Docker data services và CRM atomic snapshot đã được triển khai và test. Batch FAQ
thật đã stage nhưng không auto-approve/publish.

**Mục tiêu:** FAQ đã làm sạch đi qua đúng vòng đời dữ liệu, không chép thẳng vào
runtime.

**Công việc**

- Chuyển nguồn vào cây `data/sources` và tạo manifest page-scoped như Mục 3.
- Tạo one-shot `data-loader` có các lệnh `validate`, `stage`, `status`, `approve`,
  `publish`, `rollback`; mọi thao tác thay đổi trạng thái phải có actor/audit.
- Docker Compose mount `data/sources` read-only cho loader; API/worker chỉ đọc
  read model và không quét file trên mỗi request/tin nhắn.
- Startup/deploy có thể gọi `stage --changed`, nhưng luôn giữ
  `auto_publish=false` ngoài test.
- Nâng mapping version khi schema metadata thay đổi.
- Import idempotent vào `QUARANTINED` với checksum/source row.
- Tạo báo cáo diff giữa version đang publish và version mới.
- Review theo record hoặc batch; chỉ `APPROVED + active + audience=customer`
  được vào read model.
- Publish atomically và giữ version trước để rollback.
- Kiểm tra CFC FAQ không xuất hiện khi truy vấn bằng `page_id=ZEO`.

**Gate PASS**

- Import hai lần không nhân đôi record.
- Số record staged bằng đúng số dòng đủ điều kiện.
- Record thiếu/không duyệt không thể retrieval.
- Publish/rollback khôi phục chính xác version trước.
- CFC/ZEO isolation 100%.
- File không đổi được skip theo checksum; file lỗi không ảnh hưởng publication
  đang active.
- Development/staging/prod không thể auto-publish chỉ bằng restart container.
- Lệnh CRM warmer độc lập có distributed lock, atomic snapshot và last-known-good.
- Restart API không làm mất trạng thái sync/freshness của CRM.

**Lệnh gate chính**

```bash
pytest tests/integration/test_markdown_importer.py
pytest tests/integration/test_excel_importer.py
pytest tests/integration/test_knowledge_retrieval.py
```

**Ánh xạ ROADMAP:** Phase 3, bất biến Data Staging.

---

### Phase F3 — Intent, slot và hội thoại nhiều lượt

**Mục tiêu:** Câu hỏi phải đi đúng workflow trước khi retrieval được đánh giá.

**Công việc**

- Địa danh được phân giải trước marker từ khóa; `Rạch Giá` không được biến thành
  intent hỏi giá.
- Safety precedence cố định cho `PRICE_INQUIRY`, `HUMAN_REQUEST`, takeover.
- Qwen chỉ trả structured JSON; schema reject output lỗi hoặc thiếu evidence.
- Expected intent/answer mode lấy từ metadata, không map riêng từng câu trong code.
- Merge slots theo workflow và có transition rõ khi người dùng đổi nhu cầu.
- Follow-up ngắn phải dùng state đúng cách:
  - `thới lai` tiếp tục dealer lookup;
  - `30 tấn` bổ sung quantity cho price workflow;
  - `rải mít` chuyển sang/tạo nhánh tư vấn cây mít thay vì bị khóa vĩnh viễn ở giá.
- Restart worker không làm mất state; test độc lập phải reset conversation rõ ràng.

**Gate PASS**

- Critical intent `PRICE/HUMAN/DEALER`: 100% trên bộ regression.
- Tổng intent accuracy trên câu mẫu nguồn: tối thiểu 95%.
- Slot quan trọng (`product`, `crop`, `stage`, `location`, `quantity`, `phone`):
  F1 tối thiểu 95% trên fixture có nhãn.
- Bốn transcript đã ghi nhận không còn intent override hoặc lặp vô hạn.
- Ollama timeout/JSON lỗi luôn fallback an toàn.

**Lệnh gate chính**

```bash
pytest tests/eval/test_qwen_understanding.py
pytest tests/integration/test_aggregation_handoff.py
```

**Ánh xạ ROADMAP:** Phase 2 và Phase 4.

---

### Phase F4 — Retrieval theo miền dữ liệu

**Mục tiêu:** Tìm đúng record sau khi đã biết intent; không dùng một bảng xếp hạng
chung cho mọi loại dữ liệu.

**Công việc**

- Tạo strategy/ranker riêng cho `faq`, `product`, `agronomy`, `dealer`.
- Exact stable phrase/alias trước; lexical normalized sau; semantic search chỉ là
  lớp bổ sung.
- Câu hỏi mẫu khai báo trong record phải trỏ đúng record một cách deterministic.
- Thêm minimum score, margin giữa Top-1/Top-2 và ambiguity result.
- Nếu confidence thấp: hỏi lại hoặc handoff, không lấy đại một đáp án.
- Product facts lấy từ catalog; dealer lấy CRM resolver; FAQ không được lấn quyền
  price/dealer workflow.
- Mọi truy vấn luôn lọc `page_id`, `APPROVED`, `audience`, `active`.

**Gate PASS**

- Câu mẫu nguồn: Top-1 **119/119**, Top-3 **119/119**.
- Bộ paraphrase độc lập không dùng để build alias: Top-1 >= 90%, Top-3 >= 98%.
- 0 CFC/ZEO leakage.
- 0 record quarantined/inactive xuất hiện.
- 0 false match từ từ chung như `giá`, `sản phẩm`, `gần nhất`, `Giang`.

**Lệnh gate chính**

```bash
RUN_CFC_FAQ_EVAL=1 pytest tests/eval/test_cfc_faq_cases.py
pytest tests/integration/test_knowledge_retrieval.py
```

**Ánh xạ ROADMAP:** Phase 6.

---

### Phase F5 — Workflow và response policy

**Mục tiêu:** Record đúng phải tạo ra hành vi đúng và câu trả lời phù hợp khách
hàng.

**Công việc theo workflow**

- `DIRECT_FAQ`: trả fact đã duyệt, tối đa 1–3 câu.
- `PRODUCT_LOOKUP`: exact SKU/formula -> alias -> ambiguity clarification; không
  bịa sản phẩm ngoài catalog.
- `PRICE_HANDOFF`: không nêu giá; tạo handoff; hỏi tối đa một thông tin còn thiếu;
  chỉ xác nhận số điện thoại khi slot phone thật sự có.
- `DEALER_LOOKUP`: location exact -> tỉnh cha -> GPS khi đủ tọa độ; tối đa 2–3 đại
  lý có địa chỉ đủ căn cứ; không nói “gần nhất” nếu không chứng minh được.
- `AGRI_ADVICE`: yêu cầu crop + stage/problem; chỉ dùng record chuyên môn đã duyệt;
  thiếu dữ kiện thì hỏi lại, không tự dựng phác đồ.
- `ORDER/CONTACT/HUMAN`: không nói đã chuyển/đã gọi/đã ghi nhận nếu chưa có event
  hoặc task tương ứng.

**Output validator chung**

- Chặn `{...}`, `{{...}}`, `[...]`, `${...}` và biến có dấu gạch dưới escape.
- Chặn giá tiền, phone ngoài allowlist, thuật ngữ nội bộ như `snapshot CRM`.
- Chặn persona sai và các lời hứa chưa có căn cứ.
- Chặn claim mới không có trong selected record/slots.
- Vi phạm bất kỳ rule nào thì dùng fallback an toàn theo workflow.

**Gate PASS**

- 0 price hallucination.
- 0 placeholder/thuật ngữ nội bộ.
- 0 xác nhận phone giả.
- 0 sản phẩm hoặc đại lý không có nguồn.
- 0 persona violation trên toàn bộ output eval.
- Mọi side effect như handoff/outbox có assertion trong test, không chỉ chấm text.

**Lệnh gate chính**

```bash
pytest tests/integration/test_workflows.py
pytest tests/unit/test_safe_pipeline.py
```

**Ánh xạ ROADMAP:** Phase 5.

---

### Phase F6 — Regression toàn bộ FAQ và hội thoại thật

**Mục tiêu:** Chứng minh toàn chuỗi chạy đúng, không chỉ từng module.

**Công việc**

- Chạy 119 câu mẫu ở chế độ isolated runtime.
- Mỗi dòng có verdict và failure reason chuẩn hóa:
  `ROUTING`, `SLOT`, `RETRIEVAL`, `WORKFLOW`, `GROUNDING`, `OUTPUT_POLICY`.
- Chạy thêm bộ câu paraphrase chưa xuất hiện trong source.
- Replay bốn đợt test Messenger đã ghi nhận, mỗi đợt bắt đầu bằng state sạch.
- Thêm test nhiều lượt, restart worker, duplicate webhook và takeover race.
- So sánh report mới với baseline; fail CI nếu metric giảm.

**Gate PASS bắt buộc trước pilot**

- 100% case nguồn active đạt expected outcome.
- 100% bốn transcript regression pass.
- 0 price, leakage, duplicate reply, post-takeover reply.
- 0 output policy violation.
- Full test suite không có lỗi mới; lỗi hạ tầng/test cũ phải được tách và xử lý,
  không được bỏ qua âm thầm.

**Lệnh gate chính**

```bash
python scripts/build_cfc_faq_test_cases.py --check
python scripts/evaluate_cfc_faq.py --live --check-production
pytest tests/eval/test_regression_full.py
pytest
```

**Ánh xạ ROADMAP:** Phase 8.

---

### Phase F7 — Shadow, canary và production

**Mục tiêu:** Đưa bản đã pass vào vận hành có khả năng dừng và rollback.

**Công việc**

- Publish version FAQ đã ký duyệt; lưu version rollback.
- Chạy shadow: tạo đáp án nhưng không gửi khách, so với nhân viên/expected result.
- Canary chỉ Page CFC và một nhóm intent ít rủi ro trước (`DIRECT_FAQ`).
- Sau đó mới mở product, dealer; agronomy mở cuối cùng sau chuyên gia sign-off.
- Theo dõi intent distribution, no-match, handoff, output guard rejection, duplicate,
  outbox failure và CRM freshness.
- Kill switch, pause/resume, takeover và rollback phải được diễn tập.

**Gate PASS production**

- Shadow không có lỗi safety nghiêm trọng.
- Canary đạt ngưỡng trong khoảng quan sát đã thống nhất với chủ hệ thống.
- T01–T12 đạt 100%.
- Backup/restore, rollback FAQ, kill switch và takeover được chứng minh bằng log.
- Có business sign-off; không tự động mở rộng rollout.

**Ánh xạ ROADMAP:** Phase 7 và Phase 8.

## 6. Thứ tự PR/triển khai đề xuất

| PR | Nội dung | Phụ thuộc | Có thể coi là xong khi |
|---|---|---|---|
| PR-FAQ-1 | Schema test case + failure taxonomy | F0 | Baseline deterministic |
| PR-FAQ-2 | Làm sạch Markdown + metadata | PR-FAQ-1 | F1 pass và được duyệt |
| PR-DATA-1 | `data/sources`, manifest, loader validate/stage | PR-FAQ-1 | File mới tự stage, file cũ tự skip |
| PR-DATA-2 | Approve/publish/rollback CLI + audit | PR-DATA-1, PR-FAQ-2 | F2 file lifecycle pass |
| PR-DATA-3 | CRM job, scheduler, atomic snapshot, freshness | PR-DATA-1 | F2 CRM lifecycle pass |
| PR-FAQ-4 | Intent transition + state regression | PR-FAQ-1 | F3 pass |
| PR-FAQ-5 | Domain retrieval/ranking | PR-DATA-2, PR-FAQ-4 | F4 pass |
| PR-FAQ-6 | Workflow/composer/output guard | PR-FAQ-4, PR-FAQ-5 | F5 pass |
| PR-FAQ-7 | Full replay/eval report | PR-FAQ-6 | F6 pass |
| PR-FAQ-8 | Shadow/canary/runbook | PR-FAQ-7 | F7 sign-off |

Không gộp PR-DATA-1 tới PR-FAQ-6 thành một thay đổi lớn. Khi một gate fail, sửa
đúng tầng gây lỗi; không thêm câu điều kiện theo câu hỏi để làm test xanh.

## 7. Cách anh/chị nghiệm thu mà không cần đọc code

Sau mỗi phase cần nhận đúng bốn artefact:

1. Bảng “trước/sau” theo metric của phase.
2. Báo cáo case fail còn lại, có câu hỏi, expected, actual và failure reason.
3. Lệnh test cùng kết quả pass/fail nguyên bản.
4. Danh sách dữ liệu cần anh/chị hoặc chuyên gia nghiệp vụ ký duyệt.

Trạng thái chỉ dùng ba mức:

- `PASS`: toàn bộ gate đạt.
- `PARTIAL`: code đã có nhưng còn ít nhất một gate chưa đạt.
- `BLOCKED`: thiếu phê duyệt nghiệp vụ hoặc phụ thuộc bên ngoài; không được ghi
  thành PASS.

## 8. Definition of Done cuối cùng

Hạng mục FAQ chỉ hoàn thành khi đồng thời đạt tất cả điều kiện:

- [ ] Nguồn active không thiếu đáp án, không sai persona, không có claim chưa duyệt.
- [ ] Import/publish/rollback idempotent, có provenance.
- [ ] Câu mẫu nguồn retrieval Top-1 100%.
- [ ] Intent/slot đạt ngưỡng F3 và bốn transcript cũ pass.
- [ ] Mỗi answer mode chạy đúng workflow, không hardcode câu hỏi.
- [ ] Zero price hallucination và zero CFC/ZEO leakage.
- [ ] Zero placeholder, internal term, fake confirmation và unsupported promise.
- [ ] Full regression, takeover, duplicate và restart tests pass.
- [ ] Shadow/canary, rollback và kill switch được nghiệm thu.
- [ ] Chuyên gia ký duyệt các nội dung nông học trước khi mở cho khách thật.

Chỉ khi toàn bộ checklist trên được tích bằng bằng chứng test/log thì mới được
gọi là “pass hoàn toàn”.
