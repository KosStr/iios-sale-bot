"""Multi-step checkout flow implemented as a ConversationHandler.

Flow: start (button) -> name -> phone -> address -> confirm (buttons).
"""

from __future__ import annotations

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

from store.db.orders_repo import save_order
from store.services import cart as cart_service
from store.services.catalog_filter import format_price, get_filter
from store.utils.format import cart_summary

NAME, PHONE, ADDRESS, CONFIRM = range(4)

_CANCEL_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖️ Скасувати замовлення", callback_data="checkout:cancel")]]
)


async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if cart_service.is_empty(update.effective_user.id):
        await query.edit_message_text(
            "Ваш кошик порожній — додайте телефон перед оформленням."
        )
        return ConversationHandler.END

    context.user_data["order"] = {}
    await query.message.reply_text(
        "🧾 *Оформлення замовлення*\n\nВкажіть ваше повне ім'я (ПІБ).",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CANCEL_KEYBOARD,
    )
    return NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["order"]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Чудово. На який номер телефону з вами зв'язатися?",
        reply_markup=_CANCEL_KEYBOARD,
    )
    return PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["order"]["phone"] = update.message.text.strip()
    await update.message.reply_text(
        "Вкажіть, будь ласка, адресу доставки.", reply_markup=_CANCEL_KEYBOARD
    )
    return ADDRESS


async def collect_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order = context.user_data["order"]
    order["address"] = update.message.text.strip()

    cart = cart_service.get_cart(update.effective_user.id)
    currency = get_filter(context).get("currency", "UAH")
    review = "\n".join(
        [
            "📦 *Підтвердіть, будь ласка, замовлення*",
            "",
            cart_summary(cart, currency),
            "",
            f"Ім'я: {order['name']}",
            f"Телефон: {order['phone']}",
            f"Адреса: {order['address']}",
        ]
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Підтвердити замовлення", callback_data="checkout:confirm")],
            [InlineKeyboardButton("✖️ Скасувати замовлення", callback_data="checkout:cancel")],
        ]
    )
    await update.message.reply_text(
        review, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
    return CONFIRM


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    cart = cart_service.get_cart(user_id)

    if cart.is_empty:
        await query.edit_message_text("Ваш кошик порожній.")
        return ConversationHandler.END

    order_id = f"ORD-{int(time.time()):X}"
    order = context.user_data.get("order", {})
    currency = get_filter(context).get("currency", "UAH")

    await query.edit_message_text(
        "\n".join(
            [
                "✅ *Замовлення підтверджено!*",
                "",
                f"Номер замовлення: *{order_id}*",
                f"Разом: *{format_price(cart.total, currency)}*",
                "",
                "Ми зв'яжемося з вами найближчим часом для узгодження оплати та доставки.",
                "Дякуємо за покупку! 🎉",
            ]
        ),
        parse_mode=ParseMode.MARKDOWN,
    )

    await _notify_admins(update, context, order_id, order, cart)

    save_order(
        order_id=order_id,
        user_id=user_id,
        customer_name=order.get("name", ""),
        phone=order.get("phone", ""),
        address=order.get("address", ""),
        cart=cart,
        currency=currency,
    )

    cart_service.clear_cart(user_id)
    context.user_data.pop("order", None)
    return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer("Замовлення скасовано.")
        await query.message.reply_text(
            "Не проблема — ваш кошик збережено. Напишіть /start, щоб продовжити покупки."
        )
    else:
        await update.message.reply_text(
            "Оформлення скасовано. Ваш кошик збережено."
        )
    context.user_data.pop("order", None)
    return ConversationHandler.END


async def _notify_admins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order_id: str,
    order: dict,
    cart,
) -> None:
    admin_ids = context.bot_data.get("admin_chat_ids", [])
    if not admin_ids:
        return

    user = update.effective_user
    handle = f"@{user.username}" if user.username else f"id {user.id}"
    currency = get_filter(context).get("currency", "UAH")
    message = "\n".join(
        [
            f"🔔 *Нове замовлення {order_id}*",
            "",
            cart_summary(cart, currency),
            "",
            f"Клієнт: {order.get('name', '?')} ({handle})",
            f"Телефон: {order.get('phone', '?')}",
            f"Адреса: {order.get('address', '?')}",
        ]
    )
    for chat_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN
            )
        except Exception as err:  # noqa: BLE001 - log and continue
            print(f"Failed to notify admin {chat_id}: {err}")


def build_checkout_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_checkout, pattern=r"^checkout:start$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_address)],
            CONFIRM: [
                CallbackQueryHandler(confirm_order, pattern=r"^checkout:confirm$"),
                CallbackQueryHandler(cancel_order, pattern=r"^checkout:cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_order, pattern=r"^checkout:cancel$"),
            CommandHandler("cancel", cancel_order),
        ],
        allow_reentry=True,
    )
