"""Cart domain models."""

from __future__ import annotations

from dataclasses import dataclass

from store.data.products import Product, effective_price


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
