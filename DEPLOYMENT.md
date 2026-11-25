# Deployment Information

## Public URL
https://agent-api-production-cf0a9942.up.railway.app

## Platform
Railway (project `outstanding-solace`, service `agent-api` + Redis, environment `production`)

## Test Commands

### Health Check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-api-production-cf0a9942.up.railway.app/health"
# Expected: 200
```

### Readiness Check (Redis connected)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-api-production-cf0a9942.up.railway.app/ready"
# Expected: 200
```

### API Test (no key -> 401, with key -> 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-api-production-cf0a9942.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# Expected: 401

curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-api-production-cf0a9942.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
```

## Environment Variables Set
- `PORT` (do nền tảng tự cấp)
- `ENVIRONMENT=production`
- `REDIS_URL` (trỏ tới Redis service trên nền tảng)
- `AGENT_API_KEY` (đặt trên dashboard/CLI, không ghi vào code)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Kết quả test thực tế (2026-11-25)
```text
GET  /health               -> 200 {"status":"ok"}
GET  /ready                -> 200 {"status":"ready"}
POST /ask (không key)      -> 401 {"detail":"Invalid or missing API key"}
POST /ask (có X-API-Key)   -> 200 {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
12 request liên tiếp       -> 200 x9, rồi 429 429 429 (rate limit 10 req/phút)
```

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
