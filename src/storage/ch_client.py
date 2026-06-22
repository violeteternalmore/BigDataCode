import os
import yaml
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()
CFG = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))


def client():
    return clickhouse_connect.get_client(
        host=CFG["clickhouse"]["host"],
        port=CFG["clickhouse"]["port"],
        database=CFG["clickhouse"]["database"],
        password=os.environ.get("CH_PASSWORD", ""),
    )


def insert_df(table, df):
    client().insert_df(table, df)


def query_df(sql):
    return client().query_df(sql)
