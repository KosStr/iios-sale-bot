"""Bot construction: wires commands, buttons, and callback handlers."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from store.config import Config
from store.handlers.booking import build_booking_handler
from store.handlers.cart import add_to_cart, clear_cart, remove_from_cart, show_cart
from store.handlers.catalog import show_catalog, show_product
from store.handlers.checkout import build_checkout_handler
from store.handlers.filters import (
    open_filter_for_catalog,
    reopen_filter,
    set_filter_value,
    show_group,
    show_results,
)
from store.handlers.info import show_contacts, show_location
from store.keyboards import (
    BTN_CART,
    BTN_CATALOG,
    BTN_CONTACTS,
    BTN_HELP,
    BTN_LOCATION,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)

WELCOME = "\n".join(
    [
        "👋 *Ласкаво просимо до IIOS Store!*",
        "",
        "Переглядайте каталог, додавайте товари у кошик і замовляйте у кілька дотиків.",
        "",
        "Скористайтеся меню нижче або кнопками у повідомленнях.",
    ]
)

HELP = "\n".join(
    [
        "*Довідка IIOS Store*",
        "",
        "🛍 *Каталог* — перегляд доступних товарів",
        "🛒 *Кошик* — перегляд товарів та оформлення",
        "📅 *Забронювати* — кнопка на картці товару",
        "📞 *Контакти* — наші контакти",
        "📍 *Локація* — де нас знайти",
        "",
        "Команди:",
        "/start — головне меню",
        "/catalog — одразу до каталогу",
        "/cart — переглянути кошик",
        "/help — показати це повідомлення",
    ]
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        WELCOME, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update caused an error: %s", context.error)


def create_application(config: Config) -> Application:
    app = ApplicationBuilder().token(config.bot_token).build()
    app.bot_data["admin_chat_ids"] = config.admin_chat_ids

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("catalog", open_filter_for_catalog))
    app.add_handler(CommandHandler("cart", show_cart))

    # Multi-step conversations (registered before generic callback handlers)
    app.add_handler(build_booking_handler())
    app.add_handler(build_checkout_handler())

    # Reply-keyboard buttons (plain text)
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(BTN_CATALOG)}$"), open_filter_for_catalog))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(BTN_CART)}$"), show_cart))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(BTN_CONTACTS)}$"), show_contacts))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(BTN_LOCATION)}$"), show_location))
    app.add_handler(MessageHandler(filters.Regex(rf"^{re.escape(BTN_HELP)}$"), help_command))

    # Filter callbacks
    app.add_handler(CallbackQueryHandler(set_filter_value, pattern=r"^flt:(cat|sub|cur|price):"))
    app.add_handler(CallbackQueryHandler(show_results, pattern=r"^flt:show$"))
    app.add_handler(CallbackQueryHandler(reopen_filter, pattern=r"^flt:open$"))
    app.add_handler(CallbackQueryHandler(show_group, pattern=r"^group:"))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(show_catalog, pattern=r"^catalog:view$"))
    app.add_handler(CallbackQueryHandler(show_cart, pattern=r"^cart:view$"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern=r"^cart:clear$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern=r"^product:"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern=r"^add:"))
    app.add_handler(CallbackQueryHandler(remove_from_cart, pattern=r"^remove:"))

    app.add_error_handler(on_error)
    return app
