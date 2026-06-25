# 高频电商价格指数平台

基于 **阿里云 ECS + OSS + ClickHouse + Python** 的高频价格指数流水线：
云端生成数据 → OSS 落湖 → 清洗 → ClickHouse → 年度费雪算同比 → 产出 CPI 样式 YoY 折线图。

> 详细的一步步搭建说明见《实操教程_从云端生成数据到产出折线图.md》。
> 设计依据见《高频电商价格指数平台_系统设计文档.md》。

## 目录结构
```
price-index/
├── src/
│   ├── ingestion/   generator.py(生成) clean.py(清洗)
│   ├── storage/     oss_client.py     ch_client.py
│   ├── compute/     index.py(纯算法)  run_index.py(年度费雪同比)
│   ├── viz/         plot.py(折线图+ZIP)
│   └── main.py      一键串联入口
├── config/config.yaml   非敏感参数
├── sql/ddl.sql          ClickHouse 建表
├── tests/test_index.py  pytest 单元测试
└── .env.example         复制为 .env 填密钥（.env 不入库）
```

## 快速开始（在 ECS 上，项目根目录执行）
```bash
# 0. 装依赖
pip3 install -r requirements.txt

# 1. 配置：复制 .env 模板并填入真实密钥；按需改 config/config.yaml
cp .env.example .env && vim .env

# 2. 建 ClickHouse 库表
clickhouse-client --query "CREATE DATABASE IF NOT EXISTS price"
clickhouse-client --database price --multiquery < sql/ddl.sql

# 3. 跑通全流程（首次会生成 3 年数据，约几分钟）
python3 -m src.main

# 4. 单元测试
pytest -q
```
跑完去 OSS 的 `output/` 下载 `yoy.png`（最终折线图）和 `index_result.zip`。

## 注意
- 必须从**项目根目录**运行（代码用相对路径读 `config/config.yaml`）。
- 因为同比要「对去年同日」，**2026-05 之前的日期没有同比结果是正常的**。
- 跑完记得**释放按量付费的 ECS** 省钱。
- `n_products` 默认 20000（约 2250 万行、原始约 1.4 GB）；内存吃紧（如 2核4GB）可调小，想压测就调更大。
- 索引计算按类目分批在 ClickHouse 内自连接聚合，内存可控；相关参数见 `config.yaml` 的 `clickhouse` 段。
