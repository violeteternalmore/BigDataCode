import io
import numpy as np
import pandas as pd
import yaml
from src.storage.oss_client import upload_bytes
CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def _month_range():
    return pd.period_range(CFG["data"]["start"], CFG["data"]["end"], freq="M")


def _category_daily_rates(rng):
    """为每个类目构造一条「每日通胀率」曲线。
    年化率 = 1% 基线 + 多年缓慢波动(正弦) + 轻微均值回归随机游走，并硬性裁剪到 [0%, 2%]。
    各类目错峰、振幅略异，使同比折线既贴近 1%、又呈现可辨的类目分化与拐点。
    返回 (days, {category_id: 每日通胀率数组})。"""
    d = CFG["data"]
    inf = d.get("inflation", {})
    center = inf.get("center", 0.010)        # 年化通胀基线 ~1%
    amp = inf.get("amp", 0.0055)             # 正弦波动振幅
    period = inf.get("period_days", 540.0)   # 波动周期(天)，>1年才不会被同比抵消
    walk_sd = inf.get("walk_sd", 0.0004)     # 随机游走步长
    rev = inf.get("walk_reversion", 0.02)    # 向 0 的均值回归强度
    lo = inf.get("annual_min", 0.0)          # 年化下限
    hi = inf.get("annual_max", 0.020)        # 年化上限(2%)，保证同比不超 2%

    cats = d["categories"]
    days = pd.date_range(d["start"], d["end"], freq="D")
    n = len(days); t = np.arange(n)
    rates = {}
    for k, cat in enumerate(cats):
        a = amp + 0.0010 * (k - (len(cats) - 1) / 2)     # 各类目振幅略不同
        phase = np.pi * k / len(cats)                    # 各类目错峰
        seasonal = center + a * np.sin(2 * np.pi * t / period + phase)
        walk = np.zeros(n)
        for i in range(1, n):
            walk[i] = walk[i-1] + rng.normal(0, walk_sd)
            walk[i] -= walk[i] * rev                      # 均值回归，防跑飞
        annual = np.clip(seasonal + walk, lo, hi)
        rates[cat] = annual / 365.0                       # 转每日通胀率
    return days, rates


def _inject_dirty(df, rng, rate=0.01):
    idx = rng.choice(df.index, size=max(1, int(len(df) * rate)), replace=False)
    df.loc[idx[:len(idx) // 2], "price"] = 0
    df.loc[idx[len(idx) // 2:], "price"] = -1
    dup = df.sample(frac=rate / 2, random_state=int(rng.integers(1e9)))
    return pd.concat([df, dup], ignore_index=True)


def generate_and_upload():
    d = CFG["data"]
    rng = np.random.default_rng(d["seed"])
    cats = d["categories"]
    n_prod = d["n_products"]
    noise_sd = d.get("price_noise_sd", 0.0008)            # 各商品每日独立小噪声

    # 商品静态属性（向量化，按 i%类目数 轮流分到各类目）
    prod_ids = 290000000000 + np.arange(n_prod, dtype=np.int64)
    prod_catidx = np.arange(n_prod) % len(cats)
    prod_cat = np.array(cats)[prod_catidx]
    names = np.char.add("商品_", np.arange(n_prod).astype(str))
    price = rng.uniform(5, 200, size=n_prod)              # 当前价（跨月连续游走）
    base_sales = rng.uniform(50, 500, size=n_prod)

    days, daily_rate = _category_daily_rates(rng)         # 各类目共享的通胀趋势
    rate_lut = {c: pd.Series(r, index=days.date) for c, r in daily_rate.items()}

    for per in _month_range():
        mdays = pd.date_range(per.start_time, per.end_time, freq="D")
        D = len(mdays)
        # 各类目当月每日通胀率 → 按商品所属类目展开成 (n_prod, D)
        rate_by_cat = np.vstack([rate_lut[c].loc[mdays.date].values for c in cats])
        rate = rate_by_cat[prod_catidx]                  # (n_prod, D)
        noise = rng.normal(0, noise_sd, size=(n_prod, D))
        path = price[:, None] * np.cumprod(1 + rate + noise, axis=1)   # 连续游走
        price = path[:, -1].copy()                       # 月末价带入下月
        sales = np.clip(rng.normal(base_sales[:, None], base_sales[:, None] * 0.2,
                                   size=(n_prod, D)), 0, None).astype(np.int64)

        df = pd.DataFrame({
            "product_id":  np.repeat(prod_ids, D),
            "category_id": np.repeat(prod_cat, D),
            "name":        np.repeat(names, D),
            "price":       np.round(path.reshape(-1), 4),
            "change_date": np.tile(mdays.date, n_prod),
            "sales":       sales.reshape(-1),
        })
        df = _inject_dirty(df, rng)
        buf = io.StringIO(); df.to_csv(buf, index=False)
        upload_bytes(f"{CFG['oss']['bronze_prefix']}{per}.csv", buf.getvalue().encode("utf-8"))
        print(f"已上传 {per}.csv ，{len(df)} 行")


if __name__ == "__main__":
    generate_and_upload()
