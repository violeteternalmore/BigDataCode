import io
import numpy as np
import pandas as pd
import yaml

from src.storage.oss_client import upload_bytes

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def _init_products(rng):
    """初始化每个商品的起始价、漂移率、基础销量、所属类目。"""
    cats = CFG["data"]["categories"]
    prods = []
    for i in range(CFG["data"]["n_products"]):
        cat = cats[i % len(cats)]
        prods.append({
            "product_id": 290000000000 + i,            # 12位ID
            "category_id": cat,
            "name": f"商品_{i}",
            "price": float(rng.uniform(5, 200)),        # 起始价
            "drift": rng.normal(0.0002, 0.0003),         # 每日缓慢趋势
            "base_sales": int(rng.uniform(50, 500)),     # 基础销量
        })
    return prods


def _month_range():
    return pd.period_range(CFG["data"]["start"], CFG["data"]["end"], freq="M")


def _inject_dirty(df, rng, rate=0.01):
    """注入 0价/负价/重复行，用于检验清洗。"""
    idx = rng.choice(df.index, size=max(1, int(len(df) * rate)), replace=False)
    df.loc[idx[:len(idx) // 2], "price"] = 0
    df.loc[idx[len(idx) // 2:], "price"] = -1
    dup = df.sample(frac=rate / 2, random_state=int(rng.integers(1e9)))
    return pd.concat([df, dup], ignore_index=True)


def generate_and_upload():
    rng = np.random.default_rng(CFG["data"]["seed"])
    prods = _init_products(rng)
    # 设一个"暴涨事件"：第3个类目从 2026-09 起每天 +0.8%
    shock = {"cat": CFG["data"]["categories"][2],
             "start": pd.Timestamp("2026-09-01"), "rate": 0.008}

    for per in _month_range():
        days = pd.date_range(per.start_time, per.end_time, freq="D")
        rows = []
        for p in prods:
            price = p["price"]
            for d in days:
                price *= (1 + rng.normal(p["drift"], 0.01))            # 随机游走 + 趋势
                if p["category_id"] == shock["cat"] and d >= shock["start"]:
                    price *= (1 + shock["rate"])                       # 注入冲击
                sales = max(0, int(rng.normal(p["base_sales"], p["base_sales"] * 0.2)))
                rows.append((p["product_id"], p["category_id"], p["name"],
                             round(price, 4), d.date(), sales))
            p["price"] = price                                        # 保存月末价，下月接续
        # 列序与你提供的原始 CSV 一致：product_id,category_id,name,price,change_date,sales
        df = pd.DataFrame(rows, columns=["product_id", "category_id", "name",
                                         "price", "change_date", "sales"])
        df = _inject_dirty(df, rng)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        upload_bytes(f"{CFG['oss']['bronze_prefix']}{per}.csv", buf.getvalue().encode("utf-8"))
        print(f"已上传 {per}.csv ，{len(df)} 行")   # 本月数据上传后即丢弃，磁盘占用极小


if __name__ == "__main__":
    generate_and_upload()
