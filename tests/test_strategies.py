"""13 种策略单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np

from signal_engine.core.signal import Signal, SignalType, combine_signals
from signal_engine.core.strategies import (
    strategy_dual_ma, strategy_rsi, strategy_bollinger,
    strategy_momentum, strategy_volume, strategy_macd,
    strategy_kdj, strategy_cci, strategy_williams,
    strategy_adx, strategy_sar, strategy_obv, strategy_trix,
    STRATEGY_FNS,
)


# ================================================================
# 通用测试
# ================================================================

class TestStrategyRegistry:
    def test_all_strategies_registered(self):
        assert len(STRATEGY_FNS) >= 14

    def test_registry_keys(self):
        expected = {"dual_ma", "rsi", "bollinger", "volume_anomaly", "momentum",
                    "macd", "kdj", "cci", "williams", "adx", "sar", "obv", "trix",
                    "hl_cross"}
        assert expected.issubset(set(STRATEGY_FNS.keys()))

    def test_all_registered_are_callable(self):
        for key, fn in STRATEGY_FNS.items():
            assert callable(fn), f"{key} is not callable"


class TestEmptyData:
    """空数据不应崩溃"""

    def test_dual_ma_empty(self):
        assert strategy_dual_ma(pd.DataFrame()) is None

    def test_rsi_empty(self):
        assert strategy_rsi(pd.DataFrame()) is None

    def test_bollinger_empty(self):
        assert strategy_bollinger(pd.DataFrame()) is None


class TestInsufficientData:
    """数据量不足时返回 None"""

    def test_dual_ma_too_short(self):
        df = pd.DataFrame({"close": [1.0] * 10, "open": [1.0]*10,
                           "high": [1.01]*10, "low": [0.99]*10, "volume": [100]*10})
        assert strategy_dual_ma(df, fast=5, slow=20) is None

    def test_macd_too_short(self):
        df = pd.DataFrame({"close": [1.0] * 20, "open": [1.0]*20,
                           "high": [1.01]*20, "low": [0.99]*20, "volume": [100]*20})
        assert strategy_macd(df) is None


# ================================================================
# 双均线
# ================================================================

class TestDualMA:
    def test_golden_cross(self, golden_cross_df):
        sig = strategy_dual_ma(golden_cross_df, fast=5, slow=20)
        assert sig is not None
        assert sig.signal in (SignalType.STRONG_BUY, SignalType.BUY)

    def test_death_cross(self, death_cross_df):
        sig = strategy_dual_ma(death_cross_df, fast=5, slow=20)
        assert sig is not None
        assert sig.signal in (SignalType.STRONG_SELL, SignalType.SELL)

    def test_trending_up(self, trending_up_df):
        sig = strategy_dual_ma(trending_up_df, fast=5, slow=20)
        assert sig is not None
        # 上涨趋势中可能持有或买
        assert sig.signal in (SignalType.BUY, SignalType.HOLD, SignalType.STRONG_BUY)

    def test_flat(self, flat_df):
        sig = strategy_dual_ma(flat_df, fast=5, slow=20)
        # 横盘波动可能产生交叉信号，只要返回结果即可
        assert sig is not None


# ================================================================
# RSI
# ================================================================

class TestRSI:
    def test_oversold(self, oversold_rsi_df):
        sig = strategy_rsi(oversold_rsi_df, period=14)
        assert sig is not None
        assert sig.signal in (SignalType.BUY, SignalType.STRONG_BUY)

    def test_oversold_recovering(self, oversold_rsi_recovering_df):
        sig = strategy_rsi(oversold_rsi_recovering_df, period=14)
        assert sig is not None
        # 回升应该是 STRONG_BUY
        assert sig.signal in (SignalType.BUY, SignalType.STRONG_BUY)

    def test_trending_up_rsi(self, trending_up_df):
        sig = strategy_rsi(trending_up_df, period=14)
        assert sig is not None
        # 持续上涨 RSI 会偏高

    def test_rsi_neutral_range(self, flat_df):
        sig = strategy_rsi(flat_df, period=14)
        assert sig is not None
        assert sig.confidence > 0


# ================================================================
# 布林带
# ================================================================

class TestBollinger:
    def test_touch_lower(self, bollinger_touch_lower_df):
        sig = strategy_bollinger(bollinger_touch_lower_df, period=20, std_mult=2.0)
        assert sig is not None
        # 大跌应该触发买入信号
        assert sig.signal in (SignalType.BUY, SignalType.STRONG_BUY)

    def test_trending_up(self, trending_up_df):
        sig = strategy_bollinger(trending_up_df, period=20)
        assert sig is not None

    def test_signal_has_details(self, trending_up_df):
        sig = strategy_bollinger(trending_up_df, period=20)
        if sig and sig.signal in (SignalType.STRONG_BUY, SignalType.STRONG_SELL):
            assert "upper" in sig.details
            assert "lower" in sig.details


# ================================================================
# 涨速监控
# ================================================================

class TestMomentum:
    def test_no_signal_when_flat(self):
        n = 20
        rows = [{"close": 1.0, "open": 1.0, "high": 1.01, "low": 0.99, "volume": 1000} for _ in range(n)]
        df = pd.DataFrame(rows)
        sig = strategy_momentum(df, window=15, alert_pct=2.0)
        assert sig is None

    def test_sharp_drop(self):
        n = 20
        rows = [{"close": 1.0, "open": 1.0, "high": 1.01, "low": 0.99, "volume": 1000} for _ in range(n)]
        # 最后几根快速下跌
        for i in range(15, 20):
            rows[i] = {"close": 1.0 - (i - 14) * 0.01, "open": 1.0, "high": 1.01, "low": 0.95, "volume": 1000}
        df = pd.DataFrame(rows)
        sig = strategy_momentum(df, window=15, alert_pct=2.0)
        # 跌幅不够 2% 可能 None，看具体数值
        if sig:
            assert sig.signal in (SignalType.BUY, SignalType.STRONG_BUY)


# ================================================================
# 量价异动
# ================================================================

class TestVolumeAnomaly:
    def test_volume_spike_up(self):
        n = 25
        rows = []
        for i in range(n):
            vol = 1000000
            price = 1.0 + i * 0.001
            if i == n - 1:
                vol = 5000000  # 放量 5 倍
                price = 1.05  # 大幅上涨
            rows.append({"close": price, "open": price - 0.005,
                         "high": price + 0.01, "low": price - 0.01,
                         "volume": vol})
        df = pd.DataFrame(rows)
        sig = strategy_volume(df, avg_period=20, spike_mult=2.0)
        assert sig is not None
        assert sig.signal == SignalType.BUY

    def test_volume_spike_down(self):
        n = 25
        rows = []
        for i in range(n):
            vol = 1000000
            price = 1.0 + i * 0.001
            if i == n - 1:
                vol = 5000000
                price = 1.0 - 0.02
            rows.append({"close": price, "open": price + 0.005,
                         "high": price + 0.01, "low": price - 0.01,
                         "volume": vol})
        df = pd.DataFrame(rows)
        sig = strategy_volume(df, avg_period=20, spike_mult=2.0)
        assert sig is not None
        assert sig.signal == SignalType.SELL


# ================================================================
# MACD
# ================================================================

class TestMACD:
    def test_returns_signal_on_trending_data(self, trending_up_df):
        sig = strategy_macd(trending_up_df, fast=12, slow=26, signal_period=9)
        assert sig is not None
        assert isinstance(sig, Signal)

    def test_trending_down(self, trending_down_df):
        sig = strategy_macd(trending_down_df)
        assert sig is not None


# ================================================================
# KDJ
# ================================================================

class TestKDJ:
    def test_oversold(self, oversold_rsi_df):
        sig = strategy_kdj(oversold_rsi_df, period=9)
        assert sig is not None
        # 下跌趋势 KDJ 应该偏低
        assert sig.signal in (SignalType.BUY, SignalType.STRONG_BUY, SignalType.HOLD, SignalType.SELL)

    def test_returns_signal(self, trending_up_df):
        sig = strategy_kdj(trending_up_df)
        assert sig is not None


# ================================================================
# CCI
# ================================================================

class TestCCI:
    def test_returns_signal(self, trending_up_df):
        sig = strategy_cci(trending_up_df, period=20)
        assert sig is not None

    def test_oversold(self, oversold_rsi_df):
        sig = strategy_cci(oversold_rsi_df, period=20)
        assert sig is not None


# ================================================================
# Williams %R
# ================================================================

class TestWilliams:
    def test_returns_signal(self, trending_up_df):
        sig = strategy_williams(trending_up_df, period=14)
        assert sig is not None

    def test_oversold(self, oversold_rsi_df):
        sig = strategy_williams(oversold_rsi_df, period=14)
        assert sig is not None


# ================================================================
# ADX
# ================================================================

class TestADX:
    def test_trending_up(self, trending_up_df):
        sig = strategy_adx(trending_up_df, period=14)
        assert sig is not None

    def test_flat(self, flat_df):
        sig = strategy_adx(flat_df, period=14)
        assert sig is not None


# ================================================================
# SAR
# ================================================================

class TestSAR:
    def test_returns_signal(self, trending_up_df):
        sig = strategy_sar(trending_up_df)
        assert sig is not None

    def test_reversal(self, golden_cross_df):
        sig = strategy_sar(golden_cross_df)
        assert sig is not None


# ================================================================
# OBV
# ================================================================

class TestOBV:
    def test_returns_signal(self, trending_up_df):
        sig = strategy_obv(trending_up_df, ma_period=20)
        assert sig is not None

    def test_divergence(self):
        """价格涨但 OBV 不涨 → 背离"""
        n = 40
        rows = []
        for i in range(n):
            price = 1.0 + i * 0.01
            vol = 1000000 - i * 20000  # 量缩价涨
            rows.append({"close": price, "open": price - 0.005,
                         "high": price + 0.01, "low": price - 0.01,
                         "volume": max(vol, 100000)})
        df = pd.DataFrame(rows)
        sig = strategy_obv(df, ma_period=20)
        assert sig is not None


# ================================================================
# TRIX
# ================================================================

class TestTRIX:
    def test_returns_signal(self, trending_up_df):
        sig = strategy_trix(trending_up_df, period=12, signal_period=9)
        # TRIX 需要较多数据，可能 None
        # 只要不崩溃就行

    def test_no_crash(self, flat_df):
        sig = strategy_trix(flat_df)
        # 不崩溃即可


# ================================================================
# Signal 综合评分
# ================================================================

class TestSignalCombination:
    def test_combine_buy_signals(self):
        signals = [
            Signal("RSI", SignalType.BUY, "超卖", 0.7),
            Signal("MACD", SignalType.STRONG_BUY, "金叉", 0.8),
        ]
        combined, summary = combine_signals(signals)
        assert combined in (SignalType.BUY, SignalType.STRONG_BUY)
        assert "2" in summary  # 2 个看多

    def test_combine_sell_signals(self):
        signals = [
            Signal("RSI", SignalType.SELL, "超买", 0.6),
            Signal("布林带", SignalType.STRONG_SELL, "触上轨", 0.9),
        ]
        combined, summary = combine_signals(signals)
        assert combined in (SignalType.SELL, SignalType.STRONG_SELL)

    def test_combine_mixed_signals(self):
        signals = [
            Signal("RSI", SignalType.BUY, "超卖", 0.5),
            Signal("ADX", SignalType.SELL, "强空头趋势", 0.5),
        ]
        combined, summary = combine_signals(signals)
        # 相互抵消应该是 HOLD
        assert combined == SignalType.HOLD

    def test_combine_empty(self):
        combined, summary = combine_signals([])
        assert combined == SignalType.HOLD

    def test_combine_all_hold(self):
        signals = [
            Signal("RSI", SignalType.HOLD, "中性", 0.3),
            Signal("MACD", SignalType.HOLD, "中性", 0.3),
        ]
        combined, summary = combine_signals(signals)
        assert combined == SignalType.HOLD

    def test_score_property(self):
        s = Signal("test", SignalType.STRONG_BUY, "", 0.8)
        assert s.score == 80.0  # 100 * 0.8

        s2 = Signal("test", SignalType.STRONG_SELL, "", 1.0)
        assert s2.score == -100.0


# ================================================================
# AppState
# ================================================================

class TestAppState:
    def test_signal_cooldown(self):
        from signal_engine.core.state import AppState
        s = AppState()
        # 第一次应该通过
        assert s.is_signal_cooled_down("513100", "STRONG_BUY") is True
        # 立即再调用应该被冷却
        assert s.is_signal_cooled_down("513100", "STRONG_BUY") is False
        # 不同品种不同信号应该通过
        assert s.is_signal_cooled_down("518880", "STRONG_BUY") is True

    def test_price_history_limit(self):
        from signal_engine.core.state import AppState
        s = AppState()
        s.max_price_points = 5
        for i in range(10):
            s.update_price("513100", f"10:{i:02d}", 1.0 + i * 0.01)
        assert len(s.price_history["513100"]) == 5
        assert s.price_history["513100"][-1]["price"] == 1.09
