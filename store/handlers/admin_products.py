"""Admin product list, edit and delete (/products)."""

from __future__ import annotations

import logging
import sqlite3

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from store.data.products import get_all_products
from store.db import products_repo
from store.handlers.admin_ui import (
    PAGE_SIZE,
    category_has_subcategories,
    delete_confirm_keyboard,
    edit_category_keyboard,
    edit_menu_keyboard,
    edit_subcategory_keyboard,
    product_detail_keyboard,
    product_detail_text,
    product_list_keyboard,
)
from store.services.images import upload_image
from store.utils.admin import is_admin

logger = logging.getLogger(__name__)

EDIT_INPUT = 0

_FIELD_PROMPTS = {
    "name": "Надішліть нову *назву* товару:",
    "price": "Надішліть нову *ціну в USD* (число):",
    "stock": "Надішліть нову *кількість на складі* (ціле число):",
    "photo": "Надішліть нове *фото* товару:",
}


async def _deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer("Доступ заборонено.", show_alert=True)
    elif update.message:
        await update.message.reply_text("Ця команда лише для адміністраторів.")


def _edit_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("admin_edit", {})


def _clear_edit(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_edit", None)


async def cmd_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return
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
        keyboard = product_list_keyboard(products, page)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )


async def list_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return
    page = int(update.callback_query.data.rsplit(":", 1)[1])
    await _send_product_list(update, context, page)


async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return

    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    await query.edit_message_text(
        product_detail_text(product),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=product_detail_keyboard(product_id),
    )


async def open_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return

    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    await query.edit_message_text(
        f"✏️ *Редагування*\n\n{product_detail_text(product)}\n\nЩо змінити?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=edit_menu_keyboard(product_id),
    )


async def ask_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return

    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return

    await query.edit_message_text(
        f"🗑 *Видалити товар?*\n\n*{product.name}*\n`{product.id}`\n\nЦю дію не можна скасувати.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=delete_confirm_keyboard(product_id),
    )


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return

    query = update.callback_query
    await query.answer()
    product_id = query.data.split(":", 2)[2]

    try:
        products_repo.delete(product_id)
    except sqlite3.IntegrityError:
        await query.edit_message_text(
            "❌ Не можна видалити: товар є в замовленнях або бронюваннях.\n"
            "Зменшіть склад до 0 або залиште в каталозі."
        )
        return
    except Exception:  # noqa: BLE001
        logger.exception("Failed to delete product %s", product_id)
        await query.edit_message_text("❌ Не вдалося видалити товар.")
        return

    await _send_product_list(update, context, page=0)


async def edit_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return

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

    products_repo.update(product_id, category=category, subcategory="")
    await _show_updated_product(query, product_id, "✅ Категорію оновлено.")


async def edit_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        await _deny(update, context)
        return

    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    product_id = parts[2]
    subcategory = parts[3] if len(parts) > 3 else ""

    pending = context.user_data.pop("admin_cat_pick", None)
    if pending and pending[0] == product_id:
        products_repo.update(
            product_id, category=pending[1], subcategory=subcategory
        )
    else:
        products_repo.update(product_id, subcategory=subcategory)
    await _show_updated_product(query, product_id, "✅ Категорію оновлено.")


async def _show_updated_product(query, product_id: str, prefix: str) -> None:
    product = products_repo.fetch_by_id(product_id)
    if not product:
        await query.edit_message_text("Товар не знайдено.")
        return
    await query.edit_message_text(
        f"{prefix}\n\n{product_detail_text(product)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=edit_menu_keyboard(product_id),
    )


async def start_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update, context):
        await _deny(update, context)
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    _, _, product_id, field = query.data.split(":", 3)

    if not products_repo.fetch_by_id(product_id):
        await query.edit_message_text("Товар не знайдено.")
        return ConversationHandler.END

    state = _edit_state(context)
    state["product_id"] = product_id
    state["field"] = field

    await query.message.reply_text(
        _FIELD_PROMPTS[field],
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

    try:
        if field == "photo":
            photo = update.message.photo[-1]
            image_key = product.image or f"{product.id}.jpg"
            tg_file = await context.bot.get_file(photo.file_id)
            image_bytes = bytes(await tg_file.download_as_bytearray())
            if not upload_image(image_key, image_bytes):
                await update.message.reply_text(
                    "⚠️ Не вдалося завантажити фото в R2. Спробуйте ще раз або /cancel."
                )
                return EDIT_INPUT
            products_repo.update(product_id, image=image_key)
            message = "✅ Фото оновлено."
        else:
            text = update.message.text.strip()
            if field == "name":
                if len(text) < 2:
                    await update.message.reply_text("Назва занадто коротка.")
                    return EDIT_INPUT
                products_repo.update(
                    product_id, name=text, description=text, brand=text.split()[0]
                )
                message = "✅ Назву оновлено."
            elif field == "price":
                price = int(float(text.replace(",", ".")))
                if price <= 0:
                    await update.message.reply_text("Ціна має бути більше нуля.")
                    return EDIT_INPUT
                products_repo.update(product_id, price=price)
                message = "✅ Ціну оновлено."
            elif field == "stock":
                if not text.isdigit():
                    await update.message.reply_text("Введіть ціле число.")
                    return EDIT_INPUT
                products_repo.update(product_id, stock=int(text))
                message = "✅ Склад оновлено."
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
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=edit_menu_keyboard(product_id),
    )
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
                pattern=r"^adm:efld:[^:]+:(name|price|stock|photo)$",
            ),
        ],
        states={
            EDIT_INPUT: [
                MessageHandler(filters.PHOTO, apply_edit_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_edit_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_edit)],
        allow_reentry=True,
    )


def build_admin_product_handlers() -> list:
    return [
        CommandHandler("products", cmd_products),
        CallbackQueryHandler(list_page, pattern=r"^adm:page:\d+$"),
        CallbackQueryHandler(view_product, pattern=r"^adm:view:"),
        CallbackQueryHandler(open_edit_menu, pattern=r"^adm:edit:"),
        CallbackQueryHandler(ask_delete, pattern=r"^adm:del:[^:]+$"),
        CallbackQueryHandler(confirm_delete, pattern=r"^adm:delok:"),
        CallbackQueryHandler(edit_category_menu, pattern=r"^adm:ecat:"),
        CallbackQueryHandler(edit_subcategory, pattern=r"^adm:esub:"),
    ]
