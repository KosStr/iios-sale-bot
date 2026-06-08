"""Cart-related handlers (view, add, remove, clear)."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.data.products import get_product_by_id, is_in_stock
from store.keyboards import cart_keyboard
from store.services import cart as cart_service
from store.services.catalog_filter import get_filter
from store.utils.format import cart_summary
from store.utils.tg import edit_or_resend


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cart = cart_service.get_cart(update.effective_user.id)
    currency = get_filter(context).get("currency", "UAH")
    text = f"🛒 *Ваш кошик*\n\n{cart_summary(cart, currency)}"
    keyboard = cart_keyboard(cart)

    if update.callback_query:
        await edit_or_resend(update, context, text, keyboard)
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 1)[1]
    product = get_product_by_id(product_id)

    if not is_in_stock(product):
        await query.answer("На жаль, цього товару немає в наявності.", show_alert=True)
        return

    cart_service.add_item(update.effective_user.id, product_id, 1)
    await query.answer(f"Додано {product.name} у кошик ✅")
    await show_cart(update, context)


async def remove_from_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 1)[1]
    cart_service.remove_item(update.effective_user.id, product_id)
    await query.answer("Видалено з кошика.")
    await show_cart(update, context)


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    cart_service.clear_cart(update.effective_user.id)
    await query.answer("Кошик очищено.")
    await show_cart(update, context)
