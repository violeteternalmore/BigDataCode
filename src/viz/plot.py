import io
import zipfile

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]  # 服务器无中文字体时用英文标签
import matplotlib.pyplot as plt
import pandas as pd
import yaml

from src.storage.ch_client import query_df
from src.storage.oss_client import upload_bytes

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def plot_yoy():
    df = query_df("SELECT date, dimension, dimension_id, yoy_pct FROM index_result")
    df["date"] = pd.to_datetime(df["date"])
    # 重采样到月度，做成 CPI 样式（更平滑）
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    monthly = (df.groupby(["dimension", "dimension_id", "month"])["yoy_pct"]
                 .mean().reset_index().dropna())

    fig, ax = plt.subplots(figsize=(11, 5))
    overall = monthly[monthly["dimension"] == "overall"]
    ax.plot(overall["month"], overall["yoy_pct"], lw=2.5, label="Overall", color="#c0392b")
    for cat, sub in monthly[monthly["dimension"] == "category"].groupby("dimension_id"):
        ax.plot(sub["month"], sub["yoy_pct"], lw=1, alpha=.6, label=f"Cat {cat}")
    ax.axhline(0, color="gray", lw=.8)
    ax.set_title("E-commerce Price Index - YoY % Change")
    ax.set_ylabel("YoY %")
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()

    png = io.BytesIO()
    fig.savefig(png, dpi=150, format="png")
    upload_bytes(CFG["oss"]["output_prefix"] + "yoy.png", png.getvalue())

    # 打包结果 CSV → ZIP → 传 OSS
    csv = df.drop(columns="month").to_csv(index=False).encode("utf-8")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index_result.csv", csv)
    upload_bytes(CFG["oss"]["output_prefix"] + "index_result.zip", zbuf.getvalue())
    print("折线图 yoy.png 与 index_result.zip 已上传 OSS")


if __name__ == "__main__":
    plot_yoy()
