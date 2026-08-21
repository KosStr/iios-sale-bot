"""Admin access helpers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.services.catalog_filter import format_price
from store.utils.format import cart_summary

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


async def notify_order_chat(
    context: ContextTypes.DEFAULT_TYPE,
    order_id: str,
    order: dict,
    cart,
) -> None:
    """Send a new-order alert to NOTIFY_CHAT_ID (if configured).

    This is a personal notification channel separate from the admin list —
    set NOTIFY_CHAT_ID to your own Telegram chat ID to receive every order
    without granting that account bot-admin privileges.
    """
    chat_id: str = context.bot_data.get("notify_chat_id", "")
    if not chat_id:
        return

    text = "\n".join(
        [
            f"🛒 *Нове замовлення {order_id}*",
            "",
            cart_summary(cart, "USD"),
            "",
            f"Ім'я: {order.get('name', '?')}",
            f"Телефон: {order.get('phone', '?')}",
            f"Адреса: {order.get('address') or 'не вказано'}",
            "",
            f"Разом: *{format_price(cart.total, 'USD')}*",
        ]
    )
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN
        )
    except Exception as err:  # noqa: BLE001
        logger.warning("Failed to send order notification to %s: %s", chat_id, err)
