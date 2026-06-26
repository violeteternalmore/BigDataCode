import io
import numpy as np
import pandas as pd
import yaml

from src.storage.oss_client import list_keys, download_bytes
from src.storage.ch_client import insert_df, query_df

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))

# 只读清洗需要的列（跳过 name，省去逐行解析数百万个字符串；name 由 _build_dim 按 sku_id 还原）
_USECOLS = ["product_id", "category_id", "price", "change_date", "sales"]
_DTYPES = {"product_id": "int64", "category_id": "int64", "price": "float64", "sales": "int64"}


def clean_df(df):
    """纯清洗逻辑(不连数据库)：去非正价 + 同SKU同日Jevons去重 + 列整理 + 收窄类型。
    输入原始CSV格式的DataFrame，输出可直接写入 fact_price_daily 的DataFrame。"""
    # ① 去脏：剔除非正价格（先过滤，log 才不会碰到非正数）
    df = df[df["price"] > 0].copy()
    df["change_date"] = pd.to_datetime(df["change_date"], format="ISO8601")
    # ② 同一 SKU 同一天多报价 → Jevons 几何平均，收敛成单一代表价；销量求和。
    #    几何平均 = exp(mean(ln p))，故对 ln(price) 取均值即可全程向量化，
    #    免去逐组调用 Python UDF（2000万+次调用是清洗耗时的大头）。
    df["_lnp"] = np.log(df["price"])
    agg = (df.groupby(["product_id", "category_id", "change_date"], sort=False)
             .agg(_lnp=("_lnp", "mean"), sales=("sales", "sum")).reset_index())
    agg["price"] = np.exp(agg["_lnp"])
    # ③ 整理成事实表 schema（前向填充：本项目为每日稠密数据，故无缺口）
    fact = agg.rename(columns={"product_id": "sku_id", "change_date": "date"})
    fact = fact[["date", "sku_id", "category_id", "price", "sales"]]
    fact["date"] = fact["date"].dt.date
    fact["sku_id"] = fact["sku_id"].astype("uint64")
    fact["category_id"] = fact["category_id"].astype("uint32")
    fact["sales"] = fact["sales"].astype("uint32")
    return fact


def clean_and_load():
    for key in list_keys(CFG["oss"]["bronze_prefix"]):
        # 直接读字节 + 限定列与 dtype，省掉 utf-8 解码往返与无关列解析
        df = pd.read_csv(io.BytesIO(download_bytes(key)), usecols=_USECOLS, dtype=_DTYPES)
        fact = clean_df(df)                 # 纯清洗逻辑，已抽出便于单元测试
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
