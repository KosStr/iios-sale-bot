"""Shared admin UI helpers for product management."""

from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from store.data.products import Product
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
    return "\n".join(
        [
            f"📦 <b>{escape(product.name)}</b>",
            "",
            f"ID: <code>{escape(product.id)}</code>",
            f"Ціна: <b>{escape(format_price(product.price, 'USD'))}</b>",
            f"На складі: <b>{product.stock}</b>",
            f"Категорія: {escape(cat)}",
            f"Підкатегорія: {escape(sub)}",
            f"Фото: <code>{escape(photo)}</code>",
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
    rows = [
        [
            InlineKeyboardButton(
                f"{p.name[:28]} — {format_price(p.price, 'USD')}",
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


def edit_menu_keyboard(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Назва", callback_data=f"adm:efld:{product_id}:name"),
                InlineKeyboardButton("Ціна", callback_data=f"adm:efld:{product_id}:price"),
            ],
            [
                InlineKeyboardButton("Склад", callback_data=f"adm:efld:{product_id}:stock"),
                InlineKeyboardButton("Категорія", callback_data=f"adm:ecat:{product_id}:menu"),
            ],
            [
                InlineKeyboardButton("Фото", callback_data=f"adm:efld:{product_id}:photo"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"adm:view:{product_id}")],
        ]
    )


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


