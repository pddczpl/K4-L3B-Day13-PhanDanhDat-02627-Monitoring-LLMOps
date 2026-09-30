# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Latency P95 của `response_sent.latency_ms` (mục tiêu <= 3000ms)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh span `retrieval` và `generation` để xác định bước bất thường.
- Mitigation tạm thời: Rollback prompt về version trước nếu do prompt mới, khôi phục cấu hình hoặc giảm tải hệ thống.
- Owner: `student-02627`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Tỉ lệ lỗi toàn hệ thống `request_failed / request_received * 100` (mục tiêu <= 2%)
- Điều kiện và thời gian duy trì: `error_rate_pct > 2%` trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng nhận lỗi HTTP 500 và không nhận được phản hồi
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel Errors để xác định tỉ lệ lỗi và phân bố theo `error_type`.
  2. Lọc `data/logs.jsonl` tìm event `request_failed`, ghi nhận `correlation_id` và thông điệp lỗi trong `payload.detail`.
  3. Mở trace có cùng `correlation_id` trên Langfuse để xem chính xác span và stack trace gây lỗi.
- Mitigation tạm thời: Khởi động lại service, rollback bản build/prompt mới nhất hoặc bật chế độ phản hồi fallback.
- Owner: `student-02627`

## Alert 3

- Tên: `LowRetrievalSuccessRate`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Tỉ lệ thành công của retrieval `tool_success` (mục tiêu >= 90%)
- Điều kiện và thời gian duy trì: `retrieval_success_rate_pct < 90%` trong 5 phút
- Ảnh hưởng tới người dùng: Câu trả lời bị thiếu ngữ cảnh tài liệu chính xác, giảm chất lượng nội dung
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel Errors kiểm tra đồ thị và tỉ lệ của `tool_success_rate_pct`.
  2. Lọc `data/logs.jsonl` tìm các request có `tool_name="retrieval"` và `tool_success=false`, lấy `correlation_id`.
  3. Mở trace tương ứng trên Langfuse, kiểm tra span `retrieval` xem gặp lỗi gì (ví dụ: vector store timeout).
- Mitigation tạm thời: Khởi động lại kết nối cơ sở dữ liệu vector hoặc chuyển sang corpus cache dự phòng.
- Owner: `student-02627`
