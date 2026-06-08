"""Group product variants under a single model.

Products that share the same non-empty ``group`` (e.g. "iPhone 13") are
treated as variants of one model. Standalone products form a group of one,
keyed by their own id.
"""

from __future__ import annotations

from dataclasses import dataclass

from store.data.products import Product, effective_price, is_on_sale


def group_key(product: Product) -> str:
    return product.group or product.id


def group_label(product: Product) -> str:
    return product.group or product.name


@dataclass
class Group:
    key: str
    label: str
    variants: list[Product]

    @property
    def is_single(self) -> bool:
        return len(self.variants) == 1

    @property
    def only(self) -> Product:
        return self.variants[0]

    @property
    def min_price(self) -> int:
        return min(effective_price(v) for v in self.variants)

    @property
    def on_sale(self) -> bool:
        return any(is_on_sale(v) for v in self.variants)


def build_groups(products: list[Product]) -> list[Group]:
    """Collapse a product list into ordered groups (insertion order kept)."""
    order: list[str] = []
    by_key: dict[str, Group] = {}
    for product in products:
        key = group_key(product)
        if key not in by_key:
            by_key[key] = Group(key=key, label=group_label(product), variants=[])
            order.append(key)
        by_key[key].variants.append(product)
    return [by_key[key] for key in order]


def find_group(key: str, products: list[Product]) -> Group | None:
    for group in build_groups(products):
        if group.key == key:
            return group
    return None
