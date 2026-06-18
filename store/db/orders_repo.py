"""Order and booking persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from store.db.connection import db_connection
from store.services.cart import Cart


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def save_order(
    order_id: str,
    user_id: int,
    customer_name: str,
    phone: str,
    address: str,
    cart: Cart,
    currency: str,
) -> None:
    from store.data.products import effective_price

    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                id, user_id, customer_name, phone, address,
                total_usd, currency, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                user_id,
                customer_name,
                phone,
                address,
                cart.total,
                currency,
                _now_iso(),
            ),
        )
        conn.executemany(
            """
            INSERT INTO order_items (order_id, product_id, qty, unit_price_usd)
            VALUES (?, ?, ?, ?)
            """,
            [
                (order_id, item.product.id, item.qty, effective_price(item.product))
                for item in cart.items
            ],
        )


def save_booking(
    booking_id: str,
    user_id: int,
    product_id: str,
    customer_name: str,
    phone: str,
) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO bookings (
                id, user_id, product_id, customer_name, phone, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (booking_id, user_id, product_id, customer_name, phone, _now_iso()),
        )
