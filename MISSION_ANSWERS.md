# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production (CP1)

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`
1. **Hardcode secret (`OPENAI_API_KEY`, `DATABASE_URL`)** (dòng 17–18): Đẩy code lên GitHub sẽ lộ ngay thông tin nhạy cảm.
2. **In secret ra log bằng `print()`** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ key trong console/log aggregator.
3. **Không có health check / readiness endpoint**: Thiếu `/health` và `/ready` nên cloud platform hoặc load balancer không biết app còn sống hay sẵn sàng nhận traffic.
4. **Hardcode cấu hình & chạy ở chế độ dev** (dòng 21–22, 49–54): `DEBUG = True`, `host="localhost"` (chỉ nghe loopback, không nhận traffic từ ngoài container), `port=8000` (không đọc `PORT` env var của platform), `reload=True` (bật file watcher trong production).
5. **Dùng `print()` thay cho structured JSON logging** (dòng 33–38): Khó lọc theo level/event trên hệ thống log tập trung (Datadog, Loki).
6. **Không có graceful shutdown**: Không bắt `SIGTERM` hay `lifespan` shutdown để chờ request đang chạy hoàn tất trước khi tắt.

### Exercise 1.2: Kết quả chạy bản `develop` và `production`
- **`01-localhost-vs-production/develop` (`POST /ask?question=Hello`):**
  ```text
  200 {"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
  ```
- **`01-localhost-vs-production/production`:**
  - `GET /health` → `200 {"status":"ok","uptime_seconds":0.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:03:52.444469+00:00"}`
  - `GET /ready` → `200 {"ready":true}`
  - `POST /ask` (`{"question":"Hello"}`) → `200 {"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}`

### Exercise 1.3: Comparison table
| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Why Important? |
| --- | --- | --- | --- |
| Config & Secrets | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True` (dòng 17–22) | Đọc từ biến môi trường qua `Settings` (`config.py`), validate fail-fast khi `ENVIRONMENT=production` | Tránh lộ secret trên Git, đổi cấu hình linh hoạt giữa dev/staging/prod mà không sửa code |
| Host & Port | Cứng `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `HOST=0.0.0.0`, `PORT` từ env, `reload` chỉ bật khi `DEBUG=true` (dòng 194–198) | Container và cloud platform (Railway/Render) inject `PORT` động và cần `0.0.0.0` để route traffic từ ngoài vào |
| Health check | Không có | Có `GET /health` (liveness) và `GET /ready` (readiness trả 503 khi chưa sẵn sàng, dòng 135–161) | Platform tự restart khi container treo và load balancer chỉ gửi request khi app sẵn sàng |
| Logging | `print(...)` và in cả `OPENAI_API_KEY` (dòng 33–34) | `logging` định dạng JSON (`{"time":...,"level":...,"msg":...}`), không log secret (dòng 28–32, 111–122) | Dễ parse/truy vấn trên log aggregator và không làm rò rỉ credentials |
| Shutdown | Tắt đột ngột, không `lifespan` | Có `@asynccontextmanager lifespan` + `signal.signal(signal.SIGTERM, ...)` (dòng 39–67, 180–189) | Cho phép request đang xử lý hoàn tất trước khi container dừng khi deploy/scale down |

---

## Part 2: Docker (CP2)

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)
1. **Base image:** `python:3.11` (full Python distribution, ~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` trước `COPY . .`:** Tận dụng Docker layer cache. `requirements.txt` ít thay đổi hơn source code; nếu copy source trước thì mỗi lần sửa code đều làm mất cache và phải `pip install` lại từ đầu.
4. **CMD vs ENTRYPOINT:** `CMD` chỉ định lệnh/tham số mặc định và có thể bị ghi đè dễ dàng khi `docker run <image> <cmd>`; `ENTRYPOINT` cố định executable chính của container, các tham số truyền thêm ở `docker run` sẽ được nối vào làm đối số cho `ENTRYPOINT`.

### Exercise 2.2: Chạy container `my-agent:develop`
- Build từ gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`
- Chạy container và gọi `POST http://localhost:8000/ask?question=Hello`:
  ```text
  {"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
  ```

### Exercise 2.3: Image size comparison (đo bằng `docker images`)
- **Develop (`my-agent:develop`):** `1.67 GB` (~1,670 MB, base `python:3.11`)
- **Production (`my-agent:advanced`):** `240 MB` (multi-stage build với `python:3.11-slim`, chỉ copy packages từ stage `builder` sang `runtime`, không mang theo build tools như `gcc`)
- **Chênh lệch:** Giảm **~85.6%** dung lượng (nhỏ hơn ~1,430 MB).

### Exercise 2.4: Kiến trúc Docker Compose stack (`02-docker/production/docker-compose.yml`)
- **Sơ đồ kết nối các service (mạng `internal`):**
  ```text
  Client (:80/:443) ──▶ [nginx] ──▶ [agent (:8000)] ──┬──▶ [redis (:6379)]
                                                     └──▶ [qdrant (:6333)]
  ```
- **Services được start:** `redis` và `qdrant` start trước (agent có `depends_on ... condition: service_healthy`), sau đó `agent`, cuối cùng `nginx`. Chỉ `nginx` publish port ra ngoài; `agent`, `redis`, `qdrant` chỉ nói chuyện với nhau qua network `internal` bằng tên service (`redis://redis:6379`, `http://qdrant:6333`, Nginx `proxy_pass http://agent_backend`).
- **Kiểm tra stack qua Nginx:** máy Windows có IIS chiếm cổng 80, nên chạy kèm một file override tạm (không sửa `docker-compose.yml` của đề) đổi port Nginx thành `8081:80`:
  ```bash
  # compose.port8081.yml:  services: { nginx: { ports: !override ["8081:80"] } }
  docker compose -p k5-day14-docker -f docker-compose.yml -f compose.port8081.yml up -d --build
  ```
  ```text
  agent  Up (health: starting)     nginx  0.0.0.0:8081->80/tcp
  qdrant Up (healthy)              redis  Up (healthy)

  $ curl -i http://localhost:8081/health
  HTTP/1.1 200 OK
  Server: nginx
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  {"status":"ok","uptime_seconds":0.4,"version":"2.0.0","timestamp":"2026-11-25T10:33:34.806877"}

  $ curl -i http://localhost:8081/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
  HTTP/1.1 200 OK
  Server: nginx
  {"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
  ```
  Header `Server: nginx` và các security header (`X-Frame-Options`, `X-Content-Type-Options`) do Nginx thêm vào chứng tỏ request đi qua reverse proxy rồi mới tới agent. Dọn stack bằng `docker compose -p k5-day14-docker down -v`.

---

## Part 3: Cloud Deployment (CP6)

### Exercise 3.1 / 3.2: Deploy Agent Part 6 (`06-lab-complete/`)
- **Nền tảng chính:** Railway (service `agent-api` build từ `06-lab-complete/Dockerfile` theo `railway.toml`, kèm Redis của Railway; `REDIS_URL=${{Redis.REDIS_URL}}`, `AGENT_API_KEY` đặt trên tab Variables, không ghi trong code)
- **Public URL:** https://agent-api-production-cf0a9942.up.railway.app
- **Kết quả 4 lệnh tự kiểm (`/health`, `/ready`, `/ask` không key, `/ask` có key):**
  ```text
  $ curl $URL/health
  {"status":"ok"}  -> 200
  $ curl $URL/ready
  {"status":"ready"}  -> 200
  $ curl -X POST $URL/ask (không key)
  {"detail":"Invalid or missing API key"}  -> 401
  $ curl -X POST $URL/ask -H "X-API-Key: ***"
  {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}  -> 200
  ```
- **Rate limit trên cloud** (12 request liên tiếp có key, ngay sau request trên — tổng 10 req/phút được phép):
  ```text
  200 200 200 200 200 200 200 200 200 429 429 429
  ```
- Screenshot: [dashboard](screenshots/dashboard.png) · [running](screenshots/running.png) · [test](screenshots/test.png)

### So sánh `railway.toml` vs `render.yaml`
| Tiêu chí | `railway.toml` | `render.yaml` (Blueprint) |
| --- | --- | --- |
| Định dạng & phạm vi | TOML — cấu hình **1 service** hiện tại | YAML — khai báo **nhiều services/databases** (Infrastructure-as-Code cho cả stack) |
| Build & Healthcheck | `[build] builder = "DOCKERFILE"`, `[deploy] healthcheckPath = "/health"` | `runtime: docker`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health` |
| Biến môi trường & Secret | Không khai báo env trong file; đặt qua Railway Dashboard hoặc `railway variables set` | Khai báo trực tiếp `envVars` trong YAML; secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập tay trên dashboard, không commit lên Git) |
| Lý do khác nhau | Railway ưu tiên CLI/Dashboard nhanh gọn cho từng service | Render Blueprint quản lý đồng bộ cấu hình service + env + restart policy trong một file YAML |

### Exercise 3.3: Pipeline CI/CD Cloud Run (`03-cloud-deployment/production-cloud-run/`)
Dựa trên `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD đi qua 4 bước tuần tự khi có trigger (push lên `main`):
1. **Test (`test`):** Dùng image `python:3.11-slim`, cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`.
2. **Build (`build`):** Dùng `gcr.io/cloud-builders/docker` build image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from`).
3. **Push (`push`):** Đẩy image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Dùng `gcloud run deploy` triển khai lên Cloud Run (`asia-southeast1`, `min-instances=1` tránh cold start, `max-instances=10`, `512Mi` RAM), kết hợp `service.yaml` để gắn secret từ Secret Manager (`OPENAI_API_KEY`, `AGENT_API_KEY`) và cấu hình `livenessProbe` (`/health`) + `startupProbe` (`/ready`).

---

## Part 6: Final Project — `check_production_ready.py` Output (CP5)

Chạy bản đầy đủ (có Docker) trong WSL Ubuntu, Python 3.11 — trên Windows script không gửi được SIGTERM nên mục Graceful shutdown luôn báo ⚠️:

```bash
cd 06-lab-complete
python check_production_ready.py --public-url https://agent-api-production-cf0a9942.up.railway.app
```

Chi tiết đáng chú ý: build image 37s, image `238 MB`; SIGTERM lúc đang có request → request vẫn `200`, process thoát exit code `0`; `docker stop` exit code `0` trong `0.9s`; Public URL `GET /health → 200`.

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 44/44 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

---

## Part 4: API Security (CP3)

### Exercise 4.1–4.3: Test results (output `curl -i`, chạy lại 2026-11-25 trong WSL; token đã che)

**Exercise 4.1 — bản `develop` (`04-api-gateway/develop`, `AGENT_API_KEY=secret-key-123 python app.py`):**
```text
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"hello"}'
HTTP/1.1 401 Unauthorized
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"hello"}'
HTTP/1.1 200 OK
server: uvicorn
content-length: 122
content-type: application/json

{"question":"hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

**Exercise 4.2 — bản `production` (`04-api-gateway/production`, JWT, tài khoản `student` / `demo123`):**
```text
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"access_token":"<đã che>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer <đã che>"}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"what is docker?"}'   # không có token
HTTP/1.1 401 Unauthorized
server: uvicorn
www-authenticate: Bearer
content-type: application/json

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

**Exercise 4.3 — rate limit 10 req/phút (11 request liên tiếp với cùng token):**
```text
$ for i in $(seq 1 11); do curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"question":"what is docker?"}'; done
--- request 1
HTTP/1.1 200 OK
{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
--- request 2 → 9: HTTP/1.1 200 OK
--- request 10
HTTP/1.1 200 OK
{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":0,"budget_remaining_usd":0.000189}}
--- request 11
HTTP/1.1 429 Too Many Requests
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```
Request thứ 11 bị chặn `429` kèm header `Retry-After: 59` và `X-RateLimit-*` (sliding window 60s); `requests_remaining` giảm dần 9 → 0 qua 10 request đầu.

### Exercise 4.4: Cost guard implementation
- **Mục đích:** Rate limit chỉ giới hạn *tốc độ* (số request/phút), còn Cost Guard giới hạn *chi phí* (ngân sách USD/ngày) vì một prompt hoặc response dài có thể tốn nhiều token hơn nhiều request ngắn.
- **Cách triển khai trong `04-api-gateway/production/cost_guard.py`:**
  1. Theo dõi `UsageRecord` theo `user_id` và ngày (`YYYY-MM-DD`), cộng dồn `input_tokens`, `output_tokens` và tính `total_cost_usd` theo đơn giá trên 1K tokens.
  2. Trước khi gọi LLM, `check_budget(user_id)` kiểm tra: nếu tổng chi phí hệ thống vượt `global_daily_budget_usd` ($10/ngày) thì trả `503`; nếu chi phí user vượt `daily_budget_usd` ($1/ngày) thì chặn và trả `402 Payment Required`; nếu đạt ngưỡng cảnh báo (`warn_at_pct = 0.8`) thì ghi log warning.
  3. Sau khi gọi LLM, `record_usage()` cập nhật token và chi phí thực tế. Trong production nhiều instance, trạng thái này cần lưu trong Redis thay vì RAM.

---

## Part 5: Scaling & Reliability (CP4)

### Exercise 5.1–5.3: Health check, Graceful shutdown & Stateless design
- **Liveness (`/health`) vs Readiness (`/ready`):**
  - `/health` trả lời câu hỏi *"process có còn sống không?"* — dùng để platform quyết định restart container nếu app bị treo. Khi mất Redis, process vẫn sống nên `/health` vẫn nên trả `200`.
  - `/ready` trả lời câu hỏi *"app có sẵn sàng nhận traffic chưa?"* — dùng để Load Balancer quyết định có route request vào instance này không. Khi mất dependency quan trọng (như Redis) hoặc đang shutdown, `/ready` trả `503`.
- **Vì sao state trong RAM bị hỏng khi scale nhiều instance:**
  - Nếu lưu session history hoặc rate-limit counter trong biến Python trên RAM, request 1 vào `agent-1` sẽ chỉ lưu trên `agent-1`. Request 2 qua Load Balancer sang `agent-2` sẽ không thấy dữ liệu cũ → mất ngữ cảnh hội thoại hoặc vượt rate limit.
  - Giải pháp: đưa toàn bộ shared state (session history, rate limit, cost guard) ra **Redis** dùng chung cho mọi replica.

### Exercise 5.1: Kết quả `/health` và `/ready` (`05-scaling-reliability/develop/app.py`)
```text
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":1.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:26:35.044177+00:00","checks":{"memory":{"status":"ok","used_percent":36.7}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```
`/ready` trả `503` khi app chưa khởi động xong hoặc đang shutdown (cờ `_is_ready` bật trong `lifespan` startup, tắt khi shutdown); bản Part 6 còn trả `503` khi mất Redis (đã kiểm bởi `check_production_ready.py`: "Redis mất kết nối → /ready 503, /health vẫn 200").

### Exercise 5.2: Graceful shutdown — test SIGTERM khi đang có request
Chạy trong WSL Ubuntu (Windows không gửi được SIGTERM): bật app, gửi `POST /ask` rồi **ngay lập tức** `kill -TERM`:
```text
$ curl -X POST "http://localhost:8000/ask?question=Long%20task" &   # gửi request
$ kill -TERM 2122   # ngay lập tức
process exit code: 0
--- kết quả request đang chạy:
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}  -> HTTP 200
--- log server:
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 10:26:38,342 INFO 🔄 Graceful shutdown initiated...
2026-11-25 10:26:38,342 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [2122]
2026-11-25 10:26:38,343 INFO Received signal 15 — uvicorn will handle graceful shutdown
```
- **Request đang chạy có hoàn thành không?** Có — trả `HTTP 200` dù SIGTERM đến ngay sau khi gửi; process tự thoát với exit code `0`.
- **Cơ chế:** uvicorn bắt SIGTERM → (1) ngừng nhận connection mới, (2) chờ các request in-flight xử lý xong, (3) chạy phần shutdown của `lifespan` (đặt `_is_ready=False` để `/ready` trả 503 → load balancer ngừng gửi traffic, rồi chờ `_in_flight_requests` về 0, tối đa 30s), (4) thoát. Handler `signal.signal(SIGTERM, ...)` trong app chỉ ghi log, **không** gọi `sys.exit()` để không cắt ngang cơ chế của uvicorn.
- Trên container (Part 6): `docker stop` → exit code `0` trong `0.9s` (Dockerfile dùng `exec uvicorn ...` để uvicorn là PID 1 và nhận được SIGTERM).

### Exercise 5.4–5.5: Kết quả chạy 3 replicas + Redis + Nginx (`05-scaling-reliability/production/`)
- Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py` (cổng `8080`, endpoint `POST /chat`):
  ```text
  Session ID: 87f0f6ac-14b7-4886-9e36-c88daaa42911
  Request 1: [instance-f4ce0a]  -> Q: What is Docker?
  Request 2: [instance-7da3ea]  -> Q: Why do we need containers?
  Request 3: [instance-4b8ac7]  -> Q: What is Kubernetes?
  Request 4: [instance-f4ce0a]  -> Q: How does load balancing work?
  Request 5: [instance-7da3ea]  -> Q: What is Redis used for?

  Total requests: 5
  Instances used: {'instance-7da3ea', 'instance-f4ce0a', 'instance-4b8ac7'}
  ✅ All requests served despite different instances!
  Total messages in history: 10 (5 user + 5 assistant)
  ✅ Session history preserved across all instances via Redis!
  ```
- **Giải thích:** Nginx phân tải round-robin qua 3 container `agent` khác nhau (`instance-f4ce0a`, `instance-7da3ea`, `instance-4b8ac7`), nhưng cả 5 lượt hỏi trong cùng `session_id` đều đọc/ghi chung vào Redis nên lịch sử hội thoại 10 tin nhắn được giữ nguyên vẹn. Đã dọn stack bằng `docker compose -p k5-day14-scaling down -v`.

---

## AI Log
- **Phiên làm việc (CP0–CP4):** Dùng AI hỗ trợ kiểm tra môi trường (Python, Docker, WSL2), chạy kiểm thử các endpoint của Part 1 và Part 4 trên localhost, build các Docker image Part 2, chạy Docker Compose stack Part 2 & Part 5 (`--scale agent=3` + `test_stateless.py`), và tổng hợp kết quả đo thực tế vào `MISSION_ANSWERS.md`. Đã tự kiểm tra lại toàn bộ status code (200, 401, 429), kích thước image (`1.67 GB` vs `240 MB`) và output `test_stateless.py`.
- **Phiên làm việc (CP5–CP6):** Dùng AI hỗ trợ hoàn thiện các file TODO trong `06-lab-complete/` (`app/config.py`, `app/redis_client.py`, `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`), chạy `python check_production_ready.py` (đạt 42/42 checks passed), so sánh `railway.toml` vs `render.yaml`, mô tả pipeline `cloudbuild.yaml`/`service.yaml` và tạo khung `DEPLOYMENT.md`.
- **Phiên làm việc (CP6 — deploy & chấm lại):** Dùng AI (Claude Code) rà soát bài so với `RUBRIC.md`/`SUBMISSION.md`, hướng dẫn deploy Railway (tạo Redis, service `agent-api`, đặt biến trên tab Variables, sửa lỗi upload 404 do service cũ không nằm trong environment `production`). AI chạy giúp 4 lệnh tự kiểm + vòng lặp rate limit trên URL public (key đọc từ `railway variables`, không in ra) và chạy `check_production_ready.py` trong WSL Ubuntu (Python 3.11) để kiểm tra được SIGTERM → `PASS 12/12`. Docker Hub trả `429 Too Many Requests` khi build nên base image `python:3.11-slim` được tải qua `mirror.gcr.io` rồi tag lại. Tôi đã tự mở URL public, đối chiếu status code và output script chấm.
- **Phiên làm việc (CP8 — Part 7 observability):** Dùng AI (Claude Code) bật stack `-p k5-day14-observability`, chạy Locust headless 30 users, truy vấn Jaeger API v3 tìm trace chậm nhất / trace lỗi và grep log JSON theo `trace_id`, truy vấn Prometheus bằng đúng query của dashboard (tìm đúng timestamp 17:11:25 khớp với ảnh Grafana), chạy thí nghiệm A+C (`MOCK_ERROR_RATE=0.2`, `LLM_MODEL=mock-llm-large`) và D (`docker pause`) với script poll `/api/v1/rules` để ghi thời gian pending/firing. AI phát hiện `LLMCostBurnRateHigh` đã firing từ trước thí nghiệm (tải nền vượt $2/giờ) và một lần đo D bị nhiễu do container vừa tạo lại → đo lại. Tôi tự chụp 4 ảnh Part 7, đối chiếu số trên ảnh với số trong `BENCHMARK_REPORT.md`.
- **Phiên rà soát cuối:** Dùng AI đối chiếu bài với `CHECKPOINTS.md`/`INSTRUCTOR_GUIDE.md`, phát hiện thiếu bằng chứng Exercise 2.4 (test qua Nginx), 4.1–4.3 (output `curl -i`), 5.1–5.2 (output `/health`, `/ready`, test SIGTERM) và câu "scale có cải thiện p95 không" ở mục 5 của report. AI chạy lại các bài test này (Nginx Part 2 qua override cổng 8081 vì IIS chiếm cổng 80; Part 4 và Part 5 trong WSL) và dán output thật; tôi kiểm tra lại từng mã HTTP và log.
