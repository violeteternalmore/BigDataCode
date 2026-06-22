import pandas as pd
import yaml

from src.storage.ch_client import query_df, insert_df
from src.compute.index import fisher

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def _annual_fisher(panel):
    """对某维度的 panel(含 date,sku_id,price,sales)，逐日算「本日 vs 去年同日」的费雪。
    参照期被钉死成去年同期，所以无需固定基期，结果直接就是同比。"""
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    # 参照盘：把去年的日期 +1 年，对齐到「今年同日」，再按 (date,sku_id) join
    base = panel.rename(columns={"price": "p0", "sales": "q0"})[["date", "sku_id", "p0", "q0"]].copy()
    base["date"] = base["date"] + pd.DateOffset(years=1)          # 去年同日 → 今年同日
    cur = panel.rename(columns={"price": "p1", "sales": "q1"})[["date", "sku_id", "p1", "q1"]]
    m = cur.merge(base, on=["date", "sku_id"], how="inner")       # 两期都在的可比商品
    out = []
    for d, g in m.groupby("date"):
        out.append((d, fisher(g["p0"], g["q0"], g["p1"], g["q1"])))
    res = pd.DataFrame(out, columns=["date", "index_value"])
    res["yoy_pct"] = res["index_value"] - 100                     # 参照期=去年同期=100
    return res


def run():
    panel = query_df("SELECT date, sku_id, category_id, price, sales FROM fact_price_daily")
    results = []

    # 全网同比
    s = _annual_fisher(panel)
    s["dimension"] = "overall"
    s["dimension_id"] = "ALL"
    results.append(s)

    # 各类目同比
    for cat, sub in panel.groupby("category_id"):
        s = _annual_fisher(sub)
        s["dimension"] = "category"
        s["dimension_id"] = str(cat)
        results.append(s)

    res = pd.concat(results, ignore_index=True)
    res["index_type"] = "fisher_yoy"
    res["mom_pct"] = 0.0
    res["date"] = pd.to_datetime(res["date"]).dt.date
    res = res[["date", "dimension", "dimension_id", "index_type",
               "index_value", "yoy_pct", "mom_pct"]]

    # 熔断：全网同比单日跳变 >50 个百分点视为污染，告警
    chk = res[res["dimension"] == "overall"].sort_values("date")
    jump = chk["yoy_pct"].diff().abs().max()
    if pd.notna(jump) and jump > CFG["index"]["max_daily_change"] * 100:
        print(f"⚠ 熔断告警：全网同比单日跳变 {jump:.1f} 个百分点，疑似源数据污染！")

    insert_df("index_result", res.dropna(subset=["index_value"]))
    print(f"年度费雪同比落库 {len(res)} 行（前 1 年因无去年同期数据，自然没有结果）")


if __name__ == "__main__":
    run()
