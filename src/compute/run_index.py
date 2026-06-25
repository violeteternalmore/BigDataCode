import pandas as pd
import yaml

from src.storage.ch_client import query_df, insert_df
from src.compute.index import fisher

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def _annual_fisher(panel):
    """【纯算法·参考实现，供单元测试在小样本上校验】
    对某维度的 panel(含 date,sku_id,price,sales)，逐日算「本日 vs 去年同日」的费雪。
    参照期被钉死成去年同期，所以无需固定基期，结果直接就是同比。
    生产路径(run)在 ClickHouse 内用等价 SQL 完成同样的计算，以适配大数据量/小内存。"""
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


# ---- 生产路径：把上面的算法下推到 ClickHouse，避免把整张事实表搬进内存 ----
# 子查询 f0 = 去年同日的价量(把日期 +1 年对齐到今年)，与今年 f1 按 (sku_id,date) 等值连接，
# 即「两期都在的可比商品」；价×量用 Float64 求和(防 Decimal 溢出)，再合成费雪指数。
_FISHER = """
    sqrt(
        (sum(toFloat64(f1.price) * f0.q0) / sum(f0.p0 * f0.q0)) *
        (sum(toFloat64(f1.price) * f1.sales) / sum(f0.p0 * f1.sales))
    ) * 100
"""

_JOIN = """
    FROM fact_price_daily AS f1
    INNER JOIN (
        SELECT sku_id,
               date + INTERVAL 1 YEAR AS date,   -- 去年同日 -> 今年同日
               toFloat64(price) AS p0,
               sales AS q0
        FROM fact_price_daily
    ) AS f0 ON f1.sku_id = f0.sku_id AND f1.date = f0.date
"""


def _settings():
    """把 ClickHouse 查询级设置(自连接算法/内存上限)拼成 SETTINGS 子句，便于小内存机器调优。"""
    ch = CFG.get("clickhouse", {})
    parts = []
    if ch.get("join_algorithm"):
        parts.append(f"join_algorithm = '{ch['join_algorithm']}'")
    if ch.get("max_memory_usage"):
        parts.append(f"max_memory_usage = {ch['max_memory_usage']}")
    return ("SETTINGS " + ", ".join(parts)) if parts else ""


def _overall():
    return query_df(f"""
        SELECT f1.date AS date, {_FISHER} AS index_value
        {_JOIN}
        GROUP BY f1.date
        ORDER BY f1.date
        {_settings()}
    """)


def _by_category():
    return query_df(f"""
        SELECT f1.category_id AS category_id, f1.date AS date, {_FISHER} AS index_value
        {_JOIN}
        GROUP BY f1.category_id, f1.date
        ORDER BY f1.category_id, f1.date
        {_settings()}
    """)


def run():
    # 全网同比（聚合在 ClickHouse 内完成，仅回传每日一行结果）
    ov = _overall()
    ov["dimension"] = "overall"
    ov["dimension_id"] = "ALL"

    # 各类目同比
    cat = _by_category()
    cat["dimension"] = "category"
    cat["dimension_id"] = cat["category_id"].astype(str)
    cat = cat.drop(columns="category_id")

    res = pd.concat([ov, cat], ignore_index=True)
    res["index_type"] = "fisher_yoy"
    res["yoy_pct"] = res["index_value"] - 100                     # 参照期=去年同期=100
    res["mom_pct"] = 0.0
    res["date"] = pd.to_datetime(res["date"]).dt.date
    res = res[["date", "dimension", "dimension_id", "index_type",
               "index_value", "yoy_pct", "mom_pct"]]

    # 熔断：全网同比单日跳变 >阈值 视为污染，告警
    chk = res[res["dimension"] == "overall"].sort_values("date")
    jump = chk["yoy_pct"].diff().abs().max()
    if pd.notna(jump) and jump > CFG["index"]["max_daily_change"] * 100:
        print(f"⚠ 熔断告警：全网同比单日跳变 {jump:.1f} 个百分点，疑似源数据污染！")

    insert_df("index_result", res.dropna(subset=["index_value"]))
    print(f"年度费雪同比落库 {len(res)} 行（前 1 年因无去年同期数据，自然没有结果）")


if __name__ == "__main__":
    run()
