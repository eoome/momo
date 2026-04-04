"""测试共用 fixtures"""
import pandas as pd
import numpy as np
import pytest


@pytest.fixture
def trending_up_df() -> pd.DataFrame:
    """稳步上涨的K线数据"""
    n = 60
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    base = 1.0
    rows = []
    for i, d in enumerate(dates):
        price = base + i * 0.01  # 每天涨 0.01
        rows.append({
            "date": d, "open": price - 0.005, "close": price,
            "high": price + 0.01, "low": price - 0.01,
            "volume": 1000000 + i * 10000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def trending_down_df() -> pd.DataFrame:
    """稳步下跌的K线数据"""
    n = 60
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    base = 2.0
    rows = []
    for i, d in enumerate(dates):
        price = base - i * 0.01
        rows.append({
            "date": d, "open": price + 0.005, "close": price,
            "high": price + 0.01, "low": price - 0.01,
            "volume": 1000000 + i * 10000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def golden_cross_df() -> pd.DataFrame:
    """制造 MA5 上穿 MA20 的金叉场景"""
    n = 30
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    rows = []
    # 前 25 天缓慢下跌 → 让 MA20 较低
    for i in range(25):
        price = 2.0 - i * 0.02
        rows.append({
            "date": dates[i], "open": price, "close": price,
            "high": price + 0.005, "low": price - 0.005,
            "volume": 1000000,
        })
    # 后 5 天快速拉升 → MA5 快速上升穿过 MA20
    for i in range(25, n):
        price = rows[-1]["close"] + 0.15
        rows.append({
            "date": dates[i], "open": price - 0.02, "close": price,
            "high": price + 0.02, "low": price - 0.04,
            "volume": 2000000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def death_cross_df() -> pd.DataFrame:
    """制造 MA5 下穿 MA20 的死叉场景"""
    n = 30
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    rows = []
    # 前 25 天缓慢上涨
    for i in range(25):
        price = 1.0 + i * 0.02
        rows.append({
            "date": dates[i], "open": price, "close": price,
            "high": price + 0.005, "low": price - 0.005,
            "volume": 1000000,
        })
    # 后 5 天快速下跌
    for i in range(25, n):
        price = rows[-1]["close"] - 0.15
        rows.append({
            "date": dates[i], "open": price + 0.02, "close": price,
            "high": price + 0.04, "low": price - 0.02,
            "volume": 2000000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def oversold_rsi_df() -> pd.DataFrame:
    """制造 RSI 超卖的数据"""
    n = 30
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    rows = []
    price = 5.0
    for i, d in enumerate(dates):
        if i < 5:
            price += 0.1
        else:
            price -= 0.3  # 大幅下跌 → RSI 超卖
        rows.append({
            "date": d, "open": price + 0.05, "close": price,
            "high": price + 0.1, "low": price - 0.1,
            "volume": 1000000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def oversold_rsi_recovering_df() -> pd.DataFrame:
    """RSI 超卖后回升的场景"""
    n = 30
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    rows = []
    price = 5.0
    for i, d in enumerate(dates):
        if i < 5:
            price += 0.1
        elif i < 25:
            price -= 0.3
        else:
            price += 0.15  # 回升
        rows.append({
            "date": d, "open": price + 0.05, "close": price,
            "high": price + 0.1, "low": price - 0.1,
            "volume": 1000000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def bollinger_touch_lower_df() -> pd.DataFrame:
    """价格触及布林带下轨"""
    n = 30
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    rows = []
    for i, d in enumerate(dates):
        if i < 25:
            price = 1.0 + 0.001 * i  # 缓慢上涨建通道
        else:
            price = 1.0 - 0.1  # 突然大跌触下轨
        rows.append({
            "date": d, "open": price, "close": price,
            "high": price + 0.005, "low": price - 0.005,
            "volume": 1000000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def flat_df() -> pd.DataFrame:
    """横盘震荡数据"""
    n = 60
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    rows = []
    for i, d in enumerate(dates):
        price = 1.0 + 0.01 * np.sin(i * 0.5)  # 正弦波动
        rows.append({
            "date": d, "open": price, "close": price,
            "high": price + 0.005, "low": price - 0.005,
            "volume": 1000000,
        })
    return pd.DataFrame(rows)
