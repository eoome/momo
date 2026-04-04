"""
回测引擎 - 用历史数据验证策略表现
"""
import pandas as pd
import numpy as np

from signal_engine.core.strategies import STRATEGY_FNS
from signal_engine.core.signal import Signal, SignalType


# 各策略所需的最小K线数
_STRATEGY_MIN_BARS = {
    "dual_ma": 25,
    "rsi": 20,
    "bollinger": 25,
    "momentum": 20,
    "volume_anomaly": 25,
    "macd": 40,
    "kdj": 15,
    "cci": 25,
    "williams": 19,
    "adx": 35,
    "sar": 15,
    "obv": 25,
    "trix": 50,
    "hl_cross": 6,
}
_DEFAULT_MIN_BARS = 50


def run_backtest(
    df: pd.DataFrame,
    strategy_fn,
    strategy_kwargs: dict = None,
    initial_capital: float = 100000,
    commission_rate: float = 0.0003,
    slippage_pct: float = 0.001,
) -> dict:
    if strategy_kwargs is None:
        strategy_kwargs = {}

    if len(df) < 30:
        return _empty_result("数据不足(至少30根K线)")

    trades = []
    position = 0
    entry_price = 0.0
    entry_date = ""
    capital = initial_capital
    shares = 0
    equity_curve = []

    # 从 STRATEGY_FNS 反查 key
    strategy_key = None
    for k, v in STRATEGY_FNS.items():
        if v is strategy_fn:
            strategy_key = k
            break
    min_bars = _STRATEGY_MIN_BARS.get(strategy_key, _DEFAULT_MIN_BARS)

    for i in range(min_bars, len(df) - 1):
        sub_df = df.iloc[:i].copy()
        exec_bar = df.iloc[i]
        exec_price = float(exec_bar["open"])
        date_str = str(exec_bar.get("date", exec_bar.get("datetime", i)))

        try:
            sig = strategy_fn(sub_df, **strategy_kwargs)
        except Exception:
            sig = None

        if sig is not None:
            if sig.signal in (SignalType.BUY, SignalType.STRONG_BUY) and position == 0:
                buy_price = exec_price * (1 + slippage_pct)
                shares = int(capital * 0.95 / buy_price)
                if shares > 0:
                    cost = shares * buy_price * (1 + commission_rate)
                    capital -= cost
                    position = 1
                    entry_price = buy_price
                    entry_date = date_str

            elif sig.signal in (SignalType.SELL, SignalType.STRONG_SELL) and position == 1:
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

        close_price = float(exec_bar["close"])
        total_equity = capital + (shares * close_price if position == 1 else 0)
        equity_curve.append({"date": date_str, "equity": round(total_equity, 2)})

    if position == 1:
        final_price = float(df.iloc[-1]["close"])
        final_date = str(df.iloc[-1].get("date", ""))
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

    peak = equity_curve[0]["equity"] if equity_curve else initial_capital
    max_dd = 0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = (peak - pt["equity"]) / peak * 100
        if dd > max_dd:
            max_dd = dd

    if equity_curve:
        n_days = len(equity_curve)
        final_eq = equity_curve[-1]["equity"]
        ann_return = ((final_eq / initial_capital) ** (252 / max(n_days, 1)) - 1) * 100
    else:
        ann_return = 0

    if len(pnl_pcts) > 1:
        sharpe = (np.mean(pnl_pcts) / np.std(pnl_pcts)) if np.std(pnl_pcts) > 0 else 0
    else:
        sharpe = 0

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
        "trades": trades[-20:],
        "equity_curve": equity_curve[::max(1, len(equity_curve)//100)],
    }
