"""Admin access helpers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    admin_ids: list[str] = context.bot_data.get("admin_chat_ids", [])
    return str(user.id) in admin_ids


def user_handle(user) -> str:
    """Return '@username' or 'id <id>' for a Telegram user."""
    return f"@{user.username}" if user.username else f"id {user.id}"


async def broadcast_to_admins(
    context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    """Send a Markdown message to every configured admin chat ID."""
    for chat_id in context.bot_data.get("admin_chat_ids", []):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN
            )
        except Exception as err:  # noqa: BLE001
            logger.warning("Failed to notify admin %s: %s", chat_id, err)
