"""
实盘交易记录管理
用户记录实际买卖，系统自动计算手续费、盈亏、累计盈亏
"""
import json
import os
from dataclasses import dataclass, asdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TRADES_FILE = os.path.join(DATA_DIR, "trades.json")

# 默认手续费率 (双边)
DEFAULT_COMMISSION_RATE = 0.0003  # 万三


@dataclass
class Trade:
    id: int
    date: str              # 日期, 如 "2026/3/28"
    code: str              # ETF 代码
    name: str              # ETF 名称
    direction: str         # "买" 或 "卖"
    buy_price: float       # 实际买价
    sell_price: float      # 实际卖价 (买入时为 0)
    shares: int            # 实际仓位 (股数)
    commission: float      # 手续费 (自动计算)
    pnl: float             # 盈亏 (自动计算)
    pnl_pct: float         # 盈亏比 (自动计算)
    cumulative_pnl: float  # 累计盈亏
    note: str = ""         # 备注


def load_trades() -> list[dict]:
    """加载所有交易记录"""
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_trades(trades: list[dict]):
    """保存交易记录"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


def calc_commission(price: float, shares: int, rate: float = DEFAULT_COMMISSION_RATE) -> float:
    """计算单边手续费"""
    return round(price * shares * rate, 2)


def calc_trade_pnl(buy_price: float, sell_price: float, shares: int,
                    commission_buy: float, commission_sell: float) -> tuple[float, float]:
    """
    计算单笔盈亏
    返回: (盈亏金额, 盈亏百分比)
    """
    if buy_price <= 0 or shares <= 0:
        return 0.0, 0.0
    gross = (sell_price - buy_price) * shares
    net = gross - commission_buy - commission_sell
    cost = buy_price * shares + commission_buy
    pnl_pct = (net / cost * 100) if cost > 0 else 0.0
    return round(net, 2), round(pnl_pct, 2)


def recalc_trades(trades: list[dict]) -> list[dict]:
    """
    重新计算所有交易的手续费、盈亏、累计盈亏。
    买入: 只算手续费, 盈亏=0
    卖出: 匹配最近同品种的买入, 计算盈亏
    """
    cumulative = 0.0
    # 按日期+id排序
    sorted_trades = sorted(trades, key=lambda t: (t.get("date", ""), t.get("id", 0)))

    # 跟踪未平仓的买入记录: {code: [(buy_price, shares, commission_buy), ...]}
    open_positions: dict[str, list] = {}

    for t in sorted_trades:
        direction = t.get("direction", "")
        code = t.get("code", "")
        buy_price = float(t.get("buy_price", 0))
        sell_price = float(t.get("sell_price", 0))
        shares = int(t.get("shares", 0))

        if direction == "买":
            # 计算买入手续费
            commission = calc_commission(buy_price, shares)
            t["commission"] = commission
            t["pnl"] = 0
            t["pnl_pct"] = 0
            # 记录未平仓
            open_positions.setdefault(code, []).append([buy_price, shares, commission])

        elif direction == "卖":
            commission_sell = calc_commission(sell_price, shares)
            # 从最近的买入记录中匹配
            positions = open_positions.get(code, [])
            remaining = shares
            total_cost = 0.0
            total_buy_commission = 0.0

            while remaining > 0 and positions:
                bp, bp_shares, bp_comm = positions[0]
                if bp_shares <= remaining:
                    total_cost += bp * bp_shares
                    total_buy_commission += bp_comm
                    remaining -= bp_shares
                    positions.pop(0)
                else:
                    total_cost += bp * remaining
                    total_buy_commission += bp_comm * (remaining / bp_shares)
                    positions[0][1] -= remaining
                    remaining = 0

            # 卖出的手续费
            t["commission"] = round(commission_sell + total_buy_commission, 2)
            pnl, pnl_pct = calc_trade_pnl(
                total_cost / (shares - remaining) if (shares - remaining) > 0 else buy_price,
                sell_price, shares - remaining,
                total_buy_commission, commission_sell
            )
            # 如果没有匹配到买入记录，用用户填的 buy_price 直接算
            if remaining == shares:
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
    """添加一笔交易记录"""
    trades = load_trades()

    # 自增 ID
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
    """删除一笔交易记录"""
    trades = load_trades()
    original_len = len(trades)
    trades = [t for t in trades if t.get("id") != trade_id]
    if len(trades) == original_len:
        return False
    trades = recalc_trades(trades)
    save_trades(trades)
    return True


def update_trade(trade_id: int, updates: dict) -> dict | None:
    """更新一笔交易记录"""
    trades = load_trades()
    for t in trades:
        if t.get("id") == trade_id:
            t.update(updates)
            trades = recalc_trades(trades)
            save_trades(trades)
            return t
    return None


def get_trade_summary() -> dict:
    """获取交易汇总统计"""
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
