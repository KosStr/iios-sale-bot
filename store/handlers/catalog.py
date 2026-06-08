"""Catalog and product-detail handlers."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.data.products import get_product_by_id
from store.keyboards import catalog_results_keyboard, product_keyboard
from store.services.catalog_filter import filter_products, get_filter
from store.services.images import photo_source
from store.utils.format import product_summary
from store.utils.tg import edit_or_resend, send_photo_or_text


async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the filtered catalog list (used by the 'back to catalog' button)."""
    flt = get_filter(context)
    currency = flt.get("currency", "UAH")
    products = filter_products(flt)

    if not products:
        text = "😕 За вашим фільтром нічого не знайдено.\nЗмініть параметри фільтра."
    else:
        text = f"🛍 *Знайдено товарів: {len(products)}*\n\nОберіть товар, щоб переглянути деталі:"
    keyboard = catalog_results_keyboard(products, currency)

    if update.callback_query:
        await edit_or_resend(update, context, text, keyboard)
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 1)[1]
    product = get_product_by_id(product_id)

    if not product:
        await edit_or_resend(update, context, "На жаль, цей товар більше недоступний.")
        return

    currency = get_filter(context).get("currency", "UAH")
    text = product_summary(product, currency)
    keyboard = product_keyboard(product)
    await send_photo_or_text(update, context, text, keyboard, photo=photo_source(product))
