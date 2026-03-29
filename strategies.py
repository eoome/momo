"""
策略模块 - 5种常用策略
每个策略返回 Signal 对象
"""
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import pandas as pd
import numpy as np


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


# ================================================================
# 策略1: 双均线策略 (Dual Moving Average Crossover)
# 快线上穿慢线 → 买入, 下穿 → 卖出
# ================================================================
def strategy_dual_ma(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> Signal | None:
    if len(df) < slow:
        return None

    df = df.copy()
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()
    df = df.dropna()

    if len(df) < 2:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 金叉: 快线从下方穿越慢线
    golden = prev["ma_fast"] <= prev["ma_slow"] and curr["ma_fast"] > curr["ma_slow"]
    # 死叉: 快线从上方穿越慢线
    death = prev["ma_fast"] >= prev["ma_slow"] and curr["ma_fast"] < curr["ma_slow"]

    # 趋势强度
    gap_pct = (curr["ma_fast"] - curr["ma_slow"]) / curr["ma_slow"] * 100

    if golden:
        return Signal(
            strategy="双均线",
            signal=SignalType.STRONG_BUY,
            reason=f"MA{fast} 上穿 MA{slow} (金叉)",
            confidence=min(1.0, 0.6 + abs(gap_pct) * 0.1),
            details={"ma_fast": round(curr["ma_fast"], 4), "ma_slow": round(curr["ma_slow"], 4)},
        )
    elif death:
        return Signal(
            strategy="双均线",
            signal=SignalType.STRONG_SELL,
            reason=f"MA{fast} 下穿 MA{slow} (死叉)",
            confidence=min(1.0, 0.6 + abs(gap_pct) * 0.1),
            details={"ma_fast": round(curr["ma_fast"], 4), "ma_slow": round(curr["ma_slow"], 4)},
        )
    elif gap_pct > 1.5:
        return Signal(
            strategy="双均线",
            signal=SignalType.BUY,
            reason=f"MA{fast} 在 MA{slow} 上方, 多头排列 ({gap_pct:+.2f}%)",
            confidence=0.5,
        )
    elif gap_pct < -1.5:
        return Signal(
            strategy="双均线",
            signal=SignalType.SELL,
            reason=f"MA{fast} 在 MA{slow} 下方, 空头排列 ({gap_pct:+.2f}%)",
            confidence=0.5,
        )
    else:
        return Signal(
            strategy="双均线",
            signal=SignalType.HOLD,
            reason=f"均线缠绕, 方向不明 ({gap_pct:+.2f}%)",
            confidence=0.3,
        )


# ================================================================
# 策略2: RSI 超买超卖
# RSI < 30 → 超卖(买入), RSI > 70 → 超买(卖出)
# ================================================================
def strategy_rsi(df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> Signal | None:
    if len(df) < period + 1:
        return None

    df = df.copy()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    # Wilder's smoothing (exponential, alpha=1/period) — 比 SMA 更灵敏
    avg_gain = gain.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    df = df.dropna()

    if len(df) < 1:
        return None

    rsi = df.iloc[-1]["rsi"]
    prev_rsi = df.iloc[-2]["rsi"] if len(df) >= 2 else rsi

    if rsi < oversold:
        # RSI进入超卖区
        confidence = min(1.0, (oversold - rsi) / 20 + 0.4)
        # RSI开始回升, 信号更强
        if rsi > prev_rsi:
            confidence = min(1.0, confidence + 0.2)
            reason = f"RSI={rsi:.1f} 超卖区回升, 反弹信号"
            sig = SignalType.STRONG_BUY
        else:
            reason = f"RSI={rsi:.1f} 超卖区, 关注反弹机会"
            sig = SignalType.BUY
        return Signal(strategy="RSI", signal=sig, reason=reason, confidence=confidence)

    elif rsi > overbought:
        confidence = min(1.0, (rsi - overbought) / 20 + 0.4)
        if rsi < prev_rsi:
            confidence = min(1.0, confidence + 0.2)
            reason = f"RSI={rsi:.1f} 超买区回落, 注意风险"
            sig = SignalType.STRONG_SELL
        else:
            reason = f"RSI={rsi:.1f} 超买区, 谨慎追高"
            sig = SignalType.SELL
        return Signal(strategy="RSI", signal=sig, reason=reason, confidence=confidence)

    else:
        return Signal(
            strategy="RSI",
            signal=SignalType.HOLD,
            reason=f"RSI={rsi:.1f} 中性区间",
            confidence=0.3,
        )


# ================================================================
# 策略3: 布林带 (Bollinger Bands)
# 价格触及下轨 → 买入, 触及上轨 → 卖出
# ================================================================
def strategy_bollinger(df: pd.DataFrame, period: int = 20, std_mult: float = 2.0) -> Signal | None:
    if len(df) < period:
        return None

    df = df.copy()
    df["ma"] = df["close"].rolling(period).mean()
    df["std"] = df["close"].rolling(period).std()
    df["upper"] = df["ma"] + std_mult * df["std"]
    df["lower"] = df["ma"] - std_mult * df["std"]
    df = df.dropna()

    if len(df) < 1:
        return None

    curr = df.iloc[-1]
    price = curr["close"]
    upper = curr["upper"]
    lower = curr["lower"]
    ma = curr["ma"]

    # 计算价格在布林带中的位置 (0=下轨, 1=上轨)
    band_width = upper - lower
    if band_width == 0:
        return None
    position = (price - lower) / band_width

    if price <= lower:
        return Signal(
            strategy="布林带",
            signal=SignalType.STRONG_BUY,
            reason=f"价格触及下轨 ({price:.3f} ≤ {lower:.3f}), 超跌反弹概率大",
            confidence=min(1.0, 0.6 + (lower - price) / band_width * 2),
            details={"upper": round(upper, 3), "middle": round(ma, 3), "lower": round(lower, 3)},
        )
    elif price >= upper:
        return Signal(
            strategy="布林带",
            signal=SignalType.STRONG_SELL,
            reason=f"价格触及上轨 ({price:.3f} ≥ {upper:.3f}), 短期回调风险大",
            confidence=min(1.0, 0.6 + (price - upper) / band_width * 2),
            details={"upper": round(upper, 3), "middle": round(ma, 3), "lower": round(lower, 3)},
        )
    elif position < 0.2:
        return Signal(
            strategy="布林带",
            signal=SignalType.BUY,
            reason=f"价格接近下轨 (位置:{position:.0%}), 可逢低关注",
            confidence=0.5,
        )
    elif position > 0.8:
        return Signal(
            strategy="布林带",
            signal=SignalType.SELL,
            reason=f"价格接近上轨 (位置:{position:.0%}), 注意上方压力",
            confidence=0.5,
        )
    else:
        return Signal(
            strategy="布林带",
            signal=SignalType.HOLD,
            reason=f"布林带中轨附近 (位置:{position:.0%})",
            confidence=0.3,
        )


# ================================================================
# 策略4: 涨速监控 (Momentum)
# 短时间大幅拉升 → 追涨风险大, 短时间急跌 → 关注抄底
# ================================================================
def strategy_momentum(df: pd.DataFrame, window: int = 15, alert_pct: float = 1.0) -> Signal | None:
    """
    基于分钟K线, 监控短时间涨跌幅
    window: 监控窗口(分钟数, 对应K线根数)
    """
    if len(df) < window:
        return None

    # 取最近 window 根K线
    recent = df.tail(window)
    start_price = recent.iloc[0]["close"]
    end_price = recent.iloc[-1]["close"]

    if start_price == 0:
        return None

    change_pct = (end_price - start_price) / start_price * 100

    if change_pct >= alert_pct * 2:
        return Signal(
            strategy="涨速监控",
            signal=SignalType.STRONG_SELL,
            reason=f"{window}分钟内急涨 {change_pct:+.2f}%, 短期获利了结压力大",
            confidence=min(1.0, 0.5 + abs(change_pct - alert_pct * 2) * 0.15),
        )
    elif change_pct >= alert_pct:
        return Signal(
            strategy="涨速监控",
            signal=SignalType.SELL,
            reason=f"{window}分钟内拉升 {change_pct:+.2f}%, 注意追涨风险",
            confidence=0.6,
        )
    elif change_pct <= -alert_pct * 2:
        return Signal(
            strategy="涨速监控",
            signal=SignalType.STRONG_BUY,
            reason=f"{window}分钟内急跌 {change_pct:+.2f}%, 超跌反弹机会",
            confidence=min(1.0, 0.5 + abs(change_pct + alert_pct * 2) * 0.15),
        )
    elif change_pct <= -alert_pct:
        return Signal(
            strategy="涨速监控",
            signal=SignalType.BUY,
            reason=f"{window}分钟内下跌 {change_pct:+.2f}%, 关注是否企稳",
            confidence=0.6,
        )
    else:
        return None  # 波动正常, 不发信号


# ================================================================
# 策略5: 量价异动 (Volume Anomaly)
# 放量上涨 → 看多, 放量下跌 → 看空, 缩量 → 观望
# ================================================================
def strategy_volume(df: pd.DataFrame, avg_period: int = 20, spike_mult: float = 2.0) -> Signal | None:
    if len(df) < avg_period + 1:
        return None

    df = df.copy()
    df["avg_vol"] = df["volume"].rolling(avg_period).mean()
    df = df.dropna()

    if len(df) < 1:
        return None

    curr = df.iloc[-1]
    vol_ratio = curr["volume"] / curr["avg_vol"] if curr["avg_vol"] > 0 else 1
    price_change = (curr["close"] - curr["open"]) / curr["open"] * 100 if curr["open"] > 0 else 0

    if vol_ratio >= spike_mult and price_change > 0.5:
        return Signal(
            strategy="量价异动",
            signal=SignalType.BUY,
            reason=f"放量 {vol_ratio:.1f}x 上涨 {price_change:+.2f}%, 资金进场",
            confidence=min(1.0, 0.5 + (vol_ratio - spike_mult) * 0.15),
            details={"vol_ratio": round(vol_ratio, 1), "price_change": round(price_change, 2)},
        )
    elif vol_ratio >= spike_mult and price_change < -0.5:
        return Signal(
            strategy="量价异动",
            signal=SignalType.SELL,
            reason=f"放量 {vol_ratio:.1f}x 下跌 {price_change:+.2f}%, 资金出逃",
            confidence=min(1.0, 0.5 + (vol_ratio - spike_mult) * 0.15),
            details={"vol_ratio": round(vol_ratio, 1), "price_change": round(price_change, 2)},
        )
    elif vol_ratio < 0.5:
        return Signal(
            strategy="量价异动",
            signal=SignalType.HOLD,
            reason=f"缩量 ({vol_ratio:.1f}x), 市场观望情绪浓",
            confidence=0.4,
        )
    else:
        return None


# ================================================================
# 策略6: MACD (Moving Average Convergence Divergence)
# ================================================================
def strategy_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9) -> Signal | None:
    if len(df) < slow + signal_period:
        return None

    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["signal_line"] = df["macd"].ewm(span=signal_period, adjust=False).mean()
    df["histogram"] = df["macd"] - df["signal_line"]
    df = df.dropna()

    if len(df) < 2:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 金叉: MACD 上穿信号线
    golden = prev["macd"] <= prev["signal_line"] and curr["macd"] > curr["signal_line"]
    # 死叉: MACD 下穿信号线
    death = prev["macd"] >= prev["signal_line"] and curr["macd"] < curr["signal_line"]

    # 柱状图变化趋势
    hist_rising = curr["histogram"] > prev["histogram"]
    hist_val = curr["histogram"]

    if golden:
        conf = min(1.0, 0.6 + abs(hist_val) * 20)
        return Signal(
            strategy="MACD",
            signal=SignalType.STRONG_BUY,
            reason=f"MACD 金叉 ({curr['macd']:.4f} 上穿 {curr['signal_line']:.4f})",
            confidence=conf,
            details={"macd": round(curr["macd"], 4), "signal": round(curr["signal_line"], 4), "hist": round(hist_val, 4)},
        )
    elif death:
        conf = min(1.0, 0.6 + abs(hist_val) * 20)
        return Signal(
            strategy="MACD",
            signal=SignalType.STRONG_SELL,
            reason=f"MACD 死叉 ({curr['macd']:.4f} 下穿 {curr['signal_line']:.4f})",
            confidence=conf,
            details={"macd": round(curr["macd"], 4), "signal": round(curr["signal_line"], 4), "hist": round(hist_val, 4)},
        )
    elif hist_val > 0 and hist_rising:
        return Signal(
            strategy="MACD",
            signal=SignalType.BUY,
            reason=f"MACD 多头, 柱状图扩张 ({hist_val:.4f})",
            confidence=0.5,
        )
    elif hist_val < 0 and not hist_rising:
        return Signal(
            strategy="MACD",
            signal=SignalType.SELL,
            reason=f"MACD 空头, 柱状图扩张 ({hist_val:.4f})",
            confidence=0.5,
        )
    else:
        return Signal(
            strategy="MACD",
            signal=SignalType.HOLD,
            reason=f"MACD 柱状图收窄, 趋势减弱",
            confidence=0.3,
        )


# ================================================================
# 策略7: KDJ (Stochastic Oscillator)
# ================================================================
def strategy_kdj(df: pd.DataFrame, period: int = 9, smooth_k: int = 3, smooth_d: int = 3) -> Signal | None:
    if len(df) < period + smooth_d:
        return None

    df = df.copy()
    low_min = df["low"].rolling(period).min()
    high_max = df["high"].rolling(period).max()
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)

    # K = SMA(RSV, smooth_k), D = SMA(K, smooth_d)
    df["K"] = rsv.rolling(smooth_k).mean()
    df["D"] = df["K"].rolling(smooth_d).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    df = df.dropna()

    if len(df) < 2:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    k, d, j = curr["K"], curr["D"], curr["J"]
    prev_k, prev_d = prev["K"], prev["D"]

    # 金叉: K 上穿 D
    golden = prev_k <= prev_d and k > d
    # 死叉: K 下穿 D
    death = prev_k >= prev_d and k < d

    if k < 20 and d < 20 and j < 0:
        if golden:
            return Signal(strategy="KDJ", signal=SignalType.STRONG_BUY,
                          reason=f"KDJ 超卖金叉 (K={k:.1f} D={d:.1f} J={j:.1f})",
                          confidence=min(1.0, 0.7 + (20 - k) / 30))
        return Signal(strategy="KDJ", signal=SignalType.BUY,
                      reason=f"KDJ 超卖区 (K={k:.1f} D={d:.1f})",
                      confidence=0.6)
    elif k > 80 and d > 80 and j > 100:
        if death:
            return Signal(strategy="KDJ", signal=SignalType.STRONG_SELL,
                          reason=f"KDJ 超买死叉 (K={k:.1f} D={d:.1f} J={j:.1f})",
                          confidence=min(1.0, 0.7 + (k - 80) / 30))
        return Signal(strategy="KDJ", signal=SignalType.SELL,
                      reason=f"KDJ 超买区 (K={k:.1f} D={d:.1f})",
                      confidence=0.6)
    elif golden:
        return Signal(strategy="KDJ", signal=SignalType.BUY,
                      reason=f"KDJ 金叉 (K={k:.1f} 上穿 D={d:.1f})",
                      confidence=0.55)
    elif death:
        return Signal(strategy="KDJ", signal=SignalType.SELL,
                      reason=f"KDJ 死叉 (K={k:.1f} 下穿 D={d:.1f})",
                      confidence=0.55)
    else:
        return Signal(strategy="KDJ", signal=SignalType.HOLD,
                      reason=f"KDJ 中性 (K={k:.1f} D={d:.1f} J={j:.1f})",
                      confidence=0.3)


# ================================================================
# 策略8: CCI (Commodity Channel Index)
# CCI > 100 → 超买, CCI < -100 → 超卖
# ================================================================
def strategy_cci(df: pd.DataFrame, period: int = 20, overbought: float = 100, oversold: float = -100) -> Signal | None:
    if len(df) < period:
        return None
    df = df.copy()
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    df["cci"] = (tp - sma) / (0.015 * mad)
    df = df.dropna()
    if len(df) < 2:
        return None
    cci = df.iloc[-1]["cci"]
    prev_cci = df.iloc[-2]["cci"]
    if cci < oversold:
        conf = min(1.0, (oversold - cci) / 100 + 0.4)
        if cci > prev_cci:
            return Signal(strategy="CCI", signal=SignalType.STRONG_BUY,
                          reason=f"CCI={cci:.1f} 超卖区回升", confidence=min(1.0, conf + 0.2))
        return Signal(strategy="CCI", signal=SignalType.BUY,
                      reason=f"CCI={cci:.1f} 超卖区", confidence=conf)
    elif cci > overbought:
        conf = min(1.0, (cci - overbought) / 100 + 0.4)
        if cci < prev_cci:
            return Signal(strategy="CCI", signal=SignalType.STRONG_SELL,
                          reason=f"CCI={cci:.1f} 超买区回落", confidence=min(1.0, conf + 0.2))
        return Signal(strategy="CCI", signal=SignalType.SELL,
                      reason=f"CCI={cci:.1f} 超买区", confidence=conf)
    return Signal(strategy="CCI", signal=SignalType.HOLD,
                  reason=f"CCI={cci:.1f} 中性区间", confidence=0.3)


# ================================================================
# 策略9: Williams %R
# %R > -20 → 超买, %R < -80 → 超卖
# ================================================================
def strategy_williams(df: pd.DataFrame, period: int = 14, overbought: float = -20, oversold: float = -80) -> Signal | None:
    if len(df) < period:
        return None
    df = df.copy()
    high_max = df["high"].rolling(period).max()
    low_min = df["low"].rolling(period).min()
    df["willr"] = (high_max - df["close"]) / (high_max - low_min) * -100
    df = df.dropna()
    if len(df) < 2:
        return None
    wr = df.iloc[-1]["willr"]
    prev_wr = df.iloc[-2]["willr"]
    if wr < oversold:  # %R is negative, < -80 means oversold
        conf = min(1.0, (oversold - wr) / 30 + 0.4)
        if wr > prev_wr:
            return Signal(strategy="Williams", signal=SignalType.STRONG_BUY,
                          reason=f"Williams %R={wr:.1f} 超卖回升", confidence=min(1.0, conf + 0.2))
        return Signal(strategy="Williams", signal=SignalType.BUY,
                      reason=f"Williams %R={wr:.1f} 超卖区", confidence=conf)
    elif wr > overbought:  # > -20 means overbought
        conf = min(1.0, (wr - overbought) / 30 + 0.4)
        if wr < prev_wr:
            return Signal(strategy="Williams", signal=SignalType.STRONG_SELL,
                          reason=f"Williams %R={wr:.1f} 超买回落", confidence=min(1.0, conf + 0.2))
        return Signal(strategy="Williams", signal=SignalType.SELL,
                      reason=f"Williams %R={wr:.1f} 超买区", confidence=conf)
    return Signal(strategy="Williams", signal=SignalType.HOLD,
                  reason=f"Williams %R={wr:.1f} 中性", confidence=0.3)


# ================================================================
# 策略10: ADX (Average Directional Index) + DI
# ADX > 25 表示趋势强, +DI > -DI 看多, 反之看空
# ================================================================
def strategy_adx(df: pd.DataFrame, period: int = 14, threshold: float = 25) -> Signal | None:
    if len(df) < period * 2:
        return None
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr = pd.Series(tr, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    df = df.assign(adx=adx, plus_di=plus_di, minus_di=minus_di).dropna()
    if len(df) < 1:
        return None
    row = df.iloc[-1]
    adx_val, pdi, mdi = row["adx"], row["plus_di"], row["minus_di"]
    if adx_val >= threshold:
        if pdi > mdi:
            return Signal(strategy="ADX", signal=SignalType.BUY,
                          reason=f"ADX={adx_val:.1f} 强趋势, +DI({pdi:.1f}) > -DI({mdi:.1f})",
                          confidence=min(1.0, 0.5 + (adx_val - threshold) / 50))
        else:
            return Signal(strategy="ADX", signal=SignalType.SELL,
                          reason=f"ADX={adx_val:.1f} 强趋势, -DI({mdi:.1f}) > +DI({pdi:.1f})",
                          confidence=min(1.0, 0.5 + (adx_val - threshold) / 50))
    return Signal(strategy="ADX", signal=SignalType.HOLD,
                  reason=f"ADX={adx_val:.1f} 弱趋势, 观望", confidence=0.3)


# ================================================================
# 策略11: Parabolic SAR
# SAR 在价格下方 → 看多, 在价格上方 → 看空
# ================================================================
def strategy_sar(df: pd.DataFrame, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2) -> Signal | None:
    if len(df) < 10:
        return None
    df = df.copy()
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    sar = np.zeros(n)
    ep = np.zeros(n)
    af = np.zeros(n)
    trend = np.ones(n)  # 1=up, -1=down
    # 初始化
    trend[0] = 1
    sar[0] = low[0]
    ep[0] = high[0]
    af[0] = af_start
    for i in range(1, n):
        if trend[i-1] == 1:  # 上升趋势
            sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[max(0,i-2)])
            if high[i] > ep[i-1]:
                ep[i] = high[i]
                af[i] = min(af[i-1] + af_step, af_max)
            else:
                ep[i] = ep[i-1]
                af[i] = af[i-1]
            if low[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep[i-1]
                ep[i] = low[i]
                af[i] = af_start
            else:
                trend[i] = 1
        else:  # 下降趋势
            sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[max(0,i-2)])
            if low[i] < ep[i-1]:
                ep[i] = low[i]
                af[i] = min(af[i-1] + af_step, af_max)
            else:
                ep[i] = ep[i-1]
                af[i] = af[i-1]
            if high[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep[i-1]
                ep[i] = high[i]
                af[i] = af_start
            else:
                trend[i] = -1
    curr_trend = trend[-1]
    prev_trend = trend[-2] if n >= 2 else curr_trend
    if curr_trend == 1 and prev_trend == -1:
        return Signal(strategy="SAR", signal=SignalType.STRONG_BUY,
                      reason=f"SAR 翻转至价格下方, 趋势转多",
                      confidence=min(1.0, 0.6 + abs(close[-1] - sar[-1]) / close[-1] * 20))
    elif curr_trend == -1 and prev_trend == 1:
        return Signal(strategy="SAR", signal=SignalType.STRONG_SELL,
                      reason=f"SAR 翻转至价格上方, 趋势转空",
                      confidence=min(1.0, 0.6 + abs(close[-1] - sar[-1]) / close[-1] * 20))
    elif curr_trend == 1:
        return Signal(strategy="SAR", signal=SignalType.HOLD,
                      reason=f"SAR 在价格下方, 上升趋势中",
                      confidence=0.4)
    else:
        return Signal(strategy="SAR", signal=SignalType.HOLD,
                      reason=f"SAR 在价格上方, 下降趋势中",
                      confidence=0.4)


# ================================================================
# 策略12: OBV (On-Balance Volume) 趋势
# OBV 均线上升 + 价格上涨 → 确认多头, 反之确认空头
# ================================================================
def strategy_obv(df: pd.DataFrame, ma_period: int = 20) -> Signal | None:
    if len(df) < ma_period + 1:
        return None
    df = df.copy()
    obv = [0]
    for i in range(1, len(df)):
        if df.iloc[i]["close"] > df.iloc[i-1]["close"]:
            obv.append(obv[-1] + df.iloc[i]["volume"])
        elif df.iloc[i]["close"] < df.iloc[i-1]["close"]:
            obv.append(obv[-1] - df.iloc[i]["volume"])
        else:
            obv.append(obv[-1])
    df["obv"] = obv
    df["obv_ma"] = df["obv"].rolling(ma_period).mean()
    df = df.dropna()
    if len(df) < 2:
        return None
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    obv_rising = curr["obv"] > prev["obv"]
    obv_above_ma = curr["obv"] > curr["obv_ma"]
    price_up = curr["close"] > curr["open"]
    price_change = (curr["close"] - df.iloc[-ma_period]["close"]) / df.iloc[-ma_period]["close"] * 100
    if obv_rising and obv_above_ma and price_up and price_change > 1:
        return Signal(strategy="OBV", signal=SignalType.BUY,
                      reason=f"OBV 上升确认多头, 价格趋势一致 ({price_change:+.1f}%)",
                      confidence=min(1.0, 0.5 + abs(price_change) * 0.05))
    elif not obv_rising and not obv_above_ma and not price_up and price_change < -1:
        return Signal(strategy="OBV", signal=SignalType.SELL,
                      reason=f"OBV 下降确认空头, 价格趋势一致 ({price_change:+.1f}%)",
                      confidence=min(1.0, 0.5 + abs(price_change) * 0.05))
    elif obv_rising and not price_up:
        return Signal(strategy="OBV", signal=SignalType.BUY,
                      reason=f"OBV 上升但价格未涨, 底部吸筹可能",
                      confidence=0.45)
    elif not obv_rising and price_up:
        return Signal(strategy="OBV", signal=SignalType.SELL,
                      reason=f"价格涨但OBV下降, 量价背离风险",
                      confidence=0.45)
    return Signal(strategy="OBV", signal=SignalType.HOLD,
                  reason=f"OBV 量价关系正常", confidence=0.3)


# ================================================================
# 策略13: TRIX (Triple Exponential Average)
# TRIX 上穿信号线 → 买入, 下穿 → 卖出
# ================================================================
def strategy_trix(df: pd.DataFrame, period: int = 12, signal_period: int = 9) -> Signal | None:
    if len(df) < period * 3 + signal_period:
        return None
    df = df.copy()
    ema1 = df["close"].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    trix = ema3.pct_change() * 100
    trix_signal = trix.rolling(signal_period).mean()
    df = df.assign(trix=trix, trix_signal=trix_signal).dropna()
    if len(df) < 2:
        return None
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    golden = prev["trix"] <= prev["trix_signal"] and curr["trix"] > curr["trix_signal"]
    death = prev["trix"] >= prev["trix_signal"] and curr["trix"] < curr["trix_signal"]
    if golden:
        return Signal(strategy="TRIX", signal=SignalType.STRONG_BUY,
                      reason=f"TRIX 金叉 ({curr['trix']:.4f} 上穿 {curr['trix_signal']:.4f})",
                      confidence=min(1.0, 0.6 + abs(curr["trix"]) * 50))
    elif death:
        return Signal(strategy="TRIX", signal=SignalType.STRONG_SELL,
                      reason=f"TRIX 死叉 ({curr['trix']:.4f} 下穿 {curr['trix_signal']:.4f})",
                      confidence=min(1.0, 0.6 + abs(curr["trix"]) * 50))
    elif curr["trix"] > 0 and curr["trix"] > curr["trix_signal"]:
        return Signal(strategy="TRIX", signal=SignalType.BUY,
                      reason=f"TRIX 多头排列 ({curr['trix']:.4f})",
                      confidence=0.5)
    elif curr["trix"] < 0 and curr["trix"] < curr["trix_signal"]:
        return Signal(strategy="TRIX", signal=SignalType.SELL,
                      reason=f"TRIX 空头排列 ({curr['trix']:.4f})",
                      confidence=0.5)
    return Signal(strategy="TRIX", signal=SignalType.HOLD,
                  reason=f"TRIX 中性", confidence=0.3)


# ================================================================
# 综合信号: 汇总所有策略给出建议
# ================================================================
def combine_signals(signals: list[Signal]) -> tuple[SignalType, str]:
    """将多个策略信号综合为一个建议"""
    if not signals:
        return SignalType.HOLD, "无策略信号"

    valid = [s for s in signals if s.signal != SignalType.HOLD]
    if not valid:
        return SignalType.HOLD, "各策略均为观望"

    avg_score = sum(s.score for s in valid) / len(valid)

    # 统计各类型
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


# ================================================================
# 策略注册表: 统一供终端和 Web 使用
# ================================================================
STRATEGY_FNS = {
    "dual_ma": strategy_dual_ma,
    "rsi": strategy_rsi,
    "bollinger": strategy_bollinger,
    "volume_anomaly": strategy_volume,
    "momentum": strategy_momentum,
    "macd": strategy_macd,
    "kdj": strategy_kdj,
    "cci": strategy_cci,
    "williams": strategy_williams,
    "adx": strategy_adx,
    "sar": strategy_sar,
    "obv": strategy_obv,
    "trix": strategy_trix,
}
