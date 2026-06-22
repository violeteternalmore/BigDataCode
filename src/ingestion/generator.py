import io
import numpy as np
import pandas as pd
import yaml
from src.storage.oss_client import upload_bytes
CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))

def _init_products(rng):
    cats = CFG["data"]["categories"]
    prods = []
    for i in range(CFG["data"]["n_products"]):
        cat = cats[i % len(cats)]
        prods.append({
            "product_id": 290000000000 + i,
            "category_id": cat,
            "name": f"商品_{i}",
            "price": float(rng.uniform(5, 200)),
            "drift": rng.normal(0.0, 0.00006),    # 改：均值0、极小，价格围绕基线游走而非单向暴涨
            "base_sales": int(rng.uniform(50, 500)),
        })
    return prods

def _month_range():
    return pd.period_range(CFG["data"]["start"], CFG["data"]["end"], freq="M")

def _inject_dirty(df, rng, rate=0.01):
    idx = rng.choice(df.index, size=max(1, int(len(df) * rate)), replace=False)
    df.loc[idx[:len(idx)//2], "price"] = 0
    df.loc[idx[len(idx)//2:], "price"] = -1
    dup = df.sample(frac=rate/2, random_state=int(rng.integers(1e9)))
    return pd.concat([df, dup], ignore_index=True)

def generate_and_upload():
    rng = np.random.default_rng(CFG["data"]["seed"])
    prods = _init_products(rng)
    # 改：温和且“有起止”的冲击——只在窗口内 +0.15%/天，累计约+30%，窗口结束即停
    shock = {"cat": CFG["data"]["categories"][2],
             "start": pd.Timestamp("2026-09-01"),
             "end":   pd.Timestamp("2027-03-01"),
             "rate": 0.0015}
    for per in _month_range():
        days = pd.date_range(per.start_time, per.end_time, freq="D")
        rows = []
        for p in prods:
            price = p["price"]
            for d in days:
                price *= (1 + rng.normal(p["drift"], 0.003))   # 改：日波动 0.01→0.003
                if p["category_id"] == shock["cat"] and shock["start"] <= d < shock["end"]:
                    price *= (1 + shock["rate"])               # 改：只在窗口内施加
                sales = max(0, int(rng.normal(p["base_sales"], p["base_sales"]*0.2)))
                rows.append((p["product_id"], p["category_id"], p["name"],
                             round(price, 4), d.date(), sales))
            p["price"] = price
        df = pd.DataFrame(rows, columns=["product_id","category_id","name","price","change_date","sales"])
        df = _inject_dirty(df, rng)
        buf = io.StringIO(); df.to_csv(buf, index=False)
        upload_bytes(f"{CFG['oss']['bronze_prefix']}{per}.csv", buf.getvalue().encode("utf-8"))
        print(f"已上传 {per}.csv ，{len(df)} 行")

if __name__ == "__main__":
    generate_and_upload()