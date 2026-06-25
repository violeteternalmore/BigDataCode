"""画图相关测试。
   单元部分：测重采样纯逻辑(不连外部)。
   集成部分：真跑 plot_yoy，连 ClickHouse/OSS，无 .env 时自动跳过。"""
import os
import pandas as pd
import pytest
from src.viz.plot import resample_yoy


# ---------- 单元测试：重采样聚合逻辑 ----------
def test_resample_monthly_averages():
    # 同月两天的同比(10、20)，按月重采样应得均值15
    df = pd.DataFrame([
        ("2027-05-01", "overall", "ALL", 10.0),
        ("2027-05-15", "overall", "ALL", 20.0),
    ], columns=["date", "dimension", "dimension_id", "yoy_pct"])
    out = resample_yoy(df, "M")
    assert len(out) == 1
    assert abs(out.iloc[0]["yoy_pct"] - 15.0) < 1e-9

def test_resample_keeps_dimensions_separate():
    # 不同维度不应被混在一起聚合
    df = pd.DataFrame([
        ("2027-05-01", "overall",  "ALL", 10.0),
        ("2027-05-01", "category", "100", 30.0),
    ], columns=["date", "dimension", "dimension_id", "yoy_pct"])
    out = resample_yoy(df, "M")
    assert len(out) == 2     # 两个维度各自一行，互不干扰

def test_resample_drops_nan():
    df = pd.DataFrame([
        ("2027-05-01", "overall", "ALL", float("nan")),
        ("2027-05-02", "overall", "ALL", 5.0),
    ], columns=["date", "dimension", "dimension_id", "yoy_pct"])
    out = resample_yoy(df, "W")
    assert (out["yoy_pct"].notna()).all()   # NaN 被丢弃


# ---------- 集成测试：真跑出图（需云资源）----------
@pytest.mark.skipif(not os.path.exists(".env"),
                    reason="无 .env，跳过需要 ClickHouse/OSS 的出图集成测试")
def test_plot_yoy_runs_and_uploads():
    """完整跑一遍出图：不报错即视为通过(产物已上传OSS)。"""
    from src.viz.plot import plot_yoy
    plot_yoy()   # 跑通不抛异常即 OK