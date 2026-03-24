"""
Factory functions for product-related test DataFrames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_products(
    item_ids: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a released products DataFrame (post-rename)."""
    rng = np.random.RandomState(seed)
    items = item_ids or [f"ITEM-{chr(65 + i)}" for i in range(8)]
    return pd.DataFrame({
        "ItemNumber": items,
        "ProductName": [f"Product {it}" for it in items],
        "BookPrice": [round(rng.uniform(5, 100), 2) for _ in items],
        "ProductGroup": [f"GRP{rng.choice(['X', 'Y', 'Z'])}" for _ in items],
    })
