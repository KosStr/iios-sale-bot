"""Shopping cart service backed by persistent SQLite storage."""

from __future__ import annotations

from store.db import cart_repo
from store.models.cart import Cart, CartItem

__all__ = ["Cart", "add_item", "remove_item", "clear_cart", "get_cart", "is_empty"]


def add_item(user_id: int, product_id: str, qty: int = 1) -> None:
    cart_repo.add_item(user_id, product_id, qty)


def remove_item(user_id: int, product_id: str) -> None:
    cart_repo.remove_item(user_id, product_id)


def clear_cart(user_id: int) -> None:
    cart_repo.clear_cart(user_id)


def get_cart(user_id: int) -> Cart:
    return cart_repo.get_cart(user_id)


def is_empty(user_id: int) -> bool:
    return cart_repo.is_empty(user_id)
