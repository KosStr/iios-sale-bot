"""Automatic Telegram-channel post management for products.

Set ``CHANNEL_ID`` in the environment (e.g. ``@mychannel`` or ``-1001234567890``)
and make the bot a channel admin with *Post*, *Edit*, and *Delete messages*
permissions.  The bot then:

* Creates a channel post when a product is added via /add.
* Updates the post whenever the product is edited.
* Deletes the post when the product is deleted.

If ``CHANNEL_ID`` is not set every function is a no-op, so the feature is
completely opt-in.

Supported URL shapes (used internally when syncing existing posts)
------------------------------------------------------------------
Public  channel:  https://t.me/<username>/<msg_id>
Private channel:  https://t.me/c/<channel_id>/<msg_id>
"""

from __future__ import annotations

import logging
import re
from html import escape

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from store.data.products import Product
from store.services.catalog_filter import format_price
from store.services.images import get_image_bytes, image_url

logger = logging.getLogger(__name__)

# Matches both  t.me/username/42  and  t.me/c/1234567890/42
_URL_RE = re.compile(
    r"https?://t(?:elegram)?\.me/"
    r"(?:c/(?P<channel_id>\d+)|(?P<username>[A-Za-z]\w{3,}))/"
    r"(?P<msg_id>\d+)",
    re.IGNORECASE,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_url(url: str) -> tuple[str, int] | None:
    """Return (chat_id_str, message_id) or None if the URL is unrecognised."""
    m = _URL_RE.search(url)
    if not m:
        return None
    msg_id = int(m.group("msg_id"))
    if m.group("channel_id"):
        return f"-100{m.group('channel_id')}", msg_id
    return f"@{m.group('username')}", msg_id


def _make_post_url(channel_id: str, message_id: int) -> str:
    """Build a t.me link from a channel_id and message_id."""
    if channel_id.startswith("-100"):
        numeric = channel_id[4:]          # "-1001234567890" → "1234567890"
        return f"https://t.me/c/{numeric}/{message_id}"
    username = channel_id.lstrip("@")
    return f"https://t.me/{username}/{message_id}"


def _post_text(product: Product) -> str:
    """HTML text for a channel post / caption."""
    price = format_price(product.price, "USD")
    stock_line = (
        f"✅ В наявності: {product.stock} шт."
        if product.stock > 0
        else "❌ Немає в наявності"
    )
    parts = [f"<b>{escape(product.name)}</b>  —  {price}", ""]

    if product.brand and product.brand not in ("—", ""):
        parts.append(f"🏷 {escape(product.brand)}")
    if product.storage and product.storage not in ("—", ""):
        parts.append(f"💾 {escape(product.storage)}")
    if product.color and product.color not in ("—", ""):
        parts.append(f"🎨 {escape(product.color)}")
    if product.description and product.description not in ("—", "", product.name):
        parts += ["", escape(product.description)]

    parts += ["", stock_line]
    return "\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def _best_photo(product: Product):
    """Return the best photo source for a channel post.

    Bytes (uploaded directly by the bot) are preferred over a URL because
    Telegram's servers fetch URLs from their own network — which may not have
    access to a private or restricted R2 bucket.  Falls back to a public URL
    when no private credentials are configured, and to None when neither is
    available.
    """
    bytes_ = get_image_bytes(product)
    if bytes_:
        return bytes_
    return image_url(product)   # may be None


async def post_product(bot: Bot, channel_id: str, product: Product) -> str:
    """Send a new channel post for *product*.

    Returns the ``https://t.me/...`` URL of the new message, or ``""`` on
    failure or when *channel_id* is empty.
    """
    if not channel_id:
        return ""

    text = _post_text(product)
    photo = _best_photo(product)

    try:
        if photo:
            msg = await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=text,
                parse_mode=ParseMode.HTML,
            )
        else:
            msg = await bot.send_message(
                chat_id=channel_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        url = _make_post_url(channel_id, msg.message_id)
        logger.info("Channel post created for product %s: %s", product.id, url)
        return url
    except TelegramError as err:
        logger.warning("Could not create channel post for %s: %s", product.id, err)
        return ""


async def sync_product_post(bot: Bot, product: Product) -> None:
    """Edit the channel post linked to *product* to reflect its current state.

    Does nothing if the product has no ``channel_post_url`` or the edit fails.
    """
    if not product.channel_post_url:
        return

    parsed = _parse_url(product.channel_post_url)
    if not parsed:
        logger.warning("Cannot parse channel URL: %s", product.channel_post_url)
        return

    chat_id, message_id = parsed
    text = _post_text(product)

    try:
        if product.image:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                parse_mode=ParseMode.HTML,
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        logger.info("Channel post updated for product %s", product.id)
    except TelegramError as err:
        logger.warning(
            "Could not update channel post for %s (%s/%s): %s",
            product.id, chat_id, message_id, err,
        )


async def delete_product_post(bot: Bot, product: Product) -> None:
    """Delete the channel post linked to *product*.

    Does nothing if the product has no ``channel_post_url`` or the delete fails.
    """
    if not product.channel_post_url:
        return

    parsed = _parse_url(product.channel_post_url)
    if not parsed:
        return

    chat_id, message_id = parsed
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info("Channel post deleted for product %s", product.id)
    except TelegramError as err:
        logger.warning(
            "Could not delete channel post for %s (%s/%s): %s",
            product.id, chat_id, message_id, err,
        )
