-- 维度表：商品信息（每个 SKU 一行，小表）
CREATE TABLE IF NOT EXISTS dim_product
(
    sku_id        UInt64,                              -- 12位数字(~2.9e11)超 UInt32，用 UInt64
    name          String                  CODEC(ZSTD(3)),  -- 高基数，只在此存一份
    category_id   UInt32,                              -- ~11亿 < 42.9亿，UInt32 够
    category_name LowCardinality(String)               -- 低基数 → 字典编码
)
ENGINE = ReplacingMergeTree
ORDER BY sku_id;

-- 事实表：每日价格与销量（大表，行数 = SKU数 × 天数）
CREATE TABLE IF NOT EXISTS fact_price_daily
(
    date        Date           CODEC(Delta, ZSTD(1)),  -- 2字节；按date排序，Delta后差值近乎为0
    sku_id      UInt64         CODEC(T64, ZSTD(1)),    -- 整数位压缩 + ZSTD
    category_id UInt32         CODEC(ZSTD(1)),         -- 冗余一份，免 join 直接 GROUP BY 类目
    price       Decimal32(4)   CODEC(ZSTD(1)),         -- 4字节，精确到万分位，避免浮点漂移
    sales       UInt32         CODEC(T64, ZSTD(1))     -- 销量(件)，非负整数
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (date, category_id, sku_id);

-- 结果表：各层级指数与同比（小表）
CREATE TABLE IF NOT EXISTS index_result
(
    date         Date                   CODEC(Delta, ZSTD(1)),
    dimension    LowCardinality(String),               -- 'overall' | 'category' | 'sku'
    dimension_id String,                               -- 'ALL' / 类目id / sku_id
    index_type   LowCardinality(String),               -- 'fisher_yoy' | 'jevons'
    index_value  Decimal64(6),                          -- 年度费雪(参照=去年同期=100)
    yoy_pct      Decimal32(4),                          -- 同比% = index_value - 100 ★交付物数据源★
    mom_pct      Decimal32(4)                           -- 环比%（本项目暂置0占位）
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (dimension, dimension_id, date);
