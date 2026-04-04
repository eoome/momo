"""
实盘交易记录管理
"""
import json
import os
from dataclasses import dataclass

from signal_engine.config import DATA_DIR

TRADES_FILE = os.path.join(DATA_DIR, "trades.json")

# 默认手续费率 (双边)
DEFAULT_COMMISSION_RATE = 0.0003  # 万三


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_trades() -> list[dict]:
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_trades(trades: list[dict]):
    _ensure_dir()
    with open(TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


def calc_commission(price: float, shares: int, rate: float = DEFAULT_COMMISSION_RATE) -> float:
    return round(price * shares * rate, 2)


def calc_trade_pnl(buy_price: float, sell_price: float, shares: int,
                    commission_buy: float, commission_sell: float) -> tuple[float, float]:
    if buy_price <= 0 or shares <= 0:
        return 0.0, 0.0
    gross = (sell_price - buy_price) * shares
    net = gross - commission_buy - commission_sell
    cost = buy_price * shares + commission_buy
    pnl_pct = (net / cost * 100) if cost > 0 else 0.0
    return round(net, 2), round(pnl_pct, 2)


def recalc_trades(trades: list[dict]) -> list[dict]:
    cumulative = 0.0
    sorted_trades = sorted(trades, key=lambda t: (t.get("date", ""), t.get("id", 0)))
    open_positions: dict[str, list] = {}

    for t in sorted_trades:
        direction = t.get("direction", "")
        code = t.get("code", "")
        buy_price = float(t.get("buy_price", 0))
        sell_price = float(t.get("sell_price", 0))
        shares = int(t.get("shares", 0))

        if direction == "买":
            commission = calc_commission(buy_price, shares)
            t["commission"] = commission
            t["pnl"] = 0
            t["pnl_pct"] = 0
            open_positions.setdefault(code, []).append([buy_price, shares, commission])

        elif direction == "卖":
            commission_sell = calc_commission(sell_price, shares)
            positions = open_positions.get(code, [])
            remaining = shares
            total_cost = 0.0
            total_buy_commission = 0.0
            matched_shares = 0

            while remaining > 0 and positions:
                bp, bp_shares, bp_comm = positions[0]
                if bp_shares <= remaining:
                    total_cost += bp * bp_shares
                    total_buy_commission += bp_comm
                    matched_shares += bp_shares
                    remaining -= bp_shares
                    positions.pop(0)
                else:
                    total_cost += bp * remaining
                    total_buy_commission += bp_comm * (remaining / bp_shares)
                    matched_shares += remaining
                    positions[0][1] -= remaining
                    remaining = 0

            if matched_shares > 0:
                avg_buy_price = total_cost / matched_shares
                t["commission"] = round(commission_sell + total_buy_commission, 2)
                pnl, pnl_pct = calc_trade_pnl(
                    avg_buy_price, sell_price, matched_shares,
                    total_buy_commission, commission_sell
                )
                if remaining > 0:
                    t["note"] = t.get("note", "") + f" [警告: {remaining}股无对应买入记录]"
            else:
                t["commission"] = round(commission_sell + calc_commission(buy_price, shares), 2)
                pnl, pnl_pct = calc_trade_pnl(buy_price, sell_price, shares,
                    calc_commission(buy_price, shares), commission_sell)

            t["pnl"] = pnl
            t["pnl_pct"] = pnl_pct
        else:
            t.setdefault("commission", 0)
            t.setdefault("pnl", 0)
            t.setdefault("pnl_pct", 0)

        cumulative += t.get("pnl", 0)
        t["cumulative_pnl"] = round(cumulative, 2)

    return sorted_trades


def add_trade(date: str, code: str, name: str, direction: str,
              buy_price: float, sell_price: float, shares: int,
              note: str = "") -> dict:
    trades = load_trades()
    max_id = max((t.get("id", 0) for t in trades), default=0)

    new_trade = {
        "id": max_id + 1,
        "date": date,
        "code": code,
        "name": name,
        "direction": direction,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "shares": shares,
        "commission": 0,
        "pnl": 0,
        "pnl_pct": 0,
        "cumulative_pnl": 0,
        "note": note,
    }

    trades.append(new_trade)
    trades = recalc_trades(trades)
    save_trades(trades)
    return new_trade


def delete_trade(trade_id: int) -> bool:
    trades = load_trades()
    original_len = len(trades)
    trades = [t for t in trades if t.get("id") != trade_id]
    if len(trades) == original_len:
        return False
    trades = recalc_trades(trades)
    save_trades(trades)
    return True


def update_trade(trade_id: int, updates: dict) -> dict | None:
    trades = load_trades()
    for t in trades:
        if t.get("id") == trade_id:
            t.update(updates)
            trades = recalc_trades(trades)
            save_trades(trades)
            return t
    return None


def get_trade_summary() -> dict:
    trades = load_trades()
    if not trades:
        return {
            "total_trades": 0,
            "total_pnl": 0,
            "win_count": 0,
            "lose_count": 0,
            "win_rate": 0,
        }

    sell_trades = [t for t in trades if t.get("direction") == "卖" and t.get("pnl", 0) != 0]
    wins = [t for t in sell_trades if t["pnl"] > 0]
    loses = [t for t in sell_trades if t["pnl"] < 0]

    return {
        "total_trades": len(sell_trades),
        "total_pnl": round(sum(t["pnl"] for t in sell_trades), 2),
        "win_count": len(wins),
        "lose_count": len(loses),
        "win_rate": round(len(wins) / len(sell_trades) * 100, 1) if sell_trades else 0,
    }
