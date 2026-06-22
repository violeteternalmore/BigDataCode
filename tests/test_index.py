from src.compute.index import jevons, fisher


def test_jevons_ignores_nonpositive():
    assert abs(jevons([2, 8, 0, -5]) - 4.0) < 1e-9   # sqrt(2*8)=4，0/负被忽略


def test_fisher_no_change_is_100():
    p0 = [10, 20]; q0 = [5, 5]; p1 = [10, 20]; q1 = [5, 5]
    assert abs(fisher(p0, q0, p1, q1) - 100) < 1e-9  # 价格不变 → 指数=100


def test_fisher_handles_zero_sales():
    # 1个商品销量跌至0，不应报除零
    v = fisher([10, 20], [5, 5], [12, 20], [5, 0])
    assert v > 0
