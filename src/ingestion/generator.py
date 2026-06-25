import io
import numpy as np
import pandas as pd
import yaml
from src.storage.oss_client import upload_bytes
CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))

# —— CPI 形态参数 ——
ANNUAL_INFLATION = 0.02          # 年通胀基线 +2%
DAILY_TREND = ANNUAL_INFLATION / 365.0   # 摊到每天的温和上行
DAILY_NOISE = 0.002              # 每日 ±0.2% 随机游走


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
            "base_price": None,                       # 基准价（首日设定，季节性围绕它波动）
            # 每个类目季节振幅/相位略不同，让各类目曲线不雷同
            "seasonal_amp": 0.02 + 0.02 * (cat % 5) / 4,   # 季节振幅 2%~4%
            "phase": rng.uniform(0, 2 * np.pi),       # 季节相位
            "base_sales": int(rng.uniform(50, 500)),
        })
    return prods


def _month_range():
    return pd.period_range(CFG["data"]["start"], CFG["data"]["end"], freq="M")


def _inject_dirty(df, rng, rate=0.01):
    idx = rng.choice(df.index, size=max(1, int(len(df) * rate)), replace=False)
    df.loc[idx[:len(idx) // 2], "price"] = 0
    df.loc[idx[len(idx) // 2:], "price"] = -1
    dup = df.sample(frac=rate / 2, random_state=int(rng.integers(1e9)))
    return pd.concat([df, dup], ignore_index=True)


def generate_and_upload():
    rng = np.random.default_rng(CFG["data"]["seed"])
    prods = _init_products(rng)
    start = pd.Timestamp(CFG["data"]["start"])
    # 克制的小事件：第3类目某段时间额外微涨（累计仅几个百分点，可注释掉）
    shock = {"cat": CFG["data"]["categories"][2],
             "start": pd.Timestamp("2026-09-01"),
             "end":   pd.Timestamp("2027-02-01"),
             "rate": 0.0002}

    for per in _month_range():
        days = pd.date_range(per.start_time, per.end_time, freq="D")
        rows = []
        for p in prods:
            for d in days:
                t = (d - start).days
                # ① 温和上行的基线（趋势）
                trend = p["price"] * (1 + DAILY_TREND) ** t
                # ② 季节性：年周期正弦（这是“起起落落”的主来源）
                season = 1 + p["seasonal_amp"] * np.sin(2 * np.pi * t / 365.0 + p["phase"])
                # ③ 日常小噪声
                noise = 1 + rng.normal(0, DAILY_NOISE)
                price = trend * season * noise
                # ④ 克制的小事件
                if p["category_id"] == shock["cat"] and shock["start"] <= d < shock["end"]:
                    extra_days = (d - shock["start"]).days
                    price *= (1 + shock["rate"]) ** extra_days
                sales = max(0, int(rng.normal(p["base_sales"], p["base_sales"] * 0.2)))
                rows.append((p["product_id"], p["category_id"], p["name"],
                             round(price, 4), d.date(), sales))
        df = pd.DataFrame(rows, columns=["product_id", "category_id", "name",
                                         "price", "change_date", "sales"])
        df = _inject_dirty(df, rng)
        buf = io.StringIO(); df.to_csv(buf, index=False)
        upload_bytes(f"{CFG['oss']['bronze_prefix']}{per}.csv", buf.getvalue().encode("utf-8"))
        print(f"已上传 {per}.csv ，{len(df)} 行")


if __name__ == "__main__":
    generate_and_upload()