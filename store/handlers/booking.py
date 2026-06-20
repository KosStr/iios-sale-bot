"""Reservation ("Забронювати") flow as a ConversationHandler.

Started from the «Забронювати» button on a product card. Then: name -> phone -> confirm.
On confirm, admins are notified.
"""

from __future__ import annotations

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from store.data.products import get_product_by_id
from store.db.orders_repo import save_booking

logger = logging.getLogger(__name__)

NAME, PHONE, CONFIRM = range(3)

# Matches "book:<product_id>" but not the control actions.
_PRODUCT_PATTERN = r"^book:(?!cancel$|confirm$).+$"

_CANCEL_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖️ Скасувати", callback_data="book:cancel")]]
)


async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 1)[1]
    product = get_product_by_id(product_id)

    if not product:
        await query.edit_message_text("Цю модель не знайдено.")
        return ConversationHandler.END

    context.user_data["booking"] = {"model": product.name, "product_id": product.id}
    await query.message.reply_text(
        f"📅 Ви бронюєте: *{product.name}*\n\nВкажіть ваше ім'я (ПІБ).",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL_KEYBOARD,
    )
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["booking"]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Вкажіть номер телефону для зв'язку.", reply_markup=_CANCEL_KEYBOARD
    )
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    booking = context.user_data["booking"]
    booking["phone"] = update.message.text.strip()

    review = "\n".join(
        [
            "📋 *Підтвердіть бронювання*",
            "",
            f"Модель: {booking['model']}",
            f"Ім'я: {booking['name']}",
            f"Телефон: {booking['phone']}",
        ]
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Підтвердити", callback_data="book:confirm")],
            [InlineKeyboardButton("✖️ Скасувати", callback_data="book:cancel")],
        ]
    )
    await update.message.reply_text(
        review, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
    return CONFIRM


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    booking = context.user_data.get("booking", {})
    booking_id = f"BR-{int(time.time()):X}"

    try:
        save_booking(
            booking_id=booking_id,
            user_id=update.effective_user.id,
            product_id=booking.get("product_id", ""),
            customer_name=booking.get("name", ""),
            phone=booking.get("phone", ""),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save booking %s", booking_id)
        await query.edit_message_text(
            "На жаль, не вдалося зберегти бронювання. Спробуйте ще раз або зв'яжіться з нами."
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "\n".join(
            [
                "✅ *Бронювання прийнято!*",
                "",
                f"Номер: *{booking_id}*",
                f"Модель: {booking.get('model', '?')}",
                "",
                "Ми зв'яжемося з вами для підтвердження. Дякуємо! 🎉",
            ]
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    await _notify_admins(update, context, booking_id, booking)

    context.user_data.pop("booking", None)
    return ConversationHandler.END


async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer("Бронювання скасовано.")
        await query.message.reply_text("Бронювання скасовано. Напишіть /start, щоб продовжити.")
    else:
        await update.message.reply_text("Бронювання скасовано.")
    context.user_data.pop("booking", None)
    return ConversationHandler.END


async def _notify_admins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    booking_id: str,
    booking: dict,
) -> None:
    admin_ids = context.bot_data.get("admin_chat_ids", [])
    if not admin_ids:
        return

    user = update.effective_user
    handle = f"@{user.username}" if user.username else f"id {user.id}"
    message = "\n".join(
        [
            f"🔔 *Нове бронювання {booking_id}*",
            "",
            f"Модель: {booking.get('model', '?')}",
            f"Клієнт: {booking.get('name', '?')} ({handle})",
            f"Телефон: {booking.get('phone', '?')}",
        ]
    )
    for chat_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN
            )
        except Exception as err:  # noqa: BLE001 - log and continue
            logger.warning("Failed to notify admin %s: %s", chat_id, err)


def build_booking_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_booking, pattern=_PRODUCT_PATTERN)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            CONFIRM: [
                CallbackQueryHandler(confirm_booking, pattern=r"^book:confirm$"),
                CallbackQueryHandler(cancel_booking, pattern=r"^book:cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_booking, pattern=r"^book:cancel$"),
            CommandHandler("cancel", cancel_booking),
        ],
        allow_reentry=True,
    )
