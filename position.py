"""
持仓管理 + 操作建议
"""
from dataclasses import dataclass
from strategies import SignalType, Signal, combine_signals


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
) -> str:
    """
    结合持仓 + 信号, 给出具体操作建议
    """
    has_position = pos is not None and pos.shares > 0

    if not has_position:
        # 没有持仓
        if combined_signal in (SignalType.STRONG_BUY, SignalType.BUY):
            return f"💡 建议: 可考虑建仓, 当前无持仓, 信号偏多"
        else:
            return f"💤 建议: 暂不建仓, 继续观察"

    # 有持仓
    pnl = calc_pnl(pos, current_price)
    pnl_pct = pnl["pnl_pct"]

    # 盈利较多 + 卖出信号 → 减仓
    if pnl_pct > 5 and combined_signal in (SignalType.SELL, SignalType.STRONG_SELL):
        return f"🔔 建议: 盈利 {pnl_pct:+.1f}% + 卖出信号 → 可考虑减仓止盈"

    # 盈利 + 强卖出 → 减仓
    if pnl_pct > 0 and combined_signal == SignalType.STRONG_SELL:
        return f"🔔 建议: 盈利 {pnl_pct:+.1f}% + 强烈卖出信号 → 建议减仓"

    # 亏损较多 + 买入信号 → 加仓摊薄
    if pnl_pct < -3 and combined_signal in (SignalType.STRONG_BUY, SignalType.BUY):
        return f"💡 建议: 浮亏 {pnl_pct:+.1f}% + 买入信号 → 可考虑小幅加仓摊薄成本"

    # 亏损较多 + 卖出信号 → 止损
    if pnl_pct < -5 and combined_signal in (SignalType.SELL, SignalType.STRONG_SELL):
        return f"🚨 建议: 浮亏 {pnl_pct:+.1f}% + 卖出信号 → 考虑止损, 控制风险"

    # 亏损 + 无明显信号 → 持有观望
    if pnl_pct < 0 and combined_signal == SignalType.HOLD:
        return f"⏳ 建议: 浮亏 {pnl_pct:+.1f}%, 信号不明 → 继续持有观望"

    # 盈利 + 买入信号 → 持有或加仓
    if pnl_pct > 0 and combined_signal in (SignalType.BUY, SignalType.STRONG_BUY):
        return f"✅ 建议: 盈利 {pnl_pct:+.1f}% + 看多信号 → 继续持有"

    return f"📋 建议: 维持现状, 浮亏 {pnl_pct:+.1f}%"
