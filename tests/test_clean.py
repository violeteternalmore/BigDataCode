"""单元测试·清洗与去重正确性（不连数据库，测纯函数 clean_df）。"""
import pandas as pd
from src.ingestion.clean import clean_df


def _raw(rows):
    return pd.DataFrame(rows, columns=["product_id", "category_id", "name",
                                       "price", "change_date", "sales"])

def test_clean_drops_nonpositive_price():
    df = _raw([
        (1, 100, "a", 0,  "2025-05-01", 10),   # 0价，应删
        (1, 100, "a", -5, "2025-05-01", 10),   # 负价，应删
        (1, 100, "a", 4,  "2025-05-01", 10),   # 正常
    ])
    out = clean_df(df)
    assert len(out) == 1 and out.iloc[0]["price"] == 4

def test_clean_dedup_same_sku_day_by_jevons():
    df = _raw([
        (1, 100, "a", 2, "2025-05-01", 10),    # 同SKU同日两报价
        (1, 100, "a", 8, "2025-05-01", 20),
    ])
    out = clean_df(df)
    assert len(out) == 1                         # 收成一行
    assert abs(out.iloc[0]["price"] - 4.0) < 1e-9   # √(2×8)=4
    assert out.iloc[0]["sales"] == 30            # 销量求和
