"""
T+0 品种信号提醒系统 - 配置文件
纯配置数据，不含 I/O 逻辑
"""
import os

# 项目根目录 (momo/ 的上级)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")

# ============================================================
# 策略参数
# ============================================================
STRATEGY_PARAMS = {
    "dual_ma": {
        "fast_period": 5,
        "slow_period": 20,
        "enabled": True,
    },
    "rsi": {
        "period": 14,
        "oversold": 30,
        "overbought": 70,
        "enabled": True,
    },
    "bollinger": {
        "period": 20,
        "std_mult": 2.0,
        "enabled": True,
    },
    "momentum": {
        "window_minutes": 15,
        "alert_pct": 2.0,
        "enabled": True,
    },
    "volume_anomaly": {
        "avg_period": 20,
        "spike_mult": 2.0,
        "enabled": True,
    },
    "macd": {
        "fast": 12,
        "slow": 26,
        "signal_period": 9,
        "enabled": True,
    },
    "kdj": {
        "period": 9,
        "smooth_k": 3,
        "smooth_d": 3,
        "enabled": True,
    },
    "cci": {
        "period": 20,
        "overbought": 100,
        "oversold": -100,
        "enabled": True,
    },
    "williams": {
        "period": 14,
        "overbought": -20,
        "oversold": -80,
        "enabled": True,
    },
    "adx": {
        "period": 14,
        "threshold": 25,
        "enabled": True,
    },
    "sar": {
        "af_start": 0.02,
        "af_step": 0.02,
        "af_max": 0.2,
        "enabled": True,
    },
    "obv": {
        "ma_period": 20,
        "enabled": True,
    },
    "trix": {
        "period": 12,
        "signal_period": 9,
        "enabled": True,
    },
    "hl_cross": {
        "tolerance_pct": 0.5,
        "enabled": True,
    },
}

# ============================================================
# 运行配置
# ============================================================
RUN_CONFIG = {
    "refresh_seconds": 30,
    "history_days": 60,
    "market_open": "09:30",
    "market_close": "15:00",
    "alert_cooldown": 300,
    "show_etfs": None,
}
