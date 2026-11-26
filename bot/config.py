from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _ids(raw: str) -> frozenset[int]:
    return frozenset(int(x) for x in raw.replace(" ", "").split(",") if x.strip().lstrip("-").isdigit())


@dataclass(frozen=True)
class Config:
    bot_token: str
    deepseek_key: str
    deepseek_base_url: str
    model: str
    reasoner_model: str
    temperature: float
    max_tokens: int
    history_limit: int
    db_path: str
    admin_ids: frozenset[int]
    allowed_ids: frozenset[int]
    premium_emoji: str  # auto | on | off

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def is_allowed(self, user_id: int) -> bool:
        return not self.allowed_ids or user_id in self.allowed_ids or user_id in self.admin_ids


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token), ("DEEPSEEK_API_KEY", key)) if not v]
    if missing:
        raise SystemExit(f"Не заданы переменные окружения: {', '.join(missing)} (см. .env.example)")
    mode = os.getenv("PREMIUM_EMOJI", "auto").strip().lower()
    return Config(
        bot_token=token,
        deepseek_key=key,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
        reasoner_model=os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner").strip(),
        temperature=float(os.getenv("TEMPERATURE", "1.0")),
        max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
        history_limit=int(os.getenv("HISTORY_LIMIT", "24")),
        db_path=os.getenv("DB_PATH", "data/bot.db").strip(),
        admin_ids=_ids(os.getenv("ADMIN_IDS", "")),
        allowed_ids=_ids(os.getenv("ALLOWED_USER_IDS", "")),
        premium_emoji=mode if mode in {"auto", "on", "off"} else "auto",
    )
