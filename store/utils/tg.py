"""Telegram message helpers for navigating between text and photo screens.

Because a product card may be a photo message (with a caption) while other
screens are plain text, we can't always use ``edit_message_text``. These
helpers transparently edit when possible and otherwise delete + resend.
"""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes


async def edit_or_resend(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Show a text screen in response to a callback query.

    Edits the current message if it's text; if it's a photo (or editing
    fails), deletes it and sends a fresh text message instead.
    """
    query = update.callback_query
    await _answer(query)
    message = query.message

    if message.photo or message.caption:
        await _delete(message)
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        return

    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    except BadRequest:
        await _delete(message)
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )


async def send_photo_or_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    photo=None,
) -> None:
    """Replace the current callback message with a photo card (caption=text).

    Falls back to a plain text message if there's no photo or sending the
    photo fails (e.g. a bad URL or an empty R2 bucket).
    """
    query = update.callback_query
    await _answer(query)
    message = query.message
    chat_id = message.chat_id
    await _delete(message)

    if photo is not None:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            return
        except BadRequest:
            pass  # fall through to text

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def _answer(query) -> None:
    try:
        await query.answer()
    except BadRequest:
        pass


async def _delete(message) -> None:
    try:
        await message.delete()
    except BadRequest:
        pass
