"""Admin product list, edit and delete (/products)."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from functools import wraps
from html import escape

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

from store.models.product import (
    CATEGORY_ACCESSORIES,
    Product,
    get_all_products,
    is_on_sale,
    synced_sale_prices,
)
from store.db import cart_repo, products_repo
from store.handlers.admin.ui import (
    PAGE_SIZE,
    delete_confirm_keyboard,
    edit_category_keyboard,
    edit_menu_keyboard,
    edit_subcategory_keyboard,
    force_delete_keyboard,
    hot_list_keyboard,
    hot_list_text,
    product_detail_keyboard,
    product_detail_text,
    product_list_keyboard,
    sold_delete_confirm_keyboard,
)
from store.services.catalog_filter import category_has_subcategories
from store.services.channel_sync import delete_product_post, sync_product_post
from store.services.grouping import fits_group_key
from store.services.hot_deals import publish_hot_deals, refresh_if_hot
from store.services.site_catalog import request_catalog_refresh
from store.services.images import upload_image
from store.utils.admin import is_admin
from store.utils.tg import photo_file_id

logger = logging.getLogger(__name__)

EDIT_INPUT = 0

_FIELD_PROMPTS = {
    "name": "Надішліть нову *назву* товару:",
    "price": "Надішліть нову *ціну в USD* (число):",
    "uah": "Надішліть нову *ціну в грн* (число). Надішліть `-`, щоб прибрати:",
    "stock": "Надішліть нову *кількість на складі* (ціле число):",
    "group": (
        "Надішліть назву *моделі* — товари з однаковою моделлю показуються "
        "одним рядком у каталозі.\nНадішліть `-`, щоб зробити товар окремим:"
    ),
    "photo": "Надішліть нове *фото* товару:",
}


def _sale_prompt(product: Product) -> str:
    if product.price_uah:
        currency = "в грн"
        other = " Ціну в USD буде перераховано з тією ж знижкою." if product.price else ""
    else:
        currency = "в USD"
        other = ""
    return (
        f"Надішліть *акційну ціну {currency}* (менше за звичайну). Звичайна ціна "
        f"буде закреслена в боті, каналі та на сайті.{other}\n"
        "Надішліть `-`, щоб прибрати акцію:"
    )


def _resync_sale(product_id: str) -> str:
    """Keep the sale consistent after a regular price changed.

    The sale amount in the main currency stays as typed; the other currency is
    recomputed from the new prices. Returns a note for the admin, or "".
    """
    product = products_repo.fetch_by_id(product_id)
    if not product or not is_on_sale(product):
        return ""
    if product.price_uah and product.sale_price_uah:
        amount = product.sale_price_uah
    elif product.price_uah and product.sale_price and product.price:
        amount = round(product.price_uah * product.sale_price / product.price)
    elif not product.price_uah and product.sale_price:
        amount = product.sale_price
    else:
        amount = None
    regular = product.price_uah or product.price
    if amount is None:
        products_repo.update(product_id, sale_price=None, sale_price_uah=None, sale_until=None)
        return "\n⚠️ Змінилась валюта ціни — акцію прибрано, задайте акційну ціну знову."
    if amount >= regular:
        products_repo.update(product_id, sale_price=None, sale_price_uah=None, sale_until=None)
        return "\n⚠️ Акційна ціна вже не менша за звичайну — акцію прибрано."
    sale_usd, sale_uah = synced_sale_prices(product, amount)
    products_repo.update(product_id, sale_price=sale_usd, sale_price_uah=sale_uah)
    return ""


_LANDING_FAILED = "\n\n⚠️ Не вдалося оновити лендінг (R2). Спробуйте /hot → 🔄 Оновити лендінг."


async def _deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer("Доступ заборонено.", show_alert=True)
    elif update.message:
        await update.message.reply_text("Ця команда лише для адміністраторів.")


def admin_only(handler):
    """Reject non-admins before running `handler`.

    Returns ``ConversationHandler.END`` on denial, which also ends a
    conversation when `handler` is an entry point (plain handlers ignore it).
    """
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update, context):
            await _deny(update, context)
            return ConversationHandler.END
        return await handler(update, context)

    return wrapper


def _edit_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("admin_edit", {})


def _clear_edit(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_edit", None)


@admin_only
async def cmd_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_product_list(update, context, page=0)


async def _send_product_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int
) -> None:
    products = get_all_products()
    total = len(products)
    if total == 0:
        text = "📋 *Товари*\n\nКаталог порожній. Додайте товар командою /add."
        keyboard = product_list_keyboard([], 0)
    else:
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages - 1)
        text = f"📋 *Товари* ({total})\n\nСторінка {page + 1}/{pages}\nОберіть товар:"
        sold_count = sum(1 for p in products if p.stock <= 0)
        keyboard = product_list_keyboard(products, page, sold_count)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


@admin_only
async def list_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    page = int(update.callback_query.data.rsplit(":", 1)[1])
    await _send_product_list(update, context, page)


@admin_only
async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    await query.edit_message_text(
        product_detail_text(product),
        parse_mode=ParseMode.HTML,
        reply_markup=product_detail_keyboard(product_id),
    )


@admin_only
async def open_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    await query.edit_message_text(
        f"✏️ <b>Редагування</b>\n\n{product_detail_text(product)}\n\nЩо змінити?",
        parse_mode=ParseMode.HTML,
        reply_markup=edit_menu_keyboard(product_id, product.is_hot),
    )


@admin_only
async def toggle_hot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    products_repo.update(product_id, is_hot=int(not product.is_hot))
    if product.is_hot:
        message = "✅ Прибрано з гарячих пропозицій."
    elif product.stock > 0:
        message = "🔥 Додано до гарячих пропозицій."
    else:
        message = "🔥 Додано до гарячих, але товару немає в наявності — на сайті не з'явиться."
    if not await publish_hot_deals():
        message += _LANDING_FAILED

    updated = products_repo.fetch_by_id(product_id)
    await query.edit_message_text(
        f"{escape(message)}\n\n{product_detail_text(updated)}",
        parse_mode=ParseMode.HTML,
        reply_markup=edit_menu_keyboard(product_id, updated.is_hot),
    )


@admin_only
async def cmd_hot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    products = products_repo.fetch_hot()
    await update.message.reply_text(
        hot_list_text(products),
        parse_mode=ParseMode.HTML,
        reply_markup=hot_list_keyboard(products),
    )


@admin_only
async def republish_hot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if await publish_hot_deals():
        await query.answer("✅ Лендінг оновлено.")
    else:
        await query.answer("⚠️ Не вдалося оновити лендінг (R2).", show_alert=True)


@admin_only
async def ask_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    in_carts = cart_repo.count_users_with_product(product_id)
    cart_note = (
        f"\n\n⚠️ Товар є в кошику у <b>{in_carts}</b> користувача(-ів). "
        "Він буде автоматично видалений з їхніх кошиків."
        if in_carts > 0
        else ""
    )
    await query.edit_message_text(
        f"🗑 <b>Видалити товар?</b>\n\n<b>{escape(product.name)}</b>\n"
        f"<code>{escape(product.id)}</code>\n\nЦю дію не можна скасувати.{cart_note}",
        parse_mode=ParseMode.HTML,
        reply_markup=delete_confirm_keyboard(product_id),
    )


@admin_only
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 2)[2]

    # Fetch before deleting so we can remove the channel post.
    product_to_delete = products_repo.fetch_by_id(product_id)

    try:
        products_repo.delete(product_id)
    except sqlite3.IntegrityError:
        await query.answer()
        name = escape(product_to_delete.name) if product_to_delete else escape(product_id)
        await query.edit_message_text(
            f"⚠️ Товар <b>{name}</b> є в замовленнях або бронюваннях.\n\n"
            "Видалити все одно? Пов'язані записи в замовленнях і бронюваннях будуть очищені.",
            parse_mode=ParseMode.HTML,
            reply_markup=force_delete_keyboard(product_id),
        )
        return
    except Exception:  # noqa: BLE001
        logger.exception("Failed to delete product %s", product_id)
        await query.answer()
        await query.edit_message_text("❌ Не вдалося видалити товар.")
        return

    await _after_delete(update, context, product_to_delete)


async def _after_delete(
    update: Update, context: ContextTypes.DEFAULT_TYPE, product: Product | None
) -> None:
    """Remove the channel post / landing slide, then show the product list.

    Answers the callback query exactly once — answering it twice makes
    Telegram reject the second call, which used to abort this flow.
    """
    query = update.callback_query
    error = await delete_product_post(context.bot, product) if product else None
    if error:
        # Alerts are capped at 200 chars.
        await query.answer(
            f"⚠️ Пост у каналі не видалено, позначено «❌ ПРОДАНО».\n{error}"[:200],
            show_alert=True,
        )
        # Alerts can't hold links, so send the post link to delete it by hand.
        await query.message.reply_text(
            f"🔗 Пост товару <b>{escape(product.name)}</b> у каналі:\n"
            f"{escape(product.channel_post_url)}",
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.answer()
    if product:
        await refresh_if_hot(product)
    await _send_product_list(update, context, page=0)


@admin_only
async def force_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    product_id = query.data.split(":", 2)[2]

    product_to_delete = products_repo.fetch_by_id(product_id)

    try:
        products_repo.force_delete(product_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to force-delete product %s", product_id)
        await query.answer()
        await query.edit_message_text("❌ Не вдалося видалити товар.")
        return

    await _after_delete(update, context, product_to_delete)


def _sold_products() -> list[Product]:
    return [p for p in get_all_products() if p.stock <= 0]


@admin_only
async def ask_delete_sold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    sold = _sold_products()
    if not sold:
        await _send_product_list(update, context, page=0)
        return

    names = [f"• {escape(p.name)} · <code>{escape(p.id)}</code>" for p in sold[:30]]
    if len(sold) > 30:
        names.append(f"…і ще {len(sold) - 30}")
    await query.edit_message_text(
        f"🗑 <b>Видалити всі продані товари ({len(sold)})?</b>\n"
        "Товари з нульовим складом буде видалено з бота, а їхні пости — з каналу.\n\n"
        + "\n".join(names)
        + "\n\nПости, старші за 48 год, Telegram не дає видалити ботам — їх буде "
        "позначено «❌ ПРОДАНО», а посилання на них надіслано вам.",
        parse_mode=ParseMode.HTML,
        reply_markup=sold_delete_confirm_keyboard(),
    )


@admin_only
async def confirm_delete_sold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Видаляю…")
    deleted: list[Product] = []
    skipped: list[Product] = []
    leftover_posts: list[Product] = []
    for product in _sold_products():
        try:
            products_repo.delete(product.id)
        except sqlite3.IntegrityError:
            skipped.append(product)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Failed to delete sold product %s", product.id)
            skipped.append(product)
            continue
        deleted.append(product)
        if await delete_product_post(context.bot, product):
            leftover_posts.append(product)
    await refresh_if_hot(*deleted)

    lines = [f"🗑 Видалено з бота: <b>{len(deleted)}</b>"]
    if skipped:
        lines += [
            "",
            f"⚠️ Не видалено (є в замовленнях або бронюваннях) — видаліть вручну: "
            f"<b>{len(skipped)}</b>",
        ]
        lines += [f"• {escape(p.name)} · <code>{escape(p.id)}</code>" for p in skipped]
    if leftover_posts:
        lines += [
            "",
            f"❌ Пости позначено «ПРОДАНО», бо вони старші за 48 год — видаліть "
            f"їх у каналі вручну: <b>{len(leftover_posts)}</b>",
        ]
        lines += [
            f"• {escape(p.name)}: {escape(p.channel_post_url)}" for p in leftover_posts
        ]

    # Split into messages under Telegram's 4096-char limit.
    chunks: list[str] = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) + 1 > 4000:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    chunks.append(current)

    back = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ До списку", callback_data="adm:page:0")]]
    )
    for i, chunk in enumerate(chunks):
        markup = back if i == len(chunks) - 1 else None
        if i == 0:
            await query.edit_message_text(
                chunk, parse_mode=ParseMode.HTML, reply_markup=markup,
                disable_web_page_preview=True,
            )
        else:
            await query.message.reply_text(
                chunk, parse_mode=ParseMode.HTML, reply_markup=markup,
                disable_web_page_preview=True,
            )


@admin_only
async def edit_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    product_id = parts[2]
    action = parts[3] if len(parts) > 3 else ""

    if action == "menu":
        await query.edit_message_text(
            "Оберіть *категорію*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=edit_category_keyboard(product_id),
        )
        return

    category = action
    if category_has_subcategories(category):
        context.user_data["admin_cat_pick"] = (product_id, category)
        await query.edit_message_text(
            "Оберіть *підкатегорію*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=edit_subcategory_keyboard(product_id, category),
        )
        return

    was_accessory = _is_accessory(product_id)
    products_repo.update(product_id, category=category, subcategory="")
    await _show_updated_product(
        query, context, product_id, "✅ Категорію оновлено.", was_accessory
    )


@admin_only
async def edit_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    product_id = parts[2]
    subcategory = parts[3] if len(parts) > 3 else ""

    was_accessory = _is_accessory(product_id)
    pending = context.user_data.pop("admin_cat_pick", None)
    if pending and pending[0] == product_id:
        products_repo.update(
            product_id, category=pending[1], subcategory=subcategory
        )
    else:
        products_repo.update(product_id, subcategory=subcategory)
    await _show_updated_product(
        query, context, product_id, "✅ Категорію оновлено.", was_accessory
    )


def _is_accessory(product_id: str) -> bool:
    product = products_repo.fetch_by_id(product_id)
    return bool(product) and product.category == CATEGORY_ACCESSORIES


async def _show_updated_product(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    product_id: str,
    prefix: str,
    was_accessory: bool = False,
) -> None:
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return
    await query.edit_message_text(
        f"{prefix}\n\n{product_detail_text(product)}",
        parse_mode=ParseMode.HTML,
        reply_markup=edit_menu_keyboard(product_id, product.is_hot),
    )
    # Moving into accessories deletes the post; moving out of it creates one.
    channel_id = context.bot_data.get("channel_id", "") if was_accessory else ""
    await sync_product_post(context.bot, product, channel_id=channel_id)


@admin_only
async def start_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, _, product_id, field = query.data.split(":", 3)

    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return ConversationHandler.END

    state = _edit_state(context)
    state["product_id"] = product_id
    state["field"] = field

    await query.message.reply_text(
        _sale_prompt(product) if field == "sale" else _FIELD_PROMPTS[field],
        parse_mode=ParseMode.MARKDOWN,
    )
    return EDIT_INPUT


async def apply_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = _edit_state(context)
    product_id = state.get("product_id")
    field = state.get("field")
    if not product_id or not field:
        _clear_edit(context)
        return ConversationHandler.END

    product = products_repo.fetch_by_id(product_id)
    if not product:
        await update.message.reply_text("Товар не знайдено.")
        _clear_edit(context)
        return ConversationHandler.END

    channel_id = ""
    try:
        if field == "photo":
            file_id = photo_file_id(update.message)
            if not file_id:
                await update.message.reply_text(
                    "Надішліть *фото* (не файл). Спробуйте ще раз або /cancel.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return EDIT_INPUT
            image_key = product.image or f"{product.id}.jpg"
            tg_file = await context.bot.get_file(file_id)
            image_bytes = bytes(await tg_file.download_as_bytearray())
            if not await asyncio.to_thread(upload_image, image_key, image_bytes):
                await update.message.reply_text(
                    "⚠️ Не вдалося завантажити фото в R2. Спробуйте ще раз або /cancel."
                )
                return EDIT_INPUT
            products_repo.update(product_id, image=image_key)
            request_catalog_refresh()
            message = "✅ Фото оновлено."
        else:
            text = update.message.text.strip()
            if field == "name":
                if len(text) < 2:
                    await update.message.reply_text("Назва занадто коротка.")
                    return EDIT_INPUT
                products_repo.update(product_id, name=text)
                message = "✅ Назву оновлено."
            elif field == "price":
                price = int(float(text.replace(",", ".")))
                if price <= 0:
                    await update.message.reply_text("Ціна має бути більше нуля.")
                    return EDIT_INPUT
                products_repo.update(product_id, price=price)
                message = "✅ Ціну оновлено." + _resync_sale(product_id)
            elif field == "stock":
                if not text.isdigit():
                    await update.message.reply_text("Введіть ціле число.")
                    return EDIT_INPUT
                products_repo.update(product_id, stock=int(text))
                message = "✅ Склад оновлено."
                if product.stock <= 0 < int(text):
                    # Restocked: the sold-out post was deleted, post it anew.
                    channel_id = context.bot_data.get("channel_id", "")
            elif field == "group":
                group = "" if text == "-" else text
                if not fits_group_key(group):
                    await update.message.reply_text(
                        "Назва моделі занадто довга. Скоротіть її."
                    )
                    return EDIT_INPUT
                products_repo.update(product_id, product_group=group)
                message = "✅ Модель оновлено."
            elif field in ("uah", "sale"):
                if text == "-":
                    amount = None
                else:
                    amount = int(float(text.replace(",", ".").replace(" ", "")))
                    if amount <= 0:
                        await update.message.reply_text("Ціна має бути більше нуля.")
                        return EDIT_INPUT
                if field == "uah":
                    if amount is None and not product.price:
                        await update.message.reply_text(
                            "Немає ціни в USD — ціну в грн прибрати не можна."
                        )
                        return EDIT_INPUT
                    products_repo.update(product_id, price_uah=amount)
                    message = "✅ Ціну в грн оновлено." + _resync_sale(product_id)
                elif amount is None:
                    products_repo.update(
                        product_id, sale_price=None, sale_price_uah=None, sale_until=None
                    )
                    message = "✅ Акцію прибрано."
                else:
                    regular = product.price_uah or product.price
                    if amount >= regular:
                        await update.message.reply_text(
                            "Акційна ціна має бути меншою за звичайну. Спробуйте ще раз або /cancel."
                        )
                        return EDIT_INPUT
                    sale_usd, sale_uah = synced_sale_prices(product, amount)
                    products_repo.update(
                        product_id, sale_price=sale_usd, sale_price_uah=sale_uah, sale_until=None
                    )
                    message = "✅ Акційну ціну оновлено."
            else:
                await update.message.reply_text("Невідоме поле.")
                _clear_edit(context)
                return ConversationHandler.END
    except (ValueError, TypeError):
        await update.message.reply_text("Невірний формат. Спробуйте ще раз або /cancel.")
        return EDIT_INPUT
    except Exception:  # noqa: BLE001
        logger.exception("Failed to update product %s field %s", product_id, field)
        await update.message.reply_text("❌ Не вдалося зберегти зміни.")
        _clear_edit(context)
        return ConversationHandler.END

    _clear_edit(context)
    updated = products_repo.fetch_by_id(product_id)
    await update.message.reply_text(
        f"{message}\n\n{product_detail_text(updated)}",
        parse_mode=ParseMode.HTML,
        reply_markup=edit_menu_keyboard(product_id, updated.is_hot),
    )
    await sync_product_post(
        context.bot, updated, photo_changed=field == "photo", channel_id=channel_id
    )
    # Name, price, stock and photo all show up on the landing slide.
    await refresh_if_hot(updated)
    return ConversationHandler.END


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_edit(context)
    await update.message.reply_text("Редагування скасовано.")
    return ConversationHandler.END


def build_admin_edit_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_edit_field,
                pattern=r"^adm:efld:[^:]+:(name|price|uah|stock|group|photo|sale)$",
            ),
        ],
        states={
            EDIT_INPUT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, apply_edit_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_edit_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_edit)],
        allow_reentry=True,
    )


def build_admin_product_handlers() -> list:
    return [
        CommandHandler("products", cmd_products),
        CommandHandler("hot", cmd_hot),
        CallbackQueryHandler(toggle_hot, pattern=r"^adm:hot:"),
        CallbackQueryHandler(republish_hot, pattern=r"^adm:hotpub$"),
        CallbackQueryHandler(list_page, pattern=r"^adm:page:\d+$"),
        CallbackQueryHandler(view_product, pattern=r"^adm:view:"),
        CallbackQueryHandler(open_edit_menu, pattern=r"^adm:edit:"),
        CallbackQueryHandler(ask_delete, pattern=r"^adm:del:[^:]+$"),
        CallbackQueryHandler(confirm_delete, pattern=r"^adm:delok:"),
        CallbackQueryHandler(force_delete, pattern=r"^adm:delforce:"),
        CallbackQueryHandler(ask_delete_sold, pattern=r"^adm:soldask$"),
        CallbackQueryHandler(confirm_delete_sold, pattern=r"^adm:soldok$"),
        CallbackQueryHandler(edit_category_menu, pattern=r"^adm:ecat:"),
        CallbackQueryHandler(edit_subcategory, pattern=r"^adm:esub:"),
    ]
