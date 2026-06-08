"""Text and price formatting helpers (Markdown), currency-aware."""

from __future__ import annotations

from datetime import timedelta

from store.data.products import Product, is_on_sale, sale_time_left
from store.services.cart import Cart
from store.services.catalog_filter import format_price


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


def _price_block(product: Product, currency: str) -> list[str]:
    if is_on_sale(product):
        left = sale_time_left(product)
        until = product.sale_until.strftime("%d.%m %H:%M")
        return [
            "🔥 *АКЦІЯ*",
            f"Стара ціна: {format_price(product.price, currency)}",
            f"Ціна за акцією: *{format_price(product.sale_price, currency)}*",
            f"⏳ Діє до {until} (залишилось {format_timeleft(left)})",
        ]
    return [f"Ціна: *{format_price(product.price, currency)}*"]


def product_summary(product: Product, currency: str = "UAH") -> str:
    stock = f"В наявності: {product.stock}" if product.stock > 0 else "Немає в наявності"
    return "\n".join(
        [
            f"*{product.name}*",
            f"{product.brand} • {product.storage} • {product.color}",
            "",
            product.description,
            "",
            *_price_block(product, currency),
            stock,
        ]
    )


def cart_summary(cart: Cart, currency: str = "UAH") -> str:
    if cart.is_empty:
        return "Ваш кошик порожній."
    lines = []
    for item in cart.items:
        mark = " 🔥" if is_on_sale(item.product) else ""
        lines.append(
            f"• {item.product.name} ×{item.qty} — {format_price(item.line_total, currency)}{mark}"
        )
    lines.extend(["", f"*Разом: {format_price(cart.total, currency)}*"])
    return "\n".join(lines)
