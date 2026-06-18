"""Cart repository backed by SQLite."""

from __future__ import annotations

from datetime import datetime, timezone

from store.data.products import get_product_by_id
from store.db.connection import db_connection
from store.models.cart import Cart, CartItem


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def add_item(user_id: int, product_id: str, qty: int = 1) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO cart_items (user_id, product_id, qty, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, product_id) DO UPDATE SET
                qty = qty + excluded.qty,
                updated_at = excluded.updated_at
            """,
            (user_id, product_id, qty, _now_iso()),
        )


def remove_item(user_id: int, product_id: str) -> None:
    with db_connection() as conn:
        conn.execute(
            "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )


def clear_cart(user_id: int) -> None:
    with db_connection() as conn:
        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))


def get_cart(user_id: int) -> Cart:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT product_id, qty FROM cart_items
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()

    items: list[CartItem] = []
    for row in rows:
        product = get_product_by_id(row["product_id"])
        if product:
            items.append(CartItem(product=product, qty=row["qty"]))
    return Cart(items=items)


def is_empty(user_id: int) -> bool:
    with db_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM cart_items WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
    return count == 0
