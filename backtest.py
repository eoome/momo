"""
回测引擎 - 用历史数据验证策略表现
"""
import pandas as pd
import numpy as np
from strategies import (
    strategy_dual_ma, strategy_rsi, strategy_bollinger,
    strategy_momentum, strategy_volume, strategy_macd, strategy_kdj,
    Signal, SignalType, combine_signals,
)


def run_backtest(
    df: pd.DataFrame,
    strategy_fn,
    strategy_kwargs: dict = None,
    initial_capital: float = 100000,
    commission_rate: float = 0.0003,
    slippage_pct: float = 0.001,
) -> dict:
    """
    回测单个策略

    Parameters:
        df: OHLCV DataFrame (date, open, high, low, close, volume)
        strategy_fn: 策略函数
        strategy_kwargs: 策略参数
        initial_capital: 初始资金
        commission_rate: 手续费率 (双边)
        slippage_pct: 滑点

    Returns:
        回测结果 dict
    """
    if strategy_kwargs is None:
        strategy_kwargs = {}

    if len(df) < 30:
        return _empty_result("数据不足(至少30根K线)")

    trades = []
    position = 0  # 0=空仓, 1=持仓
    entry_price = 0.0
    entry_date = ""
    capital = initial_capital
    shares = 0
    equity_curve = []

    min_bars = 30  # 前面跳过的K线数(确保指标计算有足够数据)

    for i in range(min_bars, len(df) - 1):
        # 用截至第 i-1 根K线的数据计算信号 (避免前视偏差)
        sub_df = df.iloc[:i].copy()
        # 执行价格: 第 i 根K线的开盘价 (模拟次日开盘执行)
        exec_bar = df.iloc[i]
        exec_price = float(exec_bar["open"])
        date_str = str(exec_bar.get("date", exec_bar.get("datetime", i)))

        # 运行策略
        try:
            sig = strategy_fn(sub_df, **strategy_kwargs)
        except Exception:
            sig = None

        # 交易逻辑
        if sig is not None:
            if sig.signal in (SignalType.BUY, SignalType.STRONG_BUY) and position == 0:
                # 买入: 次日开盘 + 滑点
                buy_price = exec_price * (1 + slippage_pct)
                shares = int(capital * 0.95 / buy_price)  # 留 5% 现金
                if shares > 0:
                    cost = shares * buy_price * (1 + commission_rate)
                    capital -= cost
                    position = 1
                    entry_price = buy_price
                    entry_date = date_str

            elif sig.signal in (SignalType.SELL, SignalType.STRONG_SELL) and position == 1:
                # 卖出: 次日开盘 - 滑点
                sell_price = exec_price * (1 - slippage_pct)
                revenue = shares * sell_price * (1 - commission_rate)
                pnl = revenue - shares * entry_price

                trades.append({
                    "entry_date": entry_date,
                    "exit_date": date_str,
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(sell_price, 4),
                    "shares": shares,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((sell_price - entry_price) / entry_price * 100, 2),
                })

                capital += revenue
                position = 0
                shares = 0

        # 记录权益曲线 (用当日收盘价计算未平仓市值)
        close_price = float(exec_bar["close"])
        total_equity = capital + (shares * close_price if position == 1 else 0)
        equity_curve.append({"date": date_str, "equity": round(total_equity, 2)})

    # 如果最后还持仓, 按最后K线收盘价平仓 (无信号触发平仓的兜底)
    if position == 1:
        final_price = float(df.iloc[-1]["close"])
        final_date = str(df.iloc[-1].get("date", ""))
        # 记录最后一根K线的权益
        equity_curve.append({"date": final_date, "equity": round(capital + shares * final_price, 2)})
        sell_price = final_price * (1 - slippage_pct)
        revenue = shares * sell_price * (1 - commission_rate)
        pnl = revenue - shares * entry_price
        trades.append({
            "entry_date": entry_date,
            "exit_date": final_date,
            "entry_price": round(entry_price, 4),
            "exit_price": round(sell_price, 4),
            "shares": shares,
            "pnl": round(pnl, 2),
            "pnl_pct": round((sell_price - entry_price) / entry_price * 100, 2),
        })
        capital += revenue
        position = 0

    return _calc_metrics(trades, equity_curve, initial_capital)


def _empty_result(reason: str) -> dict:
    return {
        "total_trades": 0, "win_trades": 0, "lose_trades": 0,
        "win_rate": 0, "total_return_pct": 0, "max_drawdown_pct": 0,
        "avg_pnl_pct": 0, "avg_win_pct": 0, "avg_lose_pct": 0,
        "profit_factor": 0, "sharpe_ratio": 0, "final_equity": 0,
        "trades": [], "equity_curve": [], "reason": reason,
    }


def _calc_metrics(trades: list, equity_curve: list, initial_capital: float) -> dict:
    if not trades:
        return _empty_result("无交易产生")

    pnls = [t["pnl"] for t in trades]
    pnl_pcts = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p > 0]
    loses = [p for p in pnls if p <= 0]

    total_return = (equity_curve[-1]["equity"] - initial_capital) / initial_capital * 100 if equity_curve else 0

    # 最大回撤
    peak = equity_curve[0]["equity"] if equity_curve else initial_capital
    max_dd = 0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = (peak - pt["equity"]) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # 年化收益 (按交易日)
    if equity_curve:
        n_days = len(equity_curve)
        final_eq = equity_curve[-1]["equity"]
        ann_return = ((final_eq / initial_capital) ** (252 / max(n_days, 1)) - 1) * 100
    else:
        ann_return = 0

    # 夏普比率 (简化)
    if len(pnl_pcts) > 1:
        sharpe = (np.mean(pnl_pcts) / np.std(pnl_pcts)) if np.std(pnl_pcts) > 0 else 0
    else:
        sharpe = 0

    # 盈亏比
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(loses)) if loses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return {
        "total_trades": len(trades),
        "win_trades": len(wins),
        "lose_trades": len(loses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "total_return_pct": round(total_return, 2),
        "ann_return_pct": round(ann_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_pnl_pct": round(np.mean(pnl_pcts), 2),
        "avg_win_pct": round(np.mean([p for p in pnl_pcts if p > 0]), 2) if wins else 0,
        "avg_lose_pct": round(np.mean([p for p in pnl_pcts if p <= 0]), 2) if loses else 0,
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "final_equity": round(equity_curve[-1]["equity"], 2) if equity_curve else initial_capital,
        "trades": trades[-20:],  # 只返回最近20笔交易
        "equity_curve": equity_curve[::max(1, len(equity_curve)//100)],  # 最多100个点
    }
