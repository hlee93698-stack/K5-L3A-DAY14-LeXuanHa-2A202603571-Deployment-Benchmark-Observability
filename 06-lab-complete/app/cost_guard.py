"""
Cost guard (tiêu chí 8) — Theo dõi chi phí token trong Redis.
"""
import logging
from datetime import datetime, timezone
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        return
    try:
        current = float(r.get(_budget_key()) or 0.0)
        if current >= settings.daily_budget_usd:
            raise HTTPException(status_code=402, detail="Budget exceeded")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Cost guard check Redis error: {exc}")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K
    if r is None:
        return cost
    try:
        key = _budget_key()
        r.incrbyfloat(key, cost)
        r.expire(key, 172800)
    except Exception as exc:
        logger.warning(f"Cost guard record Redis error: {exc}")
    return cost
