"""Simple in-memory cart store keyed by Telegram user id.

NOTE: data is lost when the process restarts. For production, back this
with a persistent store (Redis, a database, etc.) keeping the same API.
"""

from __future__ import annotations

from dataclasses import dataclass

from store.data.products import Product, effective_price, get_product_by_id

# user_id -> {product_id: quantity}
_carts: dict[int, dict[str, int]] = {}


@dataclass(frozen=True)
class CartItem:
    product: Product
    qty: int

    @property
    def line_total(self) -> int:
        return effective_price(self.product) * self.qty


@dataclass(frozen=True)
class Cart:
    items: list[CartItem]

    @property
    def total(self) -> int:
        return sum(item.line_total for item in self.items)

    @property
    def count(self) -> int:
        return sum(item.qty for item in self.items)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0


def add_item(user_id: int, product_id: str, qty: int = 1) -> None:
    cart = _carts.setdefault(user_id, {})
    cart[product_id] = cart.get(product_id, 0) + qty


def remove_item(user_id: int, product_id: str) -> None:
    cart = _carts.get(user_id)
    if cart:
        cart.pop(product_id, None)


def clear_cart(user_id: int) -> None:
    _carts.pop(user_id, None)


def get_cart(user_id: int) -> Cart:
    raw = _carts.get(user_id, {})
    items: list[CartItem] = []
    for product_id, qty in raw.items():
        product = get_product_by_id(product_id)
        if product:
            items.append(CartItem(product=product, qty=qty))
    return Cart(items=items)


def is_empty(user_id: int) -> bool:
    return get_cart(user_id).is_empty
