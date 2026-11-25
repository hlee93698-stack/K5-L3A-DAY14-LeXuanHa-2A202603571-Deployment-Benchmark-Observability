# Benchmark & Observability Report — Day 14

**Họ tên:** Lê Xuân Hạ (MSSV: 2A202603571)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows, Python 3.11.2, Docker Engine 29.9.3 / Docker Compose v5.7.1

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Với mock LLM có base latency ~120ms + jitter ~60ms + retrieval ~20ms (tổng ~200ms), ngưỡng 500ms đảm bảo 95% người dùng nhận phản hồi nhanh ngay cả khi có dao động nhẹ |
| Error rate `/ask` | `< 2.0 %` | `MOCK_ERROR_RATE` mặc định là 1% (0.01); ngưỡng 2% cho phép lỗi upstream ngẫu nhiên nhỏ nhưng cảnh báo ngay khi lỗi tăng bất thường |
| Accuracy trên golden dataset | `≥ 100 %` (23/23, 0 regression) | Bộ golden dataset 23 câu bao phủ kiến thức cốt lõi; mọi thay đổi KB/prompt trước khi deploy phải pass 100% và không làm rớt câu đã đúng |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.55 | 200.1 | 235.9 | 1700.3 | 1.00% | PASS |
| 10 | 34.93 | 199.3 | 438.7 | 1708.9 | 0.67% | PASS |
| 50 | 92.72 | 211.9 | 546.2 | 1701.3 | 0.67% | FAIL (p95 > 500ms) |
| 100 | 39.21 | 1156.2 | 5202.4 | 5560.2 | 0.67% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ c=1 → c=10 → c=50, RPS tăng mạnh (4.55 → 34.93 → 92.72 req/s) nhờ xử lý bất đồng bộ (`asyncio`), nhưng đến c=100 thì RPS **tụt xuống 39.21 req/s** và p50/p95 tăng vọt (1156ms / 5202ms) do bão hòa tài nguyên CPU/event-loop trên 1 process uvicorn và hàng đợi kết nối bị nghẽn.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 211.9 | 479.9 | 528.4 |
| 0.03 (mặc định) | 273.1 | 492.9 | 1705.9 |
| 0.1 | 348.3 | 1684.0 | 1725.9 |

**Nhận xét:** `p99` và `p95` nhạy nhất với các request chậm bất thường: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request chậm), `avg` chỉ tăng nhẹ từ `211.9ms` lên `273.1ms` nhưng `p99` nhảy vọt hơn 3 lần từ `528.4ms` lên `1705.9ms`. Khi lên `0.1` (10% chậm), `p95` vọt lên `1684.0ms` (vi phạm SLO). Vì vậy **không thể đặt SLO theo average**, vì giá trị trung bình che giấu trải nghiệm tệ của nhóm người dùng ở đuôi phân phối (tail latency).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.9 | 109.3 | 114.3 |
| Tổng cost (USD) | $0.000415 | $0.000764 | $0.000796 |
| Cost / câu đúng (USD) | $0.00041475 | $0.00003639 | $0.00003459 |
| Quality gate | FAIL | FAIL (< 100%) | PASS (23/23, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa (`utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` giải thích JWT là token có chữ ký số (`signature`) và thời gian hết hạn (`exp`), xác thực stateless so với API key |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA scale dựa trên CPU, memory hoặc custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 tốn nhiều token hơn (~114.3 vs 57.9 tokens/câu) và chi phí tổng cao hơn (~1.9x) + thêm ~20ms bước retrieval so với v1, nhưng accuracy tăng từ **4.35% lên 100%**.
- Nếu xét theo **cost / câu đúng**, v2 rẻ hơn ~12 lần (`$0.00003459` vs `$0.00041475`) vì v1 trả lời sai 22/23 câu.
- **Dùng exit code trong CI để chặn merge:** `run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json` trả về exit code `0` khi đạt ngưỡng accuracy và không có câu nào bị regression, và trả về exit code khác `0` khi fail; chỉ cần chạy lệnh này trong GitHub Actions/GitLab CI step để tự động chặn PR/merge khi chất lượng giảm.

---

## 4. Observability stack (production)

### 4.1 Screenshot
- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

### 4.2 Thí nghiệm "phá hệ thống"

Điều kiện chung: stack `-p k5-day14-observability`, 2 instance agent, Locust headless 30 users chạy liên tục từ 17:07:50; thời gian đo bằng script poll `GET /api/v1/rules` mỗi 2s, ghi lại lúc mỗi alert đổi trạng thái (giờ GMT+7, ngày 2026-11-25).

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (đổi `.env` + `docker compose up -d` lúc 17:16:26) | `AgentHighErrorRate` — pending 17:17:13 (8.4%), **firing 17:18:17**, value `20.98%` > 5% | **111.7s** (≈ 30–45s agent khởi động lại + lấp cửa sổ `rate[1m]`, rồi `for: 1m`) | Error rate, Requests/s theo status code (503 tăng), LLM calls theo kết quả (error) |
| B | `MOCK_SLOW_RATE=0.3` | Không thực hiện (bài yêu cầu tối thiểu 2 thí nghiệm) | — | — |
| C | `LLM_MODEL=mock-llm-large` (cùng lúc với A) | `LLMCostBurnRateHigh` — **đã firing từ 17:14:15, trước khi đổi cấu hình**: với tải nền 30 users / ~18 req/s, `mock-llm-small` đã đốt ~$2.37/giờ > ngưỡng $2/giờ (pending 17:12:15 → firing 17:14:15). Sau khi đổi sang large, burn rate tăng từ `$2.37` lên `$9.56/giờ` (17:18:24) và `$12.57/giờ` (lúc chụp ảnh) | Không đo được (alert đã firing sẵn) | Cost burn rate (USD/giờ), LLM cost (1h), LLM latency p95 theo model |
| D | `docker pause k5-day14-observability-agent-1` lúc 17:20:39 (unpause 17:21:24) | `AgentInstanceDown` — pending 17:20:52, **firing 17:21:22** | **43.9s** (scrape fail ~13s + `for: 30s`) | Instances up (2 → 1), Requests/s theo instance; **Error rate vẫn xanh** (0.86%) |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** (phân tích bên dưới, không chạy lại trên stack) | N/A | Retrieval hit ratio, Tokens/s, bảng "Phiên bản đang chạy" — các panel HTTP/latency vẫn xanh |

Ảnh `screenshots/prometheus-alert-firing.png` chụp lúc 17:19 thấy **2 alert cùng FIRING**: `LLMCostBurnRateHigh` (Active since 6m 50s, value 12.57) và `AgentHighErrorRate` (Active since 1m 51s, value 0.2104).

**Nhận xét thí nghiệm C:** ngưỡng `$2/giờ` quá sát với chi phí của tải bình thường (30 users), nên alert báo động ngay cả khi không có sự cố → cần đặt ngưỡng dựa trên baseline thực tế (ví dụ ×2–3 baseline) hoặc so với budget tháng, nếu không đội vận hành sẽ bị "alert fatigue".

**Nhận xét thí nghiệm D — vì sao lỗi 504 ở Nginx không hiện trên metric của agent:** trong 45s pause, log Nginx ghi **29 × `504`** (`upstream timed out`, do `proxy_read_timeout 10s`) cùng 783 × `200` và 7 × `503`; nhưng error rate trên dashboard (tính từ `http_requests_total` của agent) chỉ **0.86%**. Lý do: request bị treo ở instance đang pause không bao giờ được agent xử lý xong nên agent không đếm nó; còn instance kia vẫn trả 200. Metric phía server chỉ thấy request đã tới và hoàn tất → cần thêm metric/log ở tầng load balancer (Nginx status code) hoặc **synthetic check / SLI phía client** để thấy lỗi người dùng thực sự gặp. `AgentInstanceDown` (dựa trên `up`) mới là tín hiệu bắt được sự cố này.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
- Vì `AGENT_VERSION=v1` vẫn trả HTTP `200`, latency còn nhanh hơn v2 và không lỗi hệ thống, nên metric hạ tầng (Golden Signals) không bắt được sự cố giảm chất lượng câu trả lời.
- Cách phát hiện: chạy **scheduled eval / shadow eval** định kỳ trên golden dataset (hoặc sample traffic thật để chấm bằng LLM-as-a-judge), theo dõi thêm business/quality metrics như tỷ lệ `retrieved=true`, điểm eval accuracy, hoặc phản hồi thumbs-up/down của người dùng.

### 4.3 Debug bằng trace

Stack chạy với 2 instance agent, Locust headless 30 users (bắt đầu 17:07:50 GMT+7), Jaeger → Service `observable-agent` → Find Traces → **Longest First**.

**Trace chậm nhất** (`screenshots/jaeger-slow-trace.png`):
- `trace_id`: `6b758e1f8dd53e5e7b809a17a151df51`
- Tổng thời gian: `2350.80 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`2290.83 ms`, **97.4%**) — nằm trong `agent.run` (`2315.68 ms`, 98.5%), trong khi `agent.retrieve_context` chỉ mất `24.39 ms` (1.0%). → Nút thắt là lời gọi LLM (request rơi vào nhóm `MOCK_SLOW_RATE`), không phải retrieval.
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep 6b758e1f8dd53e5e7b809a17a151df51`):

```json
{"ts": "2026-11-25T10:08:18.015492+00:00", "level": "INFO", "service": "observable-agent", "instance": "cd313e4cc848", "event": "llm_call", "trace_id": "6b758e1f8dd53e5e7b809a17a151df51", "span_id": "e80e1312e68323fa", "request_id": "acc8c5744e23", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1668.9}
{"ts": "2026-11-25T10:08:18.030259+00:00", "level": "INFO", "service": "observable-agent", "instance": "cd313e4cc848", "event": "http_request", "trace_id": "6b758e1f8dd53e5e7b809a17a151df51", "span_id": "e80e1312e68323fa", "request_id": "acc8c5744e23", "method": "POST", "route": "/ask", "status": 200, "ms": 2345.8}
```

**Trace lỗi** (`screenshots/jaeger-error-trace.png`, tag `error=true`):
- `trace_id`: `fda739a9a519deb7f7b2798cf20e9e3c` — tổng `147.49 ms`, `POST /ask` trả `503`.
- Span lỗi gốc: `chat mock-llm-small` (`108.28 ms`), event `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`; lỗi lan lên `agent.run` (`142.52 ms`) và `POST /ask`.
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep llm_error | head -1`):

```json
{"ts": "2026-11-25T10:08:04.083710+00:00", "level": "INFO", "service": "observable-agent", "instance": "cd313e4cc848", "event": "llm_error", "trace_id": "fda739a9a519deb7f7b2798cf20e9e3c", "span_id": "9502467334a5f199", "request_id": "1af839b80938", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T10:08:04.085494+00:00", "level": "INFO", "service": "observable-agent", "instance": "cd313e4cc848", "event": "http_request", "trace_id": "fda739a9a519deb7f7b2798cf20e9e3c", "span_id": "9502467334a5f199", "request_id": "1af839b80938", "method": "POST", "route": "/ask", "status": 503, "ms": 146.2}
```

### 4.4 Trả lời Exercise 7.4

Số liệu tại đúng thời điểm chụp `screenshots/grafana-dashboard.png` (**17:11:25 GMT+7**, 2 instance, Locust 30 users). Các ô trên ảnh (Traffic 18.0 req/s, Error rate 1.11%, Latency p95 299.89 ms, In-flight 8, LLM cost $0.1381) được đối chiếu lại bằng chính query của dashboard trên Prometheus API tại cùng timestamp để lấy thêm các số không in trên ảnh (avg, p99, tokens/s, req/s theo instance):

| Chỉ số | Giá trị |
|---|---|
| Traffic `/ask` | 17.98 req/s (Grafana hiển thị 18.0) |
| Error rate `/ask` | 1.11% |
| Latency p50 / p95 / p99 | 194.5 / 299.89 / 1858.7 ms |
| Latency avg | 252.5 ms |
| Saturation (in-flight) / LLM cost (1h) | 8 / $0.1381 |
| Requests/s theo instance | `172.18.0.6:8000` = 10.00, `172.18.0.4:8000` = 9.95 |
| Tokens/s | input = 1395.7, output = 736.7 |

1. **p95 vs avg:** p95 = `299.89 ms`, avg = `252.5 ms`, còn p99 = `1858.7 ms`. Phần lớn request xong trong ~200ms nên kéo avg xuống, nhưng ~3% request chậm (`MOCK_SLOW_RATE=0.03`, ~1.7–2.3s) đẩy đuôi phân phối lên rất cao. Khoảng cách avg ↔ p95/p99 lớn cho thấy phân phối lệch phải (tail latency); avg che giấu trải nghiệm tệ của nhóm user ở đuôi nên SLO phải đặt theo percentile.
2. **Nginx có chia đều không?** Có: `10.00` vs `9.95` req/s (~50/50, panel "Requests/s theo instance" hai đường gần như trùng nhau) vì upstream `agent_cluster` dùng round-robin mặc định.
3. **Vì sao input tokens/s > output tokens/s?** (`1395.7` vs `736.7`, ~1.9 lần) Agent v2 có bước retrieval: prompt gửi vào LLM = câu hỏi + đoạn context lấy từ knowledge base (+ system prompt), nên input dài; output chỉ là câu trả lời ngắn. Ví dụ trace chậm ở trên: `input_tokens=74`, `output_tokens=37`.
4. **`curl http://localhost:8080/metrics`** trả về `HTTP/1.1 404 Not Found` (trang 404 của nginx). Vì `nginx.conf` có `location = /metrics { return 404; }`: metrics lộ thông tin nội bộ (route, lưu lượng, instance, chi phí) nên không public ra ngoài; Prometheus scrape trực tiếp từng agent qua mạng Docker nội bộ (`obs_net`), không đi qua Nginx.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu trích xuất từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated` / `/ask`):

| Số instance | RPS (`/ask` / Agg) | p50 (ms) | p95 (ms) | p99 (ms) | Failures (`/ask`) |
|---|---|---|---|---|---|
| 1 | 61.94 / 67.73 | 190 / 180 | 220 / 220 | 1700 / 1700 | 1344 (phần lớn 502 lúc khởi động + 1% mock 503) |
| 3 | 59.76 / 65.63 | 190 / 190 | 240 / 230 | 1700 / 1700 | 77 (1.08% — chỉ còn ~1% mock 503) |

**Giải thích kết quả:**
- **Scale có cải thiện p95 không? Không.** p95 `/ask` là `220 ms` (1 instance) và `240 ms` (3 instance) — chênh 20ms nằm trong mức dao động giữa 2 lần chạy; p50 (`190 ms`) và p99 (`1700 ms`) giữ nguyên. RPS cũng không tăng (`67.73` → `65.63` req/s aggregated).
- **Nút thắt nằm ở đâu?** Không nằm ở agent mà ở **bộ sinh tải và độ trễ cố định của mock LLM**:
  - Locust chạy *closed-loop*: mỗi user gửi request, chờ trả lời, rồi nghỉ `wait_time = between(0.5, 2)` (trung bình 1.25s). Với 100 user và thời gian phản hồi ~0.2s, trần lý thuyết ≈ `100 / (1.25 + 0.2) ≈ 69 req/s` — đúng bằng mức đo được (~66–68 req/s) ở **cả hai** cấu hình. Tức là 1 instance đã phục vụ kịp toàn bộ tải; thêm instance không có gì để tăng.
  - Latency mỗi request do mock LLM quyết định (`MOCK_LATENCY_MS=120` + jitter, 3% request chậm ~1.7s) — đây là thời gian chờ I/O (`asyncio.sleep`), không phụ thuộc số instance, nên p50/p95/p99 không đổi.
  - Muốn thấy lợi ích của scale cần tăng tải tới mức 1 instance bão hoà (nhiều user hơn / `wait_time` nhỏ hơn, hoặc giới hạn CPU thấp hơn) — khi đó p95 của 1 instance sẽ tăng vọt còn 3 instance thì không.
- **Về Failures:** 1344 lỗi của lần chạy 1 instance **không phải do quá tải** — theo `scale_1_failures.csv`, 1279 lỗi là `502 Bad Gateway` tập trung trong 22 giây đầu (08:38:55 → 08:39:17) khi Locust bắt đầu bắn tải lúc agent chưa sẵn sàng; 65 lỗi còn lại là `503` từ mock (`MOCK_ERROR_RATE=0.01`). Lần chạy 3 instance bắt đầu khi agent đã chạy sẵn nên chỉ còn ~1.08% lỗi `503` mock. Vì vậy không thể kết luận "scale làm giảm lỗi" từ cặp số này; nếu bỏ 22 giây khởi động, error rate hai cấu hình là tương đương (~1%).

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **p95/p99 quan trọng hơn average:** Giá trị trung bình che giấu tail latency; chỉ 3% request chậm đã đẩy p99 lên >1.7s.
  2. **Cost / câu đúng & Quality gate:** Đánh giá agent phải ghép cả chất lượng (accuracy trên golden dataset) lẫn chi phí/latency, dùng exit code trong CI để chặn regression.
  3. **3 trụ cột Observability liên kết qua `trace_id`:** Metrics (Prometheus/Grafana) báo *có vấn đề*, Traces (Jaeger) chỉ ra *span nào chậm/lỗi*, và JSON Logs có `trace_id` giúp *truy vết chi tiết*.
- Nếu đưa agent lên production thật, cần thêm các metric/alert:
  - Tỷ lệ `retrieval_hit_rate` và điểm eval chất lượng định kỳ (để bắt sự cố suy giảm chất lượng như thí nghiệm E).
  - Redis latency / connection errors và tỷ lệ `429 Rate Limit` / `402 Cost Guard` theo từng API key.
