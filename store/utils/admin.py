"""Admin access helpers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    admin_ids: list[str] = context.bot_data.get("admin_chat_ids", [])
    return str(user.id) in admin_ids
