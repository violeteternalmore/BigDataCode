"""单元测试·指数计算正确性（不连任何外部系统）。"""
import numpy as np
from src.compute.index import jevons, fisher


def test_jevons_geometric_mean():
    assert abs(jevons([2, 8]) - 4.0) < 1e-9            # √(2×8)=4

def test_jevons_ignores_nonpositive():
    assert abs(jevons([2, 8, 0, -5]) - 4.0) < 1e-9     # 0/负被忽略

def test_jevons_empty_returns_nan():
    assert np.isnan(jevons([0, -1]))                   # 全无效→NaN，不报错

def test_fisher_no_change_is_100():
    assert abs(fisher([10, 20], [5, 5], [10, 20], [5, 5]) - 100) < 1e-9

def test_fisher_all_double_is_200():
    assert abs(fisher([10, 20], [5, 5], [20, 40], [5, 5]) - 200) < 1e-9  # 全翻倍→200

def test_fisher_handles_zero_sales():
    assert fisher([10, 20], [5, 5], [12, 20], [5, 0]) > 0   # 销量为0不报除零
