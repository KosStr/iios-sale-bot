"""Filter screen shown after tapping «Каталог».

Lets the user pick a category, subcategory, currency (UAH/USD) and price range,
then renders the matching products as a catalog list.

The wizard step is kept in ``flt["ui"]``: main (category) → sub → price.
Every handler here renders through ``_send_filter`` or ``render_results``,
which are also the only places that answer the callback query.
"""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from store.handlers.catalog import render_results
from store.keyboards import filter_keyboard, group_variants_keyboard
from store.services.catalog_filter import (
    CATEGORY_LABELS,
    category_has_subcategories,
    filter_products,
    filter_summary,
    get_filter,
    has_price_filter,
)
from store.services.grouping import find_group
from store.utils.tg import edit_or_resend


def _filter_text(flt: dict) -> str:
    summary = filter_summary(flt)
    ui = flt.get("ui", "main")
    if ui == "sub":
        category = CATEGORY_LABELS.get(flt.get("category", "all"), "Категорія")
        return (
            f"🔍 *{category}*\n\n{summary}\n\n"
            "Оберіть підкатегорію та натисніть «Далі»."
        )
    if ui == "price":
        return f"🔍 *Ціна*\n\n{summary}\n\nОберіть валюту та діапазон ціни."
    return f"🔍 *Фільтр товарів*\n\n{summary}\n\nОберіть категорію."


async def _send_filter(update: Update, flt: dict) -> None:
    """Render the current filter step, editing the message when possible."""
    text = _filter_text(flt)
    keyboard = filter_keyboard(flt)
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


async def _advance_after_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, flt: dict
) -> None:
    """Category/subcategory is set: go to the price step, or straight to results."""
    if has_price_filter(flt):
        flt["ui"] = "price"
        await _send_filter(update, flt)
        return
    await render_results(update, context, flt)


async def open_filter_for_catalog(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    flt = get_filter(context)
    flt["ui"] = "main"
    await _send_filter(update, flt)


async def reopen_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reopen the filter at the most relevant step for the current selection."""
    flt = get_filter(context)
    category = flt.get("category", "all")
    if category == "all":
        flt["ui"] = "main"
    elif category_has_subcategories(category):
        flt["ui"] = "sub"
    elif has_price_filter(flt):
        flt["ui"] = "price"
    else:
        flt["ui"] = "main"
    await _send_filter(update, flt)


async def to_price_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Advance from the subcategory step to price (or results if too few products)."""
    await _advance_after_category(update, context, get_filter(context))


async def back_to_main_filter(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Context-aware back: price → sub (or main), sub → main."""
    flt = get_filter(context)
    if flt.get("ui") == "price" and category_has_subcategories(
        flt.get("category", "all")
    ):
        flt["ui"] = "sub"
    else:
        flt["ui"] = "main"
        flt["subcategory"] = "all"
    await _send_filter(update, flt)


async def set_filter_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle flt:cat/sub/cur/price taps and re-render the relevant step."""
    _, field, value = update.callback_query.data.split(":", 2)
    flt = get_filter(context)

    if field == "cat":
        flt["category"] = value
        flt["subcategory"] = "all"
        flt["price"] = "any"
        if category_has_subcategories(value):
            flt["ui"] = "sub"
            await _send_filter(update, flt)
        else:
            await _advance_after_category(update, context, flt)
        return

    if field == "sub":
        flt["subcategory"] = value
        flt["price"] = "any"
        await _advance_after_category(update, context, flt)
        return

    if field == "cur":
        flt["currency"] = value
        flt["price"] = "any"
    elif field == "price":
        flt["price"] = value

    await _send_filter(update, flt)


async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_results(update, context, get_filter(context))


async def show_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Expand a multi-variant model into its variant list."""
    flt = get_filter(context)
    key = update.callback_query.data.split(":", 1)[1]
    group = find_group(key, filter_products(flt))

    if group is None:
        await render_results(update, context, flt)
        return

    await edit_or_resend(
        update,
        context,
        f"📦 *{group.label}*\n\nОберіть варіант:",
        group_variants_keyboard(group, flt.get("currency", "UAH")),
    )
