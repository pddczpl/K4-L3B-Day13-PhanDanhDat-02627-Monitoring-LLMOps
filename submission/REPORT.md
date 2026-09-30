# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Chỉ cần 3 output text và 5 ảnh runtime; dùng đường dẫn tương đối, ví dụ `evidence/03-incident-trace.png`.

## 1. Thông tin học viên

- **Họ và tên:** Phan Danh Đạt
- **MSSV:** 02627
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/pddczpl/K4-L3B-Day13-PhanDanhDat-02627-Monitoring-LLMOps
- **Commit SHA cuối:** b88362d16ed3812e86604dff7543f15b0030154f
- **Challenge ID:** day13-k4-l3b-monitoring-llmops-v1
- **Tên project Langfuse cá nhân:** day13-k4-l3b-02627

## 2. Evidence index

Giữ đúng ba output text và năm ảnh dưới đây. Không tách thêm ảnh; nếu cần giải thích, ghi bằng chữ trong các mục sau.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/pytest.txt` |
| Log validator | `evidence/log-validator.txt` |
| Dashboard validator | `evidence/dashboard-validator.txt` |
| Structured log + incident log | `evidence/01-incident-log.png` |
| Trace list | `evidence/02-trace-list.png` |
| Trace waterfall + metadata + incident trace | `evidence/03-incident-trace.png` |
| Prompt versions + promote/rollback | `evidence/04-prompt-versioning.png` |
| Dashboard + incident metric | `evidence/05-dashboard-incident.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Đạt điểm tối đa sau khi hoàn thiện middleware, binding contextvars và scrub PII |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Hợp lệ toàn bộ 6/6 panel theo contract YAML |
| `pytest` | 2 passed | 27 passed | 100% unit tests pass hoàn toàn |
| Số traces hợp lệ | 0 | 15+ traces | Đã tạo >10 traces trong project Langfuse cá nhân |
| Số PII leak | 0 | 0 | Không còn rò rỉ PII nguyên văn trong log và trace |
| Latency P95 / TTFT P95 | 394ms / 50ms | 395ms / 50ms | Đạt chuẩn SLO <= 3000ms trong điều kiện bình thường |
| Retrieval success rate | 100% | 100% | Đạt mục tiêu guardrail >= 90% |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:**
  - Được xử lý tại `app/middleware.py` qua `CorrelationIdMiddleware`.
  - Khi có request đến, middleware gọi `clear_contextvars()` để xóa sạch ngữ cảnh cũ, tránh rò rỉ dữ liệu giữa các request concurrent.
  - Kiểm tra header `x-request-id`: nếu client gửi lên thì sử dụng; nếu không có, middleware tự sinh ID ngẫu nhiên theo chuẩn `req-<8-hex>` bằng `f"req-{uuid.uuid4().hex[:8]}"`.
  - Gọi `bind_contextvars(correlation_id=correlation_id)` để structlog tự động truyền `correlation_id` vào mọi câu lệnh log phát sinh trong suốt vòng đời của request.
  - Lưu vào `request.state.correlation_id` để endpoint `chat` đọc ra trả về trong `ChatResponse` và truyền vào `agent.run()`.
  - Trả ngược lại cho client qua response headers: `x-request-id` và `x-response-time-ms`.

- **Các metadata được ghi vào structured log:**
  - Header & Core fields: `ts` (ISO-8601 UTC), `level` (`info`, `warning`, `error`), `service` (`api`, `control`), `event` (`request_received`, `response_sent`, `request_failed`), `correlation_id`.
  - Context metadata (được bind ngay đầu hàm `chat` trong `app/main.py`): `user_id_hash` (băm SHA-256 12 ký tự đầu), `session_id`, `feature`, `model` (`claude-sonnet-4-5`), `env` (`dev`).
  - Performance & Tool metrics (trong sự kiện `response_sent`): `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name` (`retrieval`), `tool_success` (`True`/`False`), và `payload` chứa preview tin nhắn đã che PII.

- **Cách bảo đảm PII được scrub trước khi ghi:**
  - Định nghĩa các biểu thức regex trong `app/pii.py` cho 4 loại dữ liệu nhạy cảm chính: `email`, `phone_vn` (đầy đủ các đầu số 09x, 08x, +84 kèm dấu cách/chấm/gạch nối), `cccd` (12 số), `credit_card` (16 số), cùng các từ khóa địa chỉ Việt Nam `(?i)\b(đường|phố|tỉnh|huyện|thành phố)\b`.
  - Đăng ký processor `scrub_event` trong mảng `processors` của `structlog` tại `app/logging_config.py`.
  - **Vị trí bắt buộc:** `scrub_event` được đặt **trước** `JsonlFileProcessor()` và `JSONRenderer()`. Nhờ đó, toàn bộ dữ liệu nhạy cảm được thay thế bằng token `[REDACTED_<TYPE>]` trước khi bản ghi log được serialize thành JSON và ghi xuống file `data/logs.jsonl` hoặc xuất ra console.

- **Cách kiểm chứng kết quả:**
  - Chạy `python scripts/validate_logs.py` đạt **100/100 điểm**, báo cáo `Potential PII leaks detected: 0`.
  - Toàn bộ 7/7 test cases trong `tests/test_pii.py` (kiểm tra email, sđt VN, cccd, thẻ ngân hàng, địa chỉ) đều pass.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
  - Toàn bộ trace được gửi về project Langfuse Cloud cá nhân có tên: `day13-k4-l3b-02627`.
  - Project sử dụng cặp API keys riêng (`LANGFUSE_PUBLIC_KEY` và `LANGFUSE_SECRET_KEY`) cấu hình trong `.env`.
  - Tên project `day13-k4-l3b-02627` hiển thị rõ ràng trên thanh điều hướng góc trên của giao diện Langfuse (thể hiện trong ảnh `02-trace-list.png`).

- **Cấu trúc root/retrieval/generation observations:**
  - Cây trace phân cấp cha-con rõ ràng:
    ```text
    day13-agent-request (trace)
    └── lab-agent-run (root observation, as_type="agent")
        ├── retrieval (child observation, as_type="retriever")
        └── generation (child observation, as_type="generation")
    ```
  - `retrieval`: đo thời gian tìm kiếm tài liệu từ corpus trong hàm `retrieve()`, gắn cờ `capture_input=False, capture_output=False` chống lộ PII.
  - `generation`: gắn kèm thông số mô hình (`claude-sonnet-4-5`), `usage_details` (`input_tokens`, `output_tokens`, `total`), `cost_details` (`total`), và liên kết trực tiếp tới managed prompt của Langfuse.

- **Cách nối trace với log:**
  - Dùng chung khóa liên kết duy nhất là `correlation_id`.
  - Trong log: `correlation_id` nằm trong từng dòng JSON `data/logs.jsonl`.
  - Trong trace: `correlation_id` được truyền vào `propagate_attributes(metadata={"correlation_id": correlation_id})` và lưu trong metadata của trace trên Langfuse.

- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version 1 (gắn nhãn `baseline` và `production`)
- **Version/label candidate:** Version 2 (gắn nhãn `candidate`)
- **Trace ID của mỗi version:**
  - Trace ID dùng Version 1 (`production` / `baseline`): `dcf86a1a209deadd114fc63006edfacd` (correlation_id: `req-328ca26e`) hoặc `00d00b6eeb8232fe48f084c9a62f7c85` (sau rollback, correlation_id: `req-f8c8956a`)
  - Trace ID dùng Version 2 (`candidate` / promoted): `d927adef02c0211f3b2a2dbc1adfb7cb` (correlation_id: `req-2129c323`)
- **Cách promote và rollback `production`:**
  - **Promote:** Trên giao diện Langfuse Prompts $\to$ chọn Version 2 $\to$ chuyển nhãn `production` sang Version 2. Ứng dụng khi chạy với `LANGFUSE_PROMPT_LABEL=production` sẽ tự động sử dụng câu prompt của Version 2 mà không cần sửa code.
  - **Rollback:** Trên giao diện Langfuse Prompts $\to$ chọn Version 1 $\to$ gán lại nhãn `production` về Version 1. Ứng dụng lập tức quay về sử dụng Version 1 an toàn và tức thì.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
  - Được xây dựng tại endpoint `http://127.0.0.1:8000/dashboard` đọc dữ liệu thời gian thực từ `data/logs.jsonl` trong cửa sổ 60 phút, tự động refresh mỗi 30 giây.
  - Đủ 6 panel theo đúng contract `config/dashboard.yaml`:
    1. *Latency percentiles and TTFT (ms):* Hiển thị P50, P95, P99 và TTFT P95 kèm đường ngưỡng P95 <= 3000ms.
    2. *Request traffic (req/min):* Tổng số request và tốc độ request/phút kèm ngưỡng >= 1.
    3. *Error rate and retrieval success (%):* Tỉ lệ lỗi toàn hệ thống (<= 2%) và tỉ lệ tìm kiếm context thành công (>= 90%).
    4. *Cost over time (USD):* Tổng chi phí và chi phí trung bình/request kèm ngưỡng <= $2.50.
    5. *Input and output tokens (tokens):* Tổng token, token input, token output kèm ngưỡng <= 50,000.
    6. *Quality score proxy (score 0-1.0):* Điểm chất lượng trung bình theo heuristic kèm ngưỡng >= 0.75.

- **SLO và lý do chọn:**
  - Primary SLO: `fast_successful_requests` với mục tiêu **99.5%** trong cửa sổ đo 28 ngày (`window: 28d`).
  - Tiêu chí đánh giá (SLI): Request được xem là tốt (`good_event`) khi có sự kiện `response_sent` và độ trễ `latency_ms <= 3000ms`, tính trên tổng số `request_received`.
  - Lý do: Đối với một ứng dụng AI hội thoại, người dùng cần nhận được phản hồi chính xác và trong khoảng thời gian chấp nhận được (dưới 3 giây) để duy trì tính tương tác tự nhiên.

- **Cách tính error budget:**
  - Với mục tiêu SLO là 99.5%, Error Budget được phép là: `100% - 99.5% = 0.5%`.
  - Ý nghĩa vận hành: Nếu hệ thống nhận 10,000 requests trong chu kỳ 28 ngày, thì tối đa 50 requests được phép bị lỗi (HTTP 500) hoặc có thời gian phản hồi chậm hơn 3000ms mà vẫn không vi phạm cam kết chất lượng dịch vụ (SLO).

- **Ba alert và runbook tương ứng:**
  - **Alert 1: `HighLatencyP95`** (Warning | `p95(latency_ms) > 3000ms` trong 5 phút | Slack `#k4-l3b-alerts` | Owner: `student-02627` | Runbook: `docs/alerts.md#alert-1`).
  - **Alert 2: `HighErrorRate`** (Critical | `error_rate_pct > 2%` trong 5 phút | Slack `#k4-l3b-alerts` | Owner: `student-02627` | Runbook: `docs/alerts.md#alert-2`).
  - **Alert 3: `LowRetrievalSuccessRate`** (Warning | `retrieval_success_rate_pct < 90%` trong 5 phút | Slack `#k4-l3b-alerts` | Owner: `student-02627` | Runbook: `docs/alerts.md#alert-3`).

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** Từ `05:10:19Z` đến `05:11:55Z` ngày `2026-09-30` (tức 12:10 đến 12:12 giờ địa phương).
- **Triệu chứng từ metrics:**
  - Trên Dashboard panel Latency, P95 Latency tăng vọt bất thường từ mức ~390ms lên **2653ms – 3591ms** (vượt xa ngưỡng SLO 2000ms / 3000ms).
  - Ngược lại, metric TTFT P95 vẫn duy trì ổn định ở mức **50ms**. Điều này chứng tỏ sự cố không xuất phát từ việc khởi động sinh token của mô hình LLM.
- **Log line và correlation ID liên quan:**
  - Correlation ID đại diện: `req-61aa5f49` (thuộc chuỗi 5 requests challenge bị chậm: `req-61aa5f49`, `req-3bba505c`, `req-1d0af11c`, `req-97700c25`, `req-62e99437`).
  - Log line trích xuất từ `data/logs.jsonl`:
    ```json
    {"service": "api", "latency_ms": 3591, "ttft_ms": 50, "tokens_in": 50, "tokens_out": 101, "cost_usd": 0.001665, "quality_score": 0.8, "tool_name": "retrieval", "tool_success": true, "payload": {"answer_preview": "Starter answer. You should improve this output logic and add better quality chec..."}, "event": "response_sent", "feature": "monitoring", "model": "claude-sonnet-4-5", "correlation_id": "req-61aa5f49", "user_id_hash": "68e37dc7cb5e", "env": "dev", "session_id": "k4-l3b-challenge-s05", "level": "info", "ts": "2026-09-30T05:11:44.151467Z"}
    ```
- **Trace ID và span gây ảnh hưởng:**
  - Trace ID trên Langfuse (cùng `correlation_id=req-61aa5f49`): `755821a9bdbc6bffecb425819a7f4552`
  - Mở chi tiết cây Waterfall trace:
    - Span root `lab-agent-run`: tổng thời gian ~3.59s.
    - Span con `generation`: chỉ mất **0.15s** (hoàn toàn bình thường).
    - Span con **`retrieval`**: mất tới **2.50s** (2500ms) $\to$ Chiếm hơn 90% tổng thời gian request.
- **Root cause:**
  - Bước truy vấn tài liệu ngữ cảnh (RAG / Vector store) bị suy giảm hiệu năng nghiêm trọng, gây ra độ trễ 2.5 giây cho mỗi lần gọi `retrieve()` (do sự cố mô phỏng `rag_slow` gây ra). Tầng sinh câu trả lời của mô hình LLM và mạng hoàn toàn bình thường.
- **Fix action:**
  - Tắt kịch bản sự cố bằng lệnh: `python scripts/inject_incident.py --disable`.
  - Trong thực tế: Khởi động lại kết nối pool tới Vector Database, kiểm tra tài nguyên cụm vector search hoặc tạm thời kích hoạt chế độ cache context cục bộ.
- **Preventive measure:**
  - Bổ sung chỉ số và alert riêng cho độ trễ của bước retrieval (`retrieval_latency > 1500ms`).
  - Thiết lập timeout tối đa (ví dụ 1.5s) cho thao tác retrieval; nếu quá thời gian thì tự động fallback về câu trả lời mặc định thay vì làm treo cả request.
  - Cấu hình auto-scaling và read-replica cho Vector DB để đảm bảo thông lượng khi lưu lượng người dùng tăng cao.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
  - Quyết định phân tách hai child observation riêng biệt (`retrieval` kiểu retriever và `generation` kiểu generation) bên trong root span `lab-agent-run`. 
  - Lý do: Một ứng dụng LLM không phải chỉ có mỗi cuộc gọi API tới mô hình. Nếu chỉ đo thời gian toàn bộ agent, khi hệ thống bị chậm, kỹ sư sẽ không thể biết nguyên nhân do mạng, do vector database, hay do LLM bị nghẽn. Việc phân rã span chi tiết giúp khoanh vùng chính xác 100% nguyên nhân sự cố trong tích tắc.
  - Đặt bước PII scrubbing trực tiếp trong logger pipeline trước khi serialize/render JSON giúp ngăn chặn rò rỉ dữ liệu nhạy cảm xuống ổ đĩa ngay từ nguồn.

- **Một lỗi/blocker đã gặp:**
  - Sau khi triển khai xong code ở CP1, khi chạy `validate_logs.py` điểm số chỉ đạt 30/100 dù code đã đúng.
  - Lỗi regex: `vn_address_keywords` ban đầu thiếu cờ case-insensitive `(?i)`, dẫn tới không phát hiện được chữ "Đường" viết hoa trong tiếng Việt.

- **Cách tìm nguyên nhân và xử lý:**
  - Phát hiện `validate_logs.py` đọc toàn bộ file `data/logs.jsonl` từ đầu đến cuối, nghĩa là 20 dòng log cũ được ghi trước khi sửa code vẫn bị validator quét trúng và tính lỗi.
  - Xử lý: Sao lưu file cũ thành `data/logs_baseline.jsonl`, xóa `logs.jsonl` cũ, khởi động lại API server và chạy lại `python scripts/load_test.py` $\to$ validator chấm đạt 100/100 điểm tuyệt đối.
  - Thêm cờ `(?i)` vào regex địa chỉ tiếng Việt để vượt qua toàn bộ 7/7 test cases trong `tests/test_pii.py`.

- **Cách hiểu luồng Metrics → Logs → Traces:**
  - **Metrics:** Cho biết **"Hệ thống có triệu chứng gì bất thường và bắt đầu từ thời điểm nào"** (Nhìn dashboard thấy P95 Latency tăng vọt lúc 12:11).
  - **Logs:** Giúp xác định **"Những request cụ thể nào bị ảnh hưởng"** bằng cách lọc log trong khoảng thời gian trên và trích xuất `correlation_id: req-61aa5f49`.
  - **Traces:** Giúp trả lời **"Bước cụ thể nào bên trong request đó là thủ phạm gây lỗi"** bằng cách mở trace cùng `correlation_id`, quan sát cây waterfall và thấy span `retrieval` chiếm 2.50s.
  - **Root cause:** Kết luận nguyên nhân gốc rễ dựa trên bằng chứng định lượng ở cả 3 tầng, không phải suy đoán cảm tính.

- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - *Prompt Versioning & Rollback:* Prompt ảnh hưởng trực tiếp tới độ dài, độ trễ và chất lượng câu trả lời. Quản lý prompt có version và label (`production`, `candidate`) cho phép đội ngũ kỹ thuật thử nghiệm prompt mới và rollback tức thì về prompt cũ khi phát hiện regression mà không cần sửa code hay deploy lại service.
  - *Token & Cost:* Chi phí LLM tỷ lệ thuận với số lượng token. Việc theo dõi token input/output theo thời gian giúp phát hiện sớm các sự cố bùng nổ chi phí (cost spike) hoặc prompt injection lặp vô tận.
  - *SLO & Error Budget:* Định lượng rõ ràng ranh giới giữa hệ thống "chấp nhận được" và "suy giảm chất lượng", là căn cứ để quyết định khi nào cần đóng băng release để tập trung tối ưu độ ổn định.

- **Điều quan trọng nhất đã học:**
  - Nắm vững kiến trúc Observability hiện đại cho hệ thống AI/LLM, hiểu sâu sắc cách phối hợp nhịp nhàng giữa Structured Logging, Distributed Tracing (Langfuse) và Metrics Dashboard.

- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Hệ thống hiện tại sử dụng FakeLLM để mô phỏng. Khi triển khai trên môi trường production thực tế với các nhà cung cấp như OpenAI, Anthropic, cần bổ sung thêm cơ chế streaming tokens (đo TTFT chuẩn hơn qua Server-Sent Events) và kết nối OTLP Collector chuyên dụng.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Có đúng 3 file text và 5 ảnh runtime theo hướng dẫn.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
