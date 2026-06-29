import io, os, zipfile
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]
import matplotlib.pyplot as plt
import pandas as pd, yaml
from src.storage.ch_client import query_df
from src.storage.oss_client import upload_bytes
CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))

FREQ = "D"   # 改这里：'D'=每日  'W'=每周（推荐，细节多又不杂乱）  'M'=每月（最平滑）

def plot_yoy():
    df = query_df("SELECT date, dimension, dimension_id, yoy_pct FROM index_result")
    df["date"] = pd.to_datetime(df["date"])
    g = resample_yoy(df, FREQ)

    fig, ax = plt.subplots(figsize=(13, 6))
    overall = g[g["dimension"] == "overall"].sort_values("bucket")
    ax.plot(overall["bucket"], overall["yoy_pct"], lw=2.5, color="#c0392b",
            marker="o", markersize=3, label="Overall")          # marker=点
    for cat, sub in g[g["dimension"] == "category"].groupby("dimension_id"):
        sub = sub.sort_values("bucket")
        ax.plot(sub["bucket"], sub["yoy_pct"], lw=1.2, alpha=.7,
                marker="o", markersize=2, label=f"Cat {cat}")
    ax.axhline(0, color="gray", lw=.8)
    ax.set_title(f"E-commerce Price Index - YoY % Change ({FREQ})")
    ax.set_ylabel("YoY %"); ax.set_xlabel("Date")
    ax.legend(fontsize=8, ncol=2); ax.grid(alpha=.3)
    fig.autofmt_xdate(); fig.tight_layout()

    png = io.BytesIO(); fig.savefig(png, dpi=150, format="png")
    pngbytes = png.getvalue()

    csv = df.to_csv(index=False).encode("utf-8")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index_result.csv", csv)
    zipbytes = zbuf.getvalue()

    # 本地各存一份（供 CI 取回挂 Artifacts；.gitignore 已忽略 *.png/*.zip）
    os.makedirs("output", exist_ok=True)
    with open("output/yoy.png", "wb") as f:
        f.write(pngbytes)
    with open("output/index_result.zip", "wb") as f:
        f.write(zipbytes)

    # 同步上传 OSS
    upload_bytes(CFG["oss"]["output_prefix"] + "yoy.png", pngbytes)
    upload_bytes(CFG["oss"]["output_prefix"] + "index_result.zip", zipbytes)
    print(f"图(粒度={FREQ})与ZIP已写 ./output/ 并上传 OSS")


def resample_yoy(df, freq="W"):
    """纯逻辑（不连外部）：把日度同比按freq(D/W/M)重采样取平均。
    输入含data,dimension,dimension_id,yoy_pct的DataFrame,返回聚合后的DataFrame。"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["bucket"] = df["date"].dt.to_period(freq).dt.to_timestamp()
    return (df.groupby(["dimension", "dimension_id", "bucket"])["yoy_pct"]
            .mean().reset_index().dropna())