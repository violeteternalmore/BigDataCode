"""系统主入口：按模式串起流水线。
用法：python -m src.main [deploy|import|full|reset]   （缺省=full，保持旧行为）
  deploy  仅检测 OSS bronze 状态，不动数据库（push 默认档）
  import  用 OSS 已有 bronze 数据：清洗入库 → 算同比 → 出图
  full    生成新数据 → OSS → 清洗入库 → 算同比 → 出图
  reset   删 OSS 数据 + DROP 重建表，再跑整套 full（危险，需显式触发）
出图模式(import/full/reset)会在 ./output/ 下生成 yoy.png 与 index_result.zip 并上传 OSS。
从项目根目录运行。"""
import sys
import yaml

from src.ingestion.generator import generate_and_upload
from src.ingestion.clean import clean_and_load
from src.compute.run_index import run as run_index
from src.viz.plot import plot_yoy
from src.storage.oss_client import list_keys, delete_prefix
from src.storage.ch_client import command

CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))
TABLES = ["index_result", "fact_price_daily", "dim_product"]


def _truncate_tables():
    """清空三张表，保证导入幂等（重复跑不会翻倍）。"""
    for t in TABLES:
        command(f"TRUNCATE TABLE IF EXISTS {t}")


def _rebuild_tables():
    """DROP 三张表后按 sql/ddl.sql 重建（reset 用；库 price 须已存在）。"""
    for t in TABLES:
        command(f"DROP TABLE IF EXISTS {t}")
    ddl = open("sql/ddl.sql", encoding="utf-8").read()
    for stmt in ddl.split(";"):
        if stmt.strip():
            command(stmt)


def _pipeline():
    clean_and_load()    # 清洗 → ClickHouse 明细表
    run_index()         # 年度费雪 → 同比
    plot_yoy()          # 折线图 + ZIP（写 ./output/ 并传 OSS）


def deploy():
    keys = list_keys(CFG["oss"]["bronze_prefix"])
    print(f"[deploy] 仅检测：OSS bronze 现有 {len(keys)} 个对象，未改动数据库")


def import_():
    keys = list_keys(CFG["oss"]["bronze_prefix"])
    if not keys:
        print("[import] OSS bronze 为空，无可导入数据；请先用 full 生成。")
        return
    _truncate_tables()
    _pipeline()


def full():
    _truncate_tables()
    generate_and_upload()
    _pipeline()


def reset():
    n = delete_prefix(CFG["oss"]["bronze_prefix"])
    m = delete_prefix(CFG["oss"]["output_prefix"])
    print(f"[reset] 已删 OSS bronze {n} + output {m} 个对象")
    _rebuild_tables()
    print("[reset] ClickHouse 表已 DROP 并按 ddl.sql 重建")
    generate_and_upload()
    _pipeline()


MODES = {"deploy": deploy, "import": import_, "full": full, "reset": reset}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode not in MODES:
        sys.exit(f"未知模式 {mode!r}；可选：{', '.join(MODES)}")
    print(f"=== 运行模式：{mode} ===")
    MODES[mode]()
