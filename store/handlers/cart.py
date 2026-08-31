"""Cart-related handlers (view, add, remove, clear)."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.data.products import get_product_by_id, is_in_stock
from store.keyboards import cart_keyboard, main_menu_keyboard
from store.services import cart as cart_service
from store.services.catalog_filter import get_filter
from store.utils.admin import is_admin
from store.utils.format import cart_summary
from store.utils.throttle import throttle
from store.utils.tg import edit_or_resend


@throttle
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


@throttle
async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 1)[1]
    product = get_product_by_id(product_id)

    if not product or not is_in_stock(product):
        await query.answer("На жаль, цього товару немає в наявності.", show_alert=True)
        return

    cart = cart_service.get_cart(update.effective_user.id)
    in_cart = next((item.qty for item in cart.items if item.product.id == product_id), 0)
    if in_cart >= product.stock:
        await query.answer(
            f"У кошику вже {in_cart} шт. — це максимум за наявністю.",
            show_alert=True,
        )
        return

    cart_service.add_item(update.effective_user.id, product_id, 1)
    cart = cart_service.get_cart(update.effective_user.id)
    count = cart.total_qty
    await query.answer(f"Додано {product.name} у кошик ✅")
    # Update the persistent reply-keyboard to show the new cart count.
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🛒 У кошику: {count}",
        reply_markup=main_menu_keyboard(
            admin=is_admin(update, context),
            cart_count=count,
        ),
    )
    await show_cart(update, context)


@throttle
async def remove_from_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 1)[1]
    cart_service.remove_item(update.effective_user.id, product_id)
    count = cart_service.get_cart(update.effective_user.id).total_qty
    await query.answer("Видалено з кошика.")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🛒 У кошику: {count}" if count > 0 else "🛒 Кошик порожній",
        reply_markup=main_menu_keyboard(
            admin=is_admin(update, context),
            cart_count=count,
        ),
    )
    await show_cart(update, context)


@throttle
async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    cart_service.clear_cart(update.effective_user.id)
    await query.answer("Кошик очищено.")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🛒 Кошик порожній",
        reply_markup=main_menu_keyboard(
            admin=is_admin(update, context),
            cart_count=0,
        ),
    )
    await show_cart(update, context)
