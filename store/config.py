"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


@dataclass(frozen=True)
class Config:
    bot_token: str
    currency: str
    admin_chat_ids: list[str] = field(default_factory=list)


def load_config() -> Config:
    raw_admins = os.getenv("ADMIN_CHAT_IDS", "")
    admin_ids = [chat_id.strip() for chat_id in raw_admins.split(",") if chat_id.strip()]
    return Config(
        bot_token=_require("BOT_TOKEN"),
        currency=os.getenv("CURRENCY", "UAH"),
        admin_chat_ids=admin_ids,
    )
