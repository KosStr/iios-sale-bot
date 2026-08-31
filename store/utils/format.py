"""Text and price formatting helpers, currency-aware.

`product_summary` renders HTML (so it can show a struck-through old price);
`cart_summary` renders legacy Markdown (used by the cart/checkout screens).
"""

from __future__ import annotations

from datetime import timedelta
from html import escape

from store.data.products import Product, is_on_sale, sale_time_left
from store.services.cart import Cart


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


def _fmt_price(product: Product) -> str:
    """Short price string using whichever price fields are set."""
    uah = product.price_uah
    usd = product.price if product.price else None
    if uah and usd:
        return f"{uah} грн (${usd})"
    if uah:
        return f"{uah} грн"
    if usd:
        return f"${usd}"
    return "—"


def _price_block(product: Product) -> list[str]:
    """HTML price lines. On sale: old price struck through, new price after it."""
    if is_on_sale(product):
        left = sale_time_left(product)
        until = product.sale_until.strftime("%d.%m %H:%M")
        old = escape(_fmt_price(product))
        sale_usd = product.sale_price
        sale_uah = product.price_uah
        if sale_uah and sale_usd:
            new = escape(f"{sale_uah} грн (${sale_usd})")
        elif sale_usd:
            new = escape(f"${sale_usd}")
        else:
            new = "—"
        return [
            "🔥 <b>АКЦІЯ</b>",
            f"💰 Ціна: <s>{old}</s> → <b>{new}</b>",
            f"⏳ Діє до {escape(until)} (залишилось {escape(format_timeleft(left))})",
        ]
    return [f"💰 Ціна: <b>{escape(_fmt_price(product))}</b>"]


def product_summary(product: Product, currency: str = "UAH") -> str:
    """HTML product card text."""
    stock = f"В наявності: {product.stock}" if product.stock > 0 else "Немає в наявності"
    return "\n".join(
        [
            f"<b>{escape(product.name)}</b>",
            f"{escape(product.brand)} • {escape(product.storage)} • {escape(product.color)}",
            "",
            escape(product.description),
            "",
            *_price_block(product),
            stock,
        ]
    )


def _item_total_str(item) -> str:
    p = item.product
    uah = (p.price_uah or 0) * item.qty
    usd = (p.price or 0) * item.qty
    parts = []
    if uah:
        parts.append(f"{uah} грн")
    if usd:
        parts.append(f"${usd}")
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
    total_uah = sum((i.product.price_uah or 0) * i.qty for i in cart.items)
    total_usd = sum((i.product.price or 0) * i.qty for i in cart.items)
    total_parts = []
    if total_uah:
        total_parts.append(f"{total_uah} грн")
    if total_usd:
        total_parts.append(f"${total_usd}")
    total_str = " / ".join(total_parts) if total_parts else "—"
    lines.extend(["", f"*Разом: {total_str}*"])
    return "\n".join(lines)
