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
            "base_sales": int(rng.uniform(50, 500)),
        })
    return prods


def _month_range():
    return pd.period_range(CFG["data"]["start"], CFG["data"]["end"], freq="M")


def _daily_inflation_path(rng):
    """构造一条'每日通胀率'曲线：缓慢游走 + 偶发低谷，使同比自然起落于 -1%~+2%。"""
    start, end = pd.Timestamp(CFG["data"]["start"]), pd.Timestamp(CFG["data"]["end"])
    days = pd.date_range(start, end, freq="D")
    n = len(days)
    # 年化通胀率在 ~1.5% 上下缓慢游走（用累积小步随机走，再拉回均值）
    annual = np.zeros(n); annual[0] = 0.015
    for t in range(1, n):
        annual[t] = annual[t-1] + rng.normal(0, 0.0008)      # 缓慢游走
        annual[t] += (0.015 - annual[t]) * 0.01              # 轻微均值回归，防跑飞
    annual = np.clip(annual, -0.02, 0.05)                    # 限制在 -2%~+5% 年化
    daily = annual / 365.0                                   # 转成每日通胀率
    return dict(zip(days.date, daily))


def _inject_dirty(df, rng, rate=0.01):
    idx = rng.choice(df.index, size=max(1, int(len(df) * rate)), replace=False)
    df.loc[idx[:len(idx) // 2], "price"] = 0
    df.loc[idx[len(idx) // 2:], "price"] = -1
    dup = df.sample(frac=rate / 2, random_state=int(rng.integers(1e9)))
    return pd.concat([df, dup], ignore_index=True)


def generate_and_upload():
    rng = np.random.default_rng(CFG["data"]["seed"])
    prods = _init_products(rng)
    infl = _daily_inflation_path(rng)          # 全局通胀率曲线（所有商品共享趋势）

    for per in _month_range():
        days = pd.date_range(per.start_time, per.end_time, freq="D")
        rows = []
        for p in prods:
            price = p["price"]
            for d in days:
                r = infl[d.date()]                              # 当日通胀率
                price *= (1 + r + rng.normal(0, 0.0015))        # 共享通胀 + 各自小噪声
                sales = max(0, int(rng.normal(p["base_sales"], p["base_sales"] * 0.2)))
                rows.append((p["product_id"], p["category_id"], p["name"],
                             round(price, 4), d.date(), sales))
            p["price"] = price
        df = pd.DataFrame(rows, columns=["product_id", "category_id", "name",
                                         "price", "change_date", "sales"])
        df = _inject_dirty(df, rng)
        buf = io.StringIO(); df.to_csv(buf, index=False)
        upload_bytes(f"{CFG['oss']['bronze_prefix']}{per}.csv", buf.getvalue().encode("utf-8"))
        print(f"已上传 {per}.csv ，{len(df)} 行")


if __name__ == "__main__":
    generate_and_upload()