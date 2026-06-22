import numpy as np


def jevons(prices):
    """几何平均：用于同 SKU 多报价去重，或无权重初级聚合。非正价格被忽略。"""
    p = np.asarray(prices, dtype=float)
    p = p[p > 0]
    return float(np.exp(np.log(p).mean())) if len(p) else np.nan


def fisher(p0, q0, p1, q1):
    """费雪指数(×100)：p0/q0=参照期价量, p1/q1=当期价量，按 SKU 对齐的数组。
    本项目里参照期 = 去年同期，所以这一次比较出来的就是年度（同比）费雪。"""
    p0, q0, p1, q1 = (np.asarray(x, float) for x in (p0, q0, p1, q1))
    L = (p1 * q0).sum() / (p0 * q0).sum()    # 拉氏：参照期销量权重
    P = (p1 * q1).sum() / (p0 * q1).sum()    # 帕氏：当期销量权重
    return float(np.sqrt(L * P)) * 100
