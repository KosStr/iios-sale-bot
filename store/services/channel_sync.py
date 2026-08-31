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
import os
import re
from html import escape

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from store.data.products import Product, is_on_sale
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


def _price_line(product: Product) -> str:
    """Format the price line for a channel post."""
    uah = product.price_uah
    usd = product.price if product.price else None
    if uah and usd:
        return f"{uah}  грн  ( {usd}$ )"
    if uah:
        return f"{uah}  грн"
    if usd:
        return f"{usd}$"
    return ""


def _post_text(product: Product) -> str:
    """HTML caption for a channel post, styled to match the IIOS channel format."""
    specs = "  ".join(
        escape(v) for v in (product.color, product.storage)
        if v and v not in ("—", "")
    )
    header = f"<b>{escape(product.name)}</b>"
    if specs:
        header += f"  {specs}"
    parts = [header]

    # Condition line (brand used as condition: "Вживаний", "Новий", etc.)
    if product.brand and product.brand not in ("—", ""):
        parts += ["", escape(product.brand)]

    # Description: each non-empty line becomes a ▪ bullet
    desc = (product.description or "").strip()
    if desc and desc != product.name:
        bullets = [
            f"▪ {escape(line.strip())}"
            for line in desc.splitlines()
            if line.strip()
        ]
        if bullets:
            parts += [""] + bullets

    # Warranty line
    parts += ["", "🛡 90 днів гарантії від IIOS"]

    # Price (sale price takes priority when active)
    if is_on_sale(product):
        regular = _price_line(product)
        sale_usd = product.sale_price
        sale_uah = product.price_uah  # UAH sale price not tracked separately
        if sale_uah and sale_usd:
            sale_line = f"<b>{sale_uah}  грн  ( {sale_usd}$ )</b>"
        elif sale_usd:
            sale_line = f"<b>{sale_usd}$</b>"
        else:
            sale_line = ""
        price_block = ["", "🔥 <b>АКЦІЯ</b>"]
        if regular:
            price_block.append(f"<s>{regular}</s>")
        if sale_line:
            price_block.append(sale_line)
        parts += price_block
    else:
        price = _price_line(product)
        if price:
            parts += ["", price]

    # Divider + payment block
    parts += [
        "",
        "———",
        "",
        "💳 Оплата:",
        "• $ / ₴ / €",
        "• Післяплата",
        "• Приват / Моно / A Bank",
        "",
        "♻ Trade-in / Обмін",
        "",
    ]

    # Contact info from env vars
    manager = os.getenv("STORE_TELEGRAM", "").strip()
    phone = os.getenv("STORE_PHONE", "").strip()
    if manager:
        parts.append(f"✉ Direct {escape(manager)}")
    if phone:
        parts.append(f"📞 {escape(phone)}")

    # Instagram
    instagram = os.getenv("STORE_INSTAGRAM", "").strip()
    if instagram:
        user = instagram.lstrip("@")
        parts += ["", "Інстаграм", f"https://instagram.com/{escape(user)}"]

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
