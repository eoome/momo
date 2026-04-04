"""
信号类型定义 + 综合评分
"""
from dataclasses import dataclass, field
from enum import Enum


class SignalType(Enum):
    STRONG_BUY = "🟢 强烈买入"
    BUY = "🔵 买入"
    HOLD = "⚪ 持有/观望"
    SELL = "🟡 卖出"
    STRONG_SELL = "🔴 强烈卖出"


@dataclass
class Signal:
    strategy: str               # 策略名称
    signal: SignalType          # 信号类型
    reason: str                 # 理由
    confidence: float = 0.0     # 置信度 0-1
    details: dict = field(default_factory=dict)

    @property
    def score(self) -> float:
        """信号强度评分 (-100 到 +100)"""
        mapping = {
            SignalType.STRONG_BUY: 100,
            SignalType.BUY: 50,
            SignalType.HOLD: 0,
            SignalType.SELL: -50,
            SignalType.STRONG_SELL: -100,
        }
        return mapping[self.signal] * self.confidence


def combine_signals(signals: list[Signal]) -> tuple[SignalType, str]:
    """将多个策略信号综合为一个建议"""
    if not signals:
        return SignalType.HOLD, "无策略信号"

    valid = [s for s in signals if s.signal != SignalType.HOLD]
    if not valid:
        return SignalType.HOLD, "各策略均为观望"

    avg_score = sum(s.score for s in valid) / len(valid)

    buy_count = sum(1 for s in valid if s.score > 0)
    sell_count = sum(1 for s in valid if s.score < 0)

    if avg_score >= 60:
        combined = SignalType.STRONG_BUY
    elif avg_score >= 20:
        combined = SignalType.BUY
    elif avg_score <= -60:
        combined = SignalType.STRONG_SELL
    elif avg_score <= -20:
        combined = SignalType.SELL
    else:
        combined = SignalType.HOLD

    summary = f"({buy_count}个看多, {sell_count}个看空, 综合评分:{avg_score:+.0f})"
    return combined, summary
