"""Shared admin UI helpers for product management."""

from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from store.data.products import Product, is_on_sale
from store.services.catalog_filter import (
    CATEGORIES,
    CATEGORY_LABELS,
    format_price,
    subcategory_options,
)

PAGE_SIZE = 8


def product_detail_text(product: Product) -> str:
    cat = CATEGORY_LABELS.get(product.category, product.category)
    sub = product.subcategory or "—"
    photo = product.image or "—"
    hot = "так" if product.is_hot else "ні"
    sale = "—"
    if is_on_sale(product):
        parts = []
        if product.sale_price_uah:
            parts.append(f"{product.sale_price_uah} грн")
        if product.sale_price:
            parts.append(f"${product.sale_price}")
        sale = " / ".join(parts) or "—"
    return "\n".join(
        [
            f"📦 <b>{escape(product.name)}</b>",
            "",
            f"ID: <code>{escape(product.id)}</code>",
            f"Модель: {escape(product.group or '—')}",
            f"Ціна: <b>{escape(format_price(product.price, 'USD'))}</b>",
            f"Ціна, грн: <b>{product.price_uah or '—'}</b>",
            f"На складі: <b>{product.stock}</b>",
            f"Категорія: {escape(cat)}",
            f"Підкатегорія: {escape(sub)}",
            f"Фото: <code>{escape(photo)}</code>",
            f"🔥 Гаряча пропозиція: <b>{hot}</b>",
            f"Акційна ціна: <b>{escape(sale)}</b>",
        ]
    )


def product_detail_keyboard(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Редагувати", callback_data=f"adm:edit:{product_id}"),
                InlineKeyboardButton("🗑 Видалити", callback_data=f"adm:del:{product_id}"),
            ],
            [InlineKeyboardButton("⬅️ До списку", callback_data="adm:page:0")],
        ]
    )


def product_list_keyboard(products: list[Product], page: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    chunk = products[start : start + PAGE_SIZE]
    # Show the id next to the (truncated) name so admins can identify a
    # product at a glance without opening its detail screen.
    rows = [
        [
            InlineKeyboardButton(
                f"{'🔥 ' if p.is_hot else ''}{p.name[:22]} · {p.id} — {format_price(p.price, 'USD')}",
                callback_data=f"adm:view:{p.id}",
            )
        ]
        for p in chunk
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"adm:page:{page - 1}"))
    if start + PAGE_SIZE < len(products):
        nav.append(InlineKeyboardButton("Далі ▶️", callback_data=f"adm:page:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🔄 Оновити", callback_data="adm:page:0")])
    return InlineKeyboardMarkup(rows)


def edit_menu_keyboard(product_id: str, is_hot: bool = False) -> InlineKeyboardMarkup:
    hot_label = "🔥 Прибрати з гарячих" if is_hot else "🔥 Зробити гарячою"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Назва", callback_data=f"adm:efld:{product_id}:name"),
                InlineKeyboardButton("Ціна $", callback_data=f"adm:efld:{product_id}:price"),
                InlineKeyboardButton("Ціна грн", callback_data=f"adm:efld:{product_id}:uah"),
            ],
            [
                InlineKeyboardButton("Склад", callback_data=f"adm:efld:{product_id}:stock"),
                InlineKeyboardButton("Категорія", callback_data=f"adm:ecat:{product_id}:menu"),
            ],
            [
                InlineKeyboardButton("Модель", callback_data=f"adm:efld:{product_id}:group"),
                InlineKeyboardButton("Фото", callback_data=f"adm:efld:{product_id}:photo"),
            ],
            [
                InlineKeyboardButton(hot_label, callback_data=f"adm:hot:{product_id}"),
                InlineKeyboardButton("Акційна ціна", callback_data=f"adm:efld:{product_id}:sale"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"adm:view:{product_id}")],
        ]
    )


def hot_list_text(products: list[Product]) -> str:
    if not products:
        return (
            "🔥 <b>Гарячі пропозиції</b>\n\nПоки порожньо. Відкрийте товар у /products → "
            "✏️ Редагувати → 🔥 Зробити гарячою."
        )
    lines = [f"🔥 <b>Гарячі пропозиції</b> ({len(products)})", ""]
    for p in products:
        note = "" if p.stock > 0 else " — <i>немає в наявності, на сайті не показується</i>"
        lines.append(f"• {escape(p.name)} <code>{escape(p.id)}</code>{note}")
    return "\n".join(lines)


def hot_list_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(p.name[:40], callback_data=f"adm:view:{p.id}")]
        for p in products
    ]
    rows.append([InlineKeyboardButton("🔄 Оновити лендінг", callback_data="adm:hotpub")])
    return InlineKeyboardMarkup(rows)


def edit_category_keyboard(product_id: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"adm:ecat:{product_id}:{key}")
        for key, label in CATEGORIES if key != "all"
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm:edit:{product_id}")])
    return InlineKeyboardMarkup(rows)


def edit_subcategory_keyboard(product_id: str, category: str) -> InlineKeyboardMarkup:
    options = [
        (key, label)
        for key, label in subcategory_options(category)
        if key != "all"
    ]
    rows = [
        [InlineKeyboardButton(label, callback_data=f"adm:esub:{product_id}:{key}")]
        for key, label in options
    ]
    rows.append(
        [
            InlineKeyboardButton(
                "Без підкатегорії", callback_data=f"adm:esub:{product_id}:"
            )
        ]
    )
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm:edit:{product_id}")])
    return InlineKeyboardMarkup(rows)


def delete_confirm_keyboard(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Так, видалити", callback_data=f"adm:delok:{product_id}"
                ),
                InlineKeyboardButton("✖️ Ні", callback_data=f"adm:view:{product_id}"),
            ]
        ]
    )


def force_delete_keyboard(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🗑 Все одно видалити", callback_data=f"adm:delforce:{product_id}"
                ),
            ],
            [InlineKeyboardButton("✖️ Скасувати", callback_data=f"adm:view:{product_id}")],
        ]
    )


