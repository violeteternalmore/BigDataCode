"""系统主入口：按序串起整条流水线。
从项目根目录运行：  python -m src.main
首次跑一次即可生成 3 年数据；之后日常调度可注释掉 generate_and_upload()。"""
from src.ingestion.generator import generate_and_upload
from src.ingestion.clean import clean_and_load
from src.compute.run_index import run as run_index
from src.viz.plot import plot_yoy

if __name__ == "__main__":
    generate_and_upload()   # ① 生成 → ② OSS（Bronze）
    clean_and_load()        # ③ 清洗 → ④ ClickHouse 明细表
    run_index()             # ⑤ 年度费雪 → ⑥ 同比
    plot_yoy()              # ⑦ 折线图 + ZIP
