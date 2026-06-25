"""连接测试·验证 OSS 与 ClickHouse 连得上、表已建好、读写权限正常。
   需要真实云资源，故在无 .env 时自动跳过（便于在 CI 或他人环境安全跳过）。"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists(".env"),
    reason="无 .env，跳过需要真实云资源的连接测试"
)


def test_clickhouse_alive():
    """能连上 ClickHouse 并执行查询。"""
    from src.storage.ch_client import query_df
    df = query_df("SELECT 1 AS ok")
    assert df.iloc[0]["ok"] == 1

def test_clickhouse_tables_exist():
    """三张目标表均已建好。"""
    from src.storage.ch_client import query_df
    tables = set(query_df("SHOW TABLES FROM price")["name"])
    assert {"dim_product", "fact_price_daily", "index_result"} <= tables

def test_oss_round_trip():
    """往 OSS 写一个测试对象再读回，内容一致 → 连通且有读写权限。"""
    from src.storage.oss_client import upload_bytes, download_text
    key = "healthcheck/ping.txt"
    upload_bytes(key, "pong".encode("utf-8"))
    assert download_text(key) == "pong"
