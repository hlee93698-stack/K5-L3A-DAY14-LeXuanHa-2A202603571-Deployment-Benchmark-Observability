"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _get_budget_usd() -> float:
    if "DAILY_BUDGET_USD" in os.environ and os.environ["DAILY_BUDGET_USD"] != "":
        return float(os.environ["DAILY_BUDGET_USD"])
    if "MONTHLY_BUDGET_USD" in os.environ and os.environ["MONTHLY_BUDGET_USD"] != "":
        return float(os.environ["MONTHLY_BUDGET_USD"])
    return 1.0


@dataclass
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )
    daily_budget_usd: float = field(default_factory=_get_budget_usd)


settings = Settings()
