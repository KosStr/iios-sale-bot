"""Product repository backed by SQLite."""

from __future__ import annotations

from datetime import datetime

from store.data.products import Product
from store.db.connection import db_connection

_SELECT = """
SELECT id, brand, name, price, storage, color, stock, description,
       category, subcategory, image, product_group, sale_price, sale_until
FROM products
"""


def _row_to_product(row) -> Product:
    sale_until = None
    if row["sale_until"]:
        sale_until = datetime.fromisoformat(row["sale_until"])
    return Product(
        id=row["id"],
        brand=row["brand"],
        name=row["name"],
        price=row["price"],
        storage=row["storage"],
        color=row["color"],
        stock=row["stock"],
        description=row["description"],
        category=row["category"],
        subcategory=row["subcategory"] or "",
        image=row["image"] or "",
        group=row["product_group"] or "",
        sale_price=row["sale_price"],
        sale_until=sale_until,
    )


def fetch_all() -> list[Product]:
    with db_connection() as conn:
        rows = conn.execute(f"{_SELECT} ORDER BY name, storage, color").fetchall()
    return [_row_to_product(row) for row in rows]


def fetch_by_id(product_id: str) -> Product | None:
    with db_connection() as conn:
        row = conn.execute(f"{_SELECT} WHERE id = ?", (product_id,)).fetchone()
    return _row_to_product(row) if row else None
