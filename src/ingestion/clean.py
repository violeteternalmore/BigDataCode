import io
import pandas as pd
import yaml

from src.storage.oss_client import list_keys, download_text
from src.storage.ch_client import insert_df, query_df
from src.compute.index import jevons

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def clean_and_load():
    for key in list_keys(CFG["oss"]["bronze_prefix"]):
        df = pd.read_csv(io.StringIO(download_text(key)))
        df["change_date"] = pd.to_datetime(df["change_date"])
        # ① 去脏：剔除非正价格
        df = df[df["price"] > 0]
        # ② 同一 SKU 同一天多报价 → Jevons 几何平均，收敛成单一代表价；销量求和
        agg = (df.groupby(["product_id", "category_id", "change_date"])
                 .agg(price=("price", jevons), sales=("sales", "sum")).reset_index())
        # ③ 整理成事实表 schema（前向填充：本项目为每日稠密数据，故无缺口）
        fact = agg.rename(columns={"product_id": "sku_id", "change_date": "date"})
        fact = fact[["date", "sku_id", "category_id", "price", "sales"]]
        fact["date"] = fact["date"].dt.date
        fact["sku_id"] = fact["sku_id"].astype("uint64")
        fact["category_id"] = fact["category_id"].astype("uint32")
        fact["sales"] = fact["sales"].astype("uint32")
        insert_df("fact_price_daily", fact)
        print(f"{key} 清洗入库 {len(fact)} 行")

    # 维度表：商品名只存一份
    insert_df("dim_product", _build_dim())


def _build_dim():
    skus = query_df("SELECT DISTINCT sku_id, category_id FROM fact_price_daily")
    skus["name"] = "商品_" + (skus["sku_id"] - 290000000000).astype(str)
    skus["category_name"] = "类目" + skus["category_id"].astype(str)
    return skus[["sku_id", "name", "category_id", "category_name"]]


if __name__ == "__main__":
    clean_and_load()
