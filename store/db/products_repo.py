"""Product repository backed by SQLite."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from store.data.products import Product
from store.db.connection import db_connection

_SELECT = """
SELECT id, brand, name, price, storage, color, stock, description,
       category, subcategory, image, product_group, sale_price, sale_until
FROM products
"""

_INSERT = """
INSERT INTO products (
    id, brand, name, price, storage, color, stock, description,
    category, subcategory, image, product_group, sale_price, sale_until
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:48] or "product"


def make_unique_id(name: str) -> str:
    base = _slugify(name)
    candidate = base
    suffix = 2
    while exists(candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def exists(product_id: str) -> bool:
    with db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    return row is not None


def insert(product: Product) -> None:
    sale_until = (
        product.sale_until.isoformat(timespec="seconds")
        if product.sale_until
        else None
    )
    with db_connection() as conn:
        conn.execute(
            _INSERT,
            (
                product.id,
                product.brand,
                product.name,
                product.price,
                product.storage,
                product.color,
                product.stock,
                product.description,
                product.category,
                product.subcategory,
                product.image,
                product.group,
                product.sale_price,
                sale_until,
            ),
        )


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


def update(product_id: str, **fields: object) -> None:
    allowed = {
        "name",
        "price",
        "stock",
        "category",
        "subcategory",
        "image",
        "description",
        "brand",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return

    columns = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [product_id]
    with db_connection() as conn:
        conn.execute(f"UPDATE products SET {columns} WHERE id = ?", values)


def delete(product_id: str) -> None:
    with db_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
