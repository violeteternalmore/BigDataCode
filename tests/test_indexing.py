"""单元测试·年度费雪同比对齐 与 数据生成健壮性（不连外部系统）。"""
import numpy as np
import pandas as pd
from src.compute.run_index import _annual_fisher
from src.ingestion.generator import _inject_dirty


def _panel(rows):
    return pd.DataFrame(rows, columns=["date", "sku_id", "price", "sales"])

def test_annual_fisher_aligns_to_last_year():
    # 同一商品：去年价10、今年价12 → 同比≈+20%
    df = _panel([
        ("2026-05-01", 1, 10, 5),
        ("2027-05-01", 1, 12, 5),
    ])
    out = _annual_fisher(df)
    row = out[out["date"] == "2027-05-01"].iloc[0]
    assert abs(row["yoy_pct"] - 20) < 1e-6

def test_annual_fisher_no_prior_year_is_empty():
    # 只有一年数据 → 无去年同期可对照 → 结果为空
    df = _panel([("2026-05-01", 1, 10, 5)])
    assert len(_annual_fisher(df)) == 0

def _raw(rows):
    return pd.DataFrame(rows, columns=["product_id", "category_id", "name",
                                       "price", "change_date", "sales"])

def test_inject_dirty_adds_bad_prices():
    rng = np.random.default_rng(0)
    df = _raw([(i, 100, "a", 5.0, "2025-05-01", 10) for i in range(200)])
    out = _inject_dirty(df, rng)
    assert (out["price"] <= 0).any()    # 确实注入了0/负价
    assert len(out) >= len(df)          # 还复制了重复行
