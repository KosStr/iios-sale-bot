"""Multi-step checkout flow implemented as a ConversationHandler.

Flow: start (button) -> name -> phone -> address -> confirm (buttons).
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

from store.db.orders_repo import save_order
from store.services import cart as cart_service
from store.services.catalog_filter import format_price, get_filter
from store.utils.admin import broadcast_to_admins, user_handle
from store.utils.format import cart_summary

logger = logging.getLogger(__name__)

NAME, PHONE, ADDRESS, CONFIRM = range(4)

_CANCEL_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("✖️ Скасувати замовлення", callback_data="checkout:cancel")]]
)


async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if cart_service.is_empty(update.effective_user.id):
        await query.edit_message_text(
            "Ваш кошик порожній — додайте товари перед оформленням."
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
    context.user_data.setdefault("order", {})["name"] = update.message.text.strip()
    await update.message.reply_text(
        "Чудово. На який номер телефону з вами зв'язатися?",
        reply_markup=_CANCEL_KEYBOARD,
    )
    return PHONE


_SKIP_ADDRESS_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("⏭ Пропустити адресу", callback_data="checkout:skip_address")],
        [InlineKeyboardButton("✖️ Скасувати замовлення", callback_data="checkout:cancel")],
    ]
)


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("order", {})["phone"] = update.message.text.strip()
    await update.message.reply_text(
        "Вкажіть, будь ласка, адресу доставки або пропустіть цей крок.",
        reply_markup=_SKIP_ADDRESS_KEYBOARD,
    )
    return ADDRESS


async def _build_confirm_message(
    order: dict, cart, currency: str
) -> tuple[str, InlineKeyboardMarkup]:
    address_line = f"Адреса: {order['address']}" if order.get("address") else "Адреса: не вказано"
    review = "\n".join(
        [
            "📦 *Підтвердіть, будь ласка, замовлення*",
            "",
            cart_summary(cart, currency),
            "",
            f"Ім'я: {order['name']}",
            f"Телефон: {order['phone']}",
            address_line,
        ]
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Підтвердити замовлення", callback_data="checkout:confirm")],
            [InlineKeyboardButton("✖️ Скасувати замовлення", callback_data="checkout:cancel")],
        ]
    )
    return review, keyboard


async def skip_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    order = context.user_data.setdefault("order", {})
    order["address"] = ""
    cart = cart_service.get_cart(update.effective_user.id)
    currency = get_filter(context).get("currency", "USD")
    review, keyboard = await _build_confirm_message(order, cart, currency)
    await query.message.reply_text(review, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    return CONFIRM


async def collect_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order = context.user_data.setdefault("order", {})
    order["address"] = update.message.text.strip()

    cart = cart_service.get_cart(update.effective_user.id)
    currency = get_filter(context).get("currency", "USD")
    review, keyboard = await _build_confirm_message(order, cart, currency)
    await update.message.reply_text(review, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
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
    currency = "USD"

    try:
        save_order(
            order_id=order_id,
            user_id=user_id,
            customer_name=order.get("name", ""),
            phone=order.get("phone", ""),
            address=order.get("address", ""),
            cart=cart,
            currency=currency,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save order %s", order_id)
        await query.edit_message_text(
            "На жаль, не вдалося зберегти замовлення. Спробуйте ще раз або зв'яжіться з нами."
        )
        return ConversationHandler.END

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
    handle = user_handle(update.effective_user)
    currency = "USD"
    await broadcast_to_admins(
        context,
        "\n".join([
            f"🔔 *Нове замовлення {order_id}*",
            "",
            cart_summary(cart, currency),
            "",
            f"Клієнт: {order.get('name', '?')} ({handle})",
            f"Телефон: {order.get('phone', '?')}",
            f"Адреса: {order.get('address', '?')}",
        ]),
    )


def build_checkout_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_checkout, pattern=r"^checkout:start$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect_address),
                CallbackQueryHandler(skip_address, pattern=r"^checkout:skip_address$"),
            ],
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
