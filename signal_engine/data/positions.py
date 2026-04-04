"""
持仓管理 + 操作建议
"""
from dataclasses import dataclass

from signal_engine.core.signal import SignalType, Signal


@dataclass
class Position:
    code: str
    cost: float       # 成本价
    shares: int       # 持仓数量
    note: str = ""


def load_positions(positions_cfg: dict) -> dict[str, Position]:
    """从配置加载持仓"""
    result = {}
    for code, info in positions_cfg.items():
        result[code] = Position(
            code=code,
            cost=info.get("cost", 0),
            shares=info.get("shares", 0),
            note=info.get("note", ""),
        )
    return result


def calc_pnl(pos: Position, current_price: float) -> dict:
    """计算盈亏"""
    if pos.cost == 0 or pos.shares == 0:
        return {"pnl": 0, "pnl_pct": 0, "market_value": 0}
    pnl = (current_price - pos.cost) * pos.shares
    pnl_pct = (current_price - pos.cost) / pos.cost * 100
    market_value = current_price * pos.shares
    return {
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "market_value": round(market_value, 2),
    }


def suggest_action(
    code: str,
    current_price: float,
    pos: Position | None,
    combined_signal: SignalType,
    signals: list[Signal],
    is_t0: bool = False,
) -> str:
    """
    结合持仓 + 信号 + T0/T1 类型, 给出具体操作建议
    """
    has_position = pos is not None and pos.shares > 0

    if not has_position:
        if combined_signal in (SignalType.STRONG_BUY, SignalType.BUY):
            return f"💡 建议: 可考虑建仓, 当前无持仓, 信号偏多"
        else:
            return f"💤 建议: 暂不建仓, 继续观察"

    pnl = calc_pnl(pos, current_price)
    pnl_pct = pnl["pnl_pct"]

    if is_t0:
        take_profit_hi = 1.5
        take_profit_lo = 0.5
        stop_loss_warn = -1.0
        stop_loss_hard = -2.0
        add_position_thresh = -0.5
    else:
        take_profit_hi = 5.0
        take_profit_lo = 0.0
        stop_loss_warn = -3.0
        stop_loss_hard = -5.0
        add_position_thresh = -3.0

    if pnl_pct > take_profit_hi and combined_signal in (SignalType.SELL, SignalType.STRONG_SELL):
        return f"🔔 建议: 盈利 {pnl_pct:+.1f}% + 卖出信号 → 可考虑减仓止盈"

    if pnl_pct > take_profit_lo and combined_signal == SignalType.STRONG_SELL:
        return f"🔔 建议: 盈利 {pnl_pct:+.1f}% + 强烈卖出信号 → 建议减仓"

    if pnl_pct < add_position_thresh and combined_signal in (SignalType.STRONG_BUY, SignalType.BUY):
        return f"💡 建议: 浮亏 {pnl_pct:+.1f}% + 买入信号 → 可考虑小幅加仓摊薄成本"

    if pnl_pct < stop_loss_warn and combined_signal in (SignalType.SELL, SignalType.STRONG_SELL):
        return f"🚨 建议: 浮亏 {pnl_pct:+.1f}% + 卖出信号 → 考虑止损, 控制风险"

    if pnl_pct < stop_loss_hard and combined_signal == SignalType.HOLD:
        return f"🚨 建议: 浮亏 {pnl_pct:+.1f}%, 已超止损线 → 建议考虑止损"

    if pnl_pct < 0 and combined_signal == SignalType.HOLD:
        return f"⏳ 建议: 浮亏 {pnl_pct:+.1f}%, 信号不明 → 继续持有观望"

    if pnl_pct > 0 and combined_signal in (SignalType.BUY, SignalType.STRONG_BUY):
        return f"✅ 建议: 盈利 {pnl_pct:+.1f}% + 看多信号 → 继续持有"

    return f"📋 建议: 维持现状, 浮亏 {pnl_pct:+.1f}%"
