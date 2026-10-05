"""Text and price formatting helpers, currency-aware.

`product_summary` renders HTML (so it can show a struck-through old price);
`cart_summary` renders legacy Markdown (used by the cart/checkout screens).
"""

from __future__ import annotations

import os
from datetime import timedelta
from html import escape

from store.data.products import (
    Product,
    effective_price,
    effective_price_uah,
    is_on_sale,
    sale_time_left,
)
from store.services.cart import Cart

_BLANK_SPECS = frozenset({"", "—", "-"})


def present_values(*parts: str | None) -> list[str]:
    """Keep only real spec values; skip empty placeholders like '—'."""
    values: list[str] = []
    for part in parts:
        if not part:
            continue
        text = part.strip()
        if text and text not in _BLANK_SPECS:
            values.append(text)
    return values


def join_specs(*parts: str | None, sep: str = " • ") -> str:
    """Join brand/storage/color, omitting blanks so leftover separators never show."""
    return sep.join(present_values(*parts))


def format_timeleft(delta: timedelta) -> str:
    """Short Ukrainian 'time left' label, e.g. '1 дн. 5 год.' or '40 хв.'."""
    total = int(delta.total_seconds())
    if total <= 0:
        return "завершується"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days >= 1:
        return f"{days} дн. {hours} год." if hours else f"{days} дн."
    if hours >= 1:
        return f"{hours} год. {minutes} хв." if minutes else f"{hours} год."
    return f"{minutes} хв."


def _price_parts(uah: int | None, usd: int | None) -> list[str]:
    """Rendered non-zero price components, e.g. ['1000 грн', '$25'].

    Zero/None values are skipped so a product priced in only one currency
    never shows an empty or dangling amount.
    """
    parts: list[str] = []
    if uah:
        parts.append(f"{uah} грн")
    if usd:
        parts.append(f"${usd}")
    return parts


def _fmt_amounts(uah: int | None, usd: int | None) -> str:
    """Both currencies render as "<uah> грн ($<usd>)"; a single one renders alone."""
    parts = _price_parts(uah, usd)
    if len(parts) == 2:
        return f"{parts[0]} ({parts[1]})"
    return parts[0] if parts else "—"


def _fmt_price(product: Product) -> str:
    """Short regular-price string using whichever price fields are set."""
    return _fmt_amounts(product.price_uah, product.price)


def _price_block(product: Product) -> list[str]:
    """HTML price lines. On sale: old price struck through, new price after it."""
    if is_on_sale(product):
        old = escape(_fmt_price(product))
        new = escape(_fmt_amounts(effective_price_uah(product), effective_price(product)))
        lines = [
            "🔥 <b>АКЦІЯ</b>",
            f"💰 Ціна: <s>{old}</s> → <b>{new}</b>",
        ]
        left = sale_time_left(product)
        if left is not None:
            until = product.sale_until.strftime("%d.%m %H:%M")
            lines.append(
                f"⏳ Діє до {escape(until)} (залишилось {escape(format_timeleft(left))})"
            )
        return lines
    return [f"💰 Ціна: <b>{escape(_fmt_price(product))}</b>"]


def _instagram_links() -> list[str]:
    """HTML links for the store's Instagram accounts (from env), if any."""
    handles = [
        os.getenv("STORE_INSTAGRAM", "@iios_cv").strip(),
        os.getenv("STORE_INSTAGRAM2", "@iios_tehnika").strip(),
    ]
    links: list[str] = []
    for handle in handles:
        if not handle:
            continue
        user = handle.lstrip("@")
        links.append(
            f'<a href="https://instagram.com/{escape(user)}">@{escape(user)}</a>'
        )
    return links


def product_summary(product: Product, currency: str = "UAH") -> str:
    """HTML product card text."""
    stock = f"В наявності: {product.stock}" if product.stock > 0 else "Немає в наявності"
    lines = [f"<b>{escape(product.name)}</b>"]
    specs = join_specs(product.brand, product.storage, product.color)
    if specs:
        lines.append(escape(specs))
    lines.extend(
        [
            "",
            stock,
            *_price_block(product),
            "",
            escape(product.description),
        ]
    )
    insta = _instagram_links()
    if insta:
        lines += ["", "📸 Instagram: " + " · ".join(insta)]
    return "\n".join(lines)


def _item_total_str(item) -> str:
    """Line total for a cart item, e.g. '2000 грн / $50'."""
    p = item.product
    parts = _price_parts(
        (effective_price_uah(p) or 0) * item.qty, (effective_price(p) or 0) * item.qty
    )
    return " / ".join(parts) if parts else "—"


def cart_summary(cart: Cart, currency: str = "UAH") -> str:
    if cart.is_empty:
        return "Ваш кошик порожній."
    lines = []
    for item in cart.items:
        mark = " 🔥" if is_on_sale(item.product) else ""
        lines.append(
            f"• {item.product.name} ×{item.qty} — {_item_total_str(item)}{mark}"
        )
    total_uah = sum((effective_price_uah(i.product) or 0) * i.qty for i in cart.items)
    total_usd = sum((effective_price(i.product) or 0) * i.qty for i in cart.items)
    total_parts = _price_parts(total_uah, total_usd)
    total_str = " / ".join(total_parts) if total_parts else "—"
    lines.extend(["", f"*Разом: {total_str}*"])
    return "\n".join(lines)
