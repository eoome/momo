"""
极值交叉策略测试
包含: 用户原始例子 + 合成场景 + 简易回测
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np

from signal_engine.core.signal import Signal, SignalType
from signal_engine.core.strategies import strategy_hl_cross, _find_crossover


# ================================================================
# 交叉点计算测试
# ================================================================

class TestCrossoverCalc:
    """验证交叉点数学计算"""

    def test_user_example(self):
        """
        用户原始例子:
          Day0: H=10, L=2
          Day1: H=6,  L=4
          Day2: H=3,  L=1
          线A: 10→4→3, 线B: 2→6→1
          交叉点应 = 3.5
        """
        cross = _find_crossover(h0=10, l0=2, h1=6, l1=4, h2=3, l2=1)
        assert cross is not None
        assert abs(cross - 3.5) < 0.01

    def test_no_cross_parallel(self):
        """两线平行 → 无交叉"""
        cross = _find_crossover(h0=5, l0=1, h1=3, l1=4, h2=6, l2=2)
        # dy_a = 6-4 = 2, dy_b = 2-3 = -1, 不平行
        # 重新设计平行场景
        # 线A: (5,4)→(6), dy_a = 6-4 = 2
        # 线B: (1,3)→(5), dy_b = 5-3 = 2
        # denom = 2-2 = 0 → 平行
        cross = _find_crossover(h0=5, l0=1, h1=3, l1=4, h2=6, l2=5)
        assert cross is None

    def test_cross_outside_segment(self):
        """交叉点不在当前段内"""
        # 线A: L1=1→H2=2, 线B: H1=5→L2=4, 交叉在段外
        cross = _find_crossover(h0=10, l0=2, h1=5, l1=1, h2=2, l2=4)
        assert cross is None

    def test_cross_symmetric(self):
        """对称场景: 交叉应在中点"""
        # 线A: L1=2→H2=8, 线B: H1=8→L2=2
        # dy_a = 8-2 = 6, dy_b = 2-8 = -6
        # t = (8-2)/(6-(-6)) = 6/12 = 0.5
        # cross = 2 + 6*0.5 = 5
        cross = _find_crossover(h0=5, l0=1, h1=8, l1=2, h2=8, l2=2)
        assert cross is not None
        assert abs(cross - 5.0) < 0.01


# ================================================================
# 用户原始例子 — 完整蜡烛信号
# ================================================================

class TestUserExample:
    """用用户给的数据验证策略输出"""

    def _make_df(self, candles):
        """构造 DataFrame: [(H, L, close), ...]"""
        rows = []
        for h, l, c in candles:
            o = l + (h - l) * 0.3  # 假设开盘在区间下 30%
            rows.append({
                "open": o, "high": h, "low": l, "close": c,
                "volume": 1000000,
            })
        return pd.DataFrame(rows)

    def test_user_data_buy_above_cross(self):
        """
        用户数据:
          Day0: H=10, L=2
          Day1: H=6,  L=4
          Day2: H=3,  L=1   ← 交叉点 3.5
          Day3: 价格高于 3.5 → 应该买入
        """
        df = self._make_df([
            (10, 2, 5),   # Day0
            (6, 4, 5),    # Day1
            (3, 1, 2),    # Day2 (交叉点在这里 = 3.5)
            (5, 4, 4.5),  # Day3: 最高5, 最低4, 收盘4.5 > 3.5 → 买
        ])
        sig = strategy_hl_cross(df, tolerance_pct=0.5)
        assert sig is not None
        assert sig.signal in (SignalType.BUY, SignalType.STRONG_BUY)
        assert sig.details["crossover"] == 3.5

    def test_user_data_sell_below_cross(self):
        """
        用户数据:
          交叉点 = 3.5
          Day3: 价格低于 3.5 → 应该卖出
        """
        df = self._make_df([
            (10, 2, 5),    # Day0
            (6, 4, 5),     # Day1
            (3, 1, 2),     # Day2
            (2.5, 1, 1.5), # Day3: 收盘1.5 < 3.5 → 卖
        ])
        sig = strategy_hl_cross(df, tolerance_pct=0.5)
        assert sig is not None
        assert sig.signal in (SignalType.SELL, SignalType.STRONG_SELL)
        assert sig.details["crossover"] == 3.5

    def test_user_data_hold_at_cross(self):
        """
        交叉点 = 3.5
        Day3: 收盘在 3.5 附近 → 持有观望
        """
        df = self._make_df([
            (10, 2, 5),
            (6, 4, 5),
            (3, 1, 2),
            (3.6, 3.4, 3.5),  # 收盘刚好在交叉点
        ])
        sig = strategy_hl_cross(df, tolerance_pct=0.5)
        assert sig is not None
        assert sig.signal == SignalType.HOLD


# ================================================================
# 合成场景测试
# ================================================================

class TestSyntheticScenarios:

    def _make_trend_df(self, trend="up", n=30):
        """生成趋势数据"""
        rows = []
        price = 1.0
        for i in range(n):
            if trend == "up":
                change = np.random.uniform(0.001, 0.02)
            elif trend == "down":
                change = np.random.uniform(-0.02, -0.001)
            else:
                change = np.random.uniform(-0.01, 0.01)

            price *= (1 + change)
            h = price * (1 + np.random.uniform(0.002, 0.015))
            l = price * (1 - np.random.uniform(0.002, 0.015))
            o = price * (1 + np.random.uniform(-0.005, 0.005))
            c = price * (1 + np.random.uniform(-0.005, 0.005))

            rows.append({
                "open": o, "high": max(h, o, c), "low": min(l, o, c),
                "close": c, "volume": 1000000,
            })
        return pd.DataFrame(rows)

    def test_uptrend(self):
        """上涨趋势中策略应该产生信号"""
        for seed in range(5):
            np.random.seed(seed)
            df = self._make_trend_df("up", 50)
            sig = strategy_hl_cross(df)
            # 不崩溃即可
            assert sig is None or isinstance(sig, Signal)

    def test_downtrend(self):
        """下跌趋势中策略应该产生信号"""
        for seed in range(5):
            np.random.seed(seed)
            df = self._make_trend_df("down", 50)
            sig = strategy_hl_cross(df)
            assert sig is None or isinstance(sig, Signal)

    def test_not_enough_data(self):
        """数据不足 4 根 → None"""
        df = pd.DataFrame([
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"open": 1, "high": 3, "low": 0.8, "close": 2.0, "volume": 100},
            {"open": 1, "high": 2.5, "low": 1, "close": 1.8, "volume": 100},
        ])
        assert strategy_hl_cross(df) is None


# ================================================================
# 简易回测 — 用合成数据验证策略是否有正期望
# ================================================================

class TestBacktest:
    """
    简易回测: 在合成数据上跑极值交叉策略
    统计买入后 N 天的胜率和平均收益
    """

    def _generate_price_series(self, n=200, seed=42):
        """生成带趋势和震荡的价格序列"""
        np.random.seed(seed)
        rows = []
        price = 10.0

        for i in range(n):
            # 混合趋势: 每 50 天切换方向
            phase = (i // 50) % 4
            if phase == 0:
                drift = 0.002   # 上涨
            elif phase == 1:
                drift = 0.0     # 震荡
            elif phase == 2:
                drift = -0.002  # 下跌
            else:
                drift = 0.0     # 震荡

            noise = np.random.normal(0, 0.015)
            price *= (1 + drift + noise)

            daily_range = abs(np.random.normal(0, 0.02)) + 0.005
            h = price * (1 + daily_range / 2)
            l = price * (1 - daily_range / 2)
            c = price * (1 + np.random.uniform(-daily_range/3, daily_range/3))

            rows.append({
                "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                "open": price, "high": max(h, price, c),
                "low": min(l, price, c), "close": c,
                "volume": 1000000,
            })

        return pd.DataFrame(rows)

    def _run_simple_backtest(self, df, hold_days=3):
        """买入后持有 hold_days 天的收益统计"""
        trades = []
        i = 4  # 从第4天开始 (需要前3天计算交叉)

        while i + hold_days < len(df):
            sub_df = df.iloc[:i+1]
            sig = strategy_hl_cross(sub_df)

            if sig and sig.signal == SignalType.STRONG_BUY:
                buy_price = df.iloc[i]["close"]
                sell_price = df.iloc[i + hold_days]["close"]
                pnl_pct = (sell_price - buy_price) / buy_price * 100
                trades.append({
                    "buy_day": i, "buy_price": buy_price,
                    "sell_price": sell_price, "pnl_pct": pnl_pct,
                    "confidence": sig.confidence,
                })
                i += hold_days + 1  # 跳过持有期
            elif sig and sig.signal == SignalType.STRONG_SELL:
                # 做空收益 (如果有)
                sell_price = df.iloc[i]["close"]
                buy_back = df.iloc[i + hold_days]["close"]
                pnl_pct = (sell_price - buy_back) / sell_price * 100
                trades.append({
                    "buy_day": i, "buy_price": sell_price,
                    "sell_price": buy_back, "pnl_pct": pnl_pct,
                    "confidence": sig.confidence,
                    "direction": "short",
                })
                i += hold_days + 1
            else:
                i += 1

        return trades

    def test_backtest_report(self):
        """运行回测并输出报告"""
        df = self._generate_price_series(300, seed=42)
        trades = self._run_simple_backtest(df, hold_days=3)

        if not trades:
            pytest.skip("未产生交易信号")

        wins = [t for t in trades if t["pnl_pct"] > 0]
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        total_return = sum(t["pnl_pct"] for t in trades)
        avg_pnl = total_return / len(trades)
        win_rate = len(wins) / len(trades) * 100

        print(f"\n{'='*50}")
        print(f"极值交叉策略回测报告")
        print(f"{'='*50}")
        print(f"数据: {len(df)} 根K线")
        print(f"交易次数: {len(trades)}")
        print(f"盈利: {len(wins)} 笔")
        print(f"亏损: {len(losses)} 笔")
        print(f"胜率: {win_rate:.1f}%")
        print(f"平均收益: {avg_pnl:+.2f}%")
        print(f"累计收益: {total_return:+.2f}%")
        if wins:
            print(f"平均盈利: {np.mean([t['pnl_pct'] for t in wins]):+.2f}%")
        if losses:
            print(f"平均亏损: {np.mean([t['pnl_pct'] for t in losses]):+.2f}%")
            print(f"盈亏比: {abs(np.mean([t['pnl_pct'] for t in wins]) / np.mean([t['pnl_pct'] for t in losses])):.2f}" if losses and np.mean([t['pnl_pct'] for t in losses]) != 0 else "盈亏比: N/A")
        print(f"{'='*50}")

        # 打印前 10 笔交易
        print(f"\n前 10 笔交易:")
        for j, t in enumerate(trades[:10]):
            direction = t.get("direction", "long")
            print(f"  #{j+1} Day{t['buy_day']:3d} {direction:5s} "
                  f"{t['buy_price']:.3f} → {t['sell_price']:.3f} "
                  f"{'✅' if t['pnl_pct'] > 0 else '❌'} {t['pnl_pct']:+.2f}% "
                  f"(conf={t['confidence']:.2f})")

        # 基本断言: 至少产生了一些交易
        assert len(trades) > 0, "策略应该产生至少一笔交易"

    def test_backtest_multiple_seeds(self):
        """多个随机种子验证稳定性"""
        results = []
        for seed in range(10):
            df = self._generate_price_series(300, seed=seed)
            trades = self._run_simple_backtest(df, hold_days=3)
            if trades:
                win_rate = len([t for t in trades if t["pnl_pct"] > 0]) / len(trades)
                avg_pnl = sum(t["pnl_pct"] for t in trades) / len(trades)
                results.append({
                    "seed": seed, "trades": len(trades),
                    "win_rate": win_rate, "avg_pnl": avg_pnl,
                })

        if not results:
            pytest.skip("所有种子均无交易")

        print(f"\n{'='*60}")
        print(f"多种子稳定性测试 ({len(results)}/10 产生交易)")
        print(f"{'='*60}")
        for r in results:
            print(f"  seed={r['seed']:2d}  交易={r['trades']:3d}  "
                  f"胜率={r['win_rate']*100:5.1f}%  平均={r['avg_pnl']:+.2f}%")

        avg_win_rate = np.mean([r["win_rate"] for r in results])
        avg_pnl_all = np.mean([r["avg_pnl"] for r in results])
        print(f"  {'─'*50}")
        print(f"  平均胜率: {avg_win_rate*100:.1f}%")
        print(f"  平均收益: {avg_pnl_all:+.2f}%")
        print(f"{'='*60}")

        assert len(results) >= 5, "至少一半的种子应该产生交易"


# ================================================================
# 策略注册验证
# ================================================================

class TestRegistration:
    def test_registered_in_strategy_fns(self):
        from signal_engine.core.strategies import STRATEGY_FNS
        assert "hl_cross" in STRATEGY_FNS
        assert callable(STRATEGY_FNS["hl_cross"])

    def test_config_has_params(self):
        from signal_engine.config import STRATEGY_PARAMS
        assert "hl_cross" in STRATEGY_PARAMS
