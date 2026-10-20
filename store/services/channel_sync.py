"""Automatic Telegram-channel post management for products.

Set ``CHANNEL_ID`` in the environment (e.g. ``@mychannel`` or ``-1001234567890``)
and make the bot a channel admin with *Post*, *Edit*, and *Delete messages*
permissions.  The bot then:

* Creates a channel post when a product is added via /add (except
  accessories, which are never posted to the channel).
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
from dataclasses import replace
from html import escape

from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from store.data.products import (
    CATEGORY_ACCESSORIES,
    Product,
    effective_price,
    effective_price_uah,
    is_on_sale,
)
from store.db import products_repo
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
    if specs:
        header = f"<b>{escape(product.name)}  {specs}</b>"
    else:
        header = f"<b>{escape(product.name)}</b>"
    parts = [header]

    # Price first — right under the header. Sale price takes priority.
    if is_on_sale(product):
        regular = _price_line(product)
        sale_usd = effective_price(product) or None
        sale_uah = effective_price_uah(product)
        if sale_uah and sale_usd:
            sale_line = f"<b>{sale_uah}  грн  ( {sale_usd}$ )</b>"
        elif sale_uah:
            sale_line = f"<b>{sale_uah}  грн</b>"
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

    # Condition (brand) + stock, one line below the price, joined by a separator
    stock_label = "В наявності" if product.stock and product.stock > 0 else "Немає в наявності"
    condition_bits = []
    if product.brand and product.brand not in ("—", ""):
        condition_bits.append(escape(product.brand))
    condition_bits.append(stock_label)
    parts.append(" | ".join(condition_bits))

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
    if product.warranty_days:
        parts += ["", f"🛡 {product.warranty_days} днів гарантії від IIOS"]

    # Divider + payment block
    parts += [
        "",
        "———",
        "",
        "💳 Оплата:",
        "• $ / ₴ / €",
        "• Післяплата",
        "• Розтермінування",
        "• Приват / Моно / A Bank / ПУМБ",
        "",
        "♻ Trade-in / Обмін",
        "",
    ]

    # Contact info from env vars
    manager = os.getenv("STORE_MANAGER", "@iios_manager").strip()
    phone = os.getenv("STORE_PHONE", "").strip()
    if manager:
        parts.append(f"✉ Direct {escape(manager)}")
    if phone:
        parts.append(f"📞 {escape(phone)}")

    # Instagram (both store accounts, if configured)
    insta_handles = [
        os.getenv("STORE_INSTAGRAM", "@iios_cv").strip(),
        os.getenv("STORE_INSTAGRAM2", "@iios_tehnika").strip(),
    ]
    insta_links = [
        f"https://instagram.com/{escape(handle.lstrip('@'))}"
        for handle in insta_handles
        if handle
    ]
    if insta_links:
        parts += ["", "Інстаграм"] + insta_links

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


async def _send_post(bot: Bot, channel_id: str, product: Product):
    """Send a channel post for *product*; return the Message or None on failure."""
    text = _post_text(product)
    photo = _best_photo(product)
    try:
        if photo:
            try:
                return await bot.send_photo(
                    chat_id=channel_id,
                    photo=photo,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
            except BadRequest as err:
                # Captions are capped at 1024 chars; a long description would
                # otherwise mean no post at all. Fall back to a text post.
                if "caption is too long" not in str(err).lower():
                    raise
                logger.warning(
                    "Caption too long for %s, posting as text instead", product.id
                )
        return await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as err:
        logger.warning("Could not create channel post for %s: %s", product.id, err)
        return None


async def post_product(bot: Bot, channel_id: str, product: Product) -> str:
    """Send a new channel post for *product*.

    Returns the ``https://t.me/...`` URL of the new message, or ``""`` on
    failure, when *channel_id* is empty, or when *product* is an accessory.
    """
    if not channel_id:
        return ""
    if product.category == CATEGORY_ACCESSORIES:
        logger.info("Skipping channel post for accessory %s", product.id)
        return ""

    msg = await _send_post(bot, channel_id, product)
    if msg is None:
        return ""
    url = _make_post_url(channel_id, msg.message_id)
    logger.info("Channel post created for product %s: %s", product.id, url)
    return url


def _is_not_modified(err: TelegramError) -> bool:
    return "message is not modified" in str(err).lower()


async def _edit_text_or_caption(
    bot: Bot, chat_id: str, message_id: int, product: Product
) -> None:
    """Edit the post's caption (photo post) or text (text post).

    The post kind isn't stored, so guess from ``product.image`` and switch to
    the other call when Telegram says the message has no caption / no text
    (e.g. the photo couldn't be fetched when the post was created).
    """
    text = _post_text(product)

    async def edit_caption() -> None:
        await bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id,
            caption=text, parse_mode=ParseMode.HTML,
        )

    async def edit_text() -> None:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, parse_mode=ParseMode.HTML,
        )

    first, second = (edit_caption, edit_text) if product.image else (edit_text, edit_caption)
    try:
        await first()
    except BadRequest as err:
        if _is_not_modified(err):
            return
        if "there is no" not in str(err).lower():
            raise
        try:
            await second()
        except BadRequest as err2:
            if not _is_not_modified(err2):
                raise


async def _replace_post(bot: Bot, product: Product) -> None:
    """Re-create the post (new photo on a text post) and store the new URL."""
    parsed = _parse_url(product.channel_post_url)
    if not parsed:
        return
    chat_id, _ = parsed
    msg = await _send_post(bot, chat_id, product)
    if msg is None:
        return
    await delete_product_post(bot, product)
    url = _make_post_url(chat_id, msg.message_id)
    products_repo.update(product.id, channel_post_url=url)
    logger.info("Channel post re-created for product %s: %s", product.id, url)


async def sync_product_post(
    bot: Bot,
    product: Product,
    *,
    photo_changed: bool = False,
    channel_id: str = "",
) -> None:
    """Bring the channel post for *product* in line with its current state.

    * Accessory with a post → the post is deleted (accessories aren't posted).
    * No post yet and *channel_id* given → a post is created (used when a
      product moves out of the accessories category).
    * *photo_changed* → the post's photo is replaced; a text-only post is
      re-posted with the photo, since Telegram can't add media to a text message.
    * Otherwise the caption/text is edited.

    Failures are logged, never raised.
    """
    if product.category == CATEGORY_ACCESSORIES:
        if product.channel_post_url:
            await delete_product_post(bot, product)
            products_repo.update(product.id, channel_post_url="")
        return

    if not product.channel_post_url:
        if channel_id:
            url = await post_product(bot, channel_id, product)
            if url:
                products_repo.update(product.id, channel_post_url=url)
        return

    parsed = _parse_url(product.channel_post_url)
    if not parsed:
        logger.warning("Cannot parse channel URL: %s", product.channel_post_url)
        return
    chat_id, message_id = parsed

    try:
        if photo_changed:
            photo = _best_photo(product)
            if photo:
                try:
                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media=InputMediaPhoto(
                            media=photo,
                            caption=_post_text(product),
                            parse_mode=ParseMode.HTML,
                        ),
                    )
                    logger.info("Channel post photo updated for product %s", product.id)
                    return
                except BadRequest as err:
                    if _is_not_modified(err):
                        return
                    # Text post (or over-long caption): post it anew instead.
                    logger.info(
                        "Can't swap photo on post for %s (%s); re-posting", product.id, err
                    )
                    await _replace_post(bot, product)
                    return
        await _edit_text_or_caption(bot, chat_id, message_id, product)
        logger.info("Channel post updated for product %s", product.id)
    except TelegramError as err:
        logger.warning(
            "Could not update channel post for %s (%s/%s): %s",
            product.id, chat_id, message_id, err,
        )


async def delete_product_post(bot: Bot, product: Product) -> bool:
    """Delete the channel post linked to *product*.

    Returns True when the post is gone (or there was none). When Telegram
    refuses the delete (e.g. the bot lacks the *Delete messages* right), the
    post is edited to say the item is no longer available so the channel
    doesn't keep advertising it, and False is returned.
    """
    if not product.channel_post_url:
        return True

    parsed = _parse_url(product.channel_post_url)
    if not parsed:
        logger.warning("Cannot parse channel URL: %s", product.channel_post_url)
        return False

    chat_id, message_id = parsed
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info("Channel post deleted for product %s", product.id)
        return True
    except BadRequest as err:
        if "message to delete not found" in str(err).lower():
            # Already removed by hand in the channel.
            return True
        logger.warning(
            "Could not delete channel post for %s (%s/%s): %s",
            product.id, chat_id, message_id, err,
        )
    except TelegramError as err:
        logger.warning(
            "Could not delete channel post for %s (%s/%s): %s",
            product.id, chat_id, message_id, err,
        )

    # Fallback: mark the post as unavailable.
    gone = replace(product, stock=0, sale_price=None, sale_price_uah=None, sale_until=None)
    try:
        await _edit_text_or_caption(bot, chat_id, message_id, gone)
    except TelegramError as err:
        logger.warning("Could not mark channel post for %s as removed: %s", product.id, err)
    return False
