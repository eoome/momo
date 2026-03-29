"""
ETF T+0 信号提醒系统 - 配置文件
"""

# ============================================================
# T+0 ETF 列表 (从 data/t0_etf_list.json 自动加载)
# 由 t0_fetcher.py 定期更新, 不需要手动维护
# ============================================================
def _load_t0_etfs() -> list[tuple]:
    """从 t0_fetcher 生成的 JSON 加载 T+0 ETF 列表, 返回 config 格式 [(secid, code, name, market)]"""
    import json as _json
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "t0_etf_list.json")
    if not _os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as _f:
            data = _json.load(_f)
        result = []
        for e in data.get("etfs", []):
            code = e["code"]
            name = e["name"]
            market = e.get("market", "sh")
            secid = f"1.{code}" if market == "sh" else f"0.{code}"
            result.append((secid, code, name, market))
        return result
    except Exception:
        return []

T0_ETFS_FROM_FILE = _load_t0_etfs()

# ============================================================
# 监控品种列表 (已清空 — Dashboard 从 data/positions.json 读取持仓)
# 如需终端模式(main.py)使用，可在此处重新添加
# 格式: (secid, 代码, 名称, 市场前缀)
# ============================================================
T0_ETFS = T0_ETFS_FROM_FILE  # 自动从 t0_etf_list.json 加载

# ============================================================
# 我的持仓 (手动维护)
# 格式: 代码 -> {成本价, 持仓数量, 备注}
# ============================================================
MY_POSITIONS = {
    # "513100": {"cost": 1.650, "shares": 10000, "note": "纳指底仓"},
    # "518880": {"cost": 5.200, "shares": 5000,  "note": "黄金观察仓"},
}

# ============================================================
# 策略参数
# ============================================================
STRATEGY_PARAMS = {
    # 双均线策略
    "dual_ma": {
        "fast_period": 5,      # 快线周期
        "slow_period": 20,     # 慢线周期
        "enabled": True,
    },
    # RSI 策略
    "rsi": {
        "period": 14,          # RSI 周期
        "oversold": 30,        # 超卖阈值
        "overbought": 70,      # 超买阈值
        "enabled": True,
    },
    # 布林带策略
    "bollinger": {
        "period": 20,          # 中轨周期
        "std_mult": 2.0,       # 标准差倍数
        "enabled": True,
    },
    # 涨速监控
    "momentum": {
        "window_minutes": 15,  # 监控窗口(分钟)
        "alert_pct": 1.0,      # 涨速报警阈值(%)
        "enabled": True,
    },
    # 量价异动
    "volume_anomaly": {
        "avg_period": 20,      # 均量周期
        "spike_mult": 2.0,     # 放量倍数
        "enabled": True,
    },
    # MACD
    "macd": {
        "fast": 12,            # 快线周期
        "slow": 26,            # 慢线周期
        "signal_period": 9,    # 信号线周期
        "enabled": True,
    },
    # KDJ
    "kdj": {
        "period": 9,           # 周期
        "smooth_k": 3,         # K 平滑
        "smooth_d": 3,         # D 平滑
        "enabled": True,
    },
    # CCI
    "cci": {
        "period": 20,          # 周期
        "overbought": 100,     # 超买阈值
        "oversold": -100,      # 超卖阈值
        "enabled": True,
    },
    # Williams %R
    "williams": {
        "period": 14,          # 周期
        "overbought": -20,     # 超买阈值
        "oversold": -80,       # 超卖阈值
        "enabled": True,
    },
    # ADX
    "adx": {
        "period": 14,          # 周期
        "threshold": 25,       # 趋势强度阈值
        "enabled": True,
    },
    # SAR
    "sar": {
        "af_start": 0.02,      # 加速因子初始值
        "af_step": 0.02,       # 加速因子步长
        "af_max": 0.2,         # 加速因子最大值
        "enabled": True,
    },
    # OBV
    "obv": {
        "ma_period": 20,       # 均量周期
        "enabled": True,
    },
    # TRIX
    "trix": {
        "period": 12,          # 周期
        "signal_period": 9,    # 信号线周期
        "enabled": True,
    },
}

# ============================================================
# 运行配置
# ============================================================
RUN_CONFIG = {
    "refresh_seconds": 30,     # 刷新间隔(秒)
    "history_days": 60,        # 拉取历史K线天数(用于策略计算)
    "market_open": "09:30",    # 开盘时间
    "market_close": "15:00",   # 收盘时间
    "alert_cooldown": 300,     # 同一信号冷却时间(秒)
    "show_etfs": None,         # None=全部, 或指定列表 ["513100","518880"]
}
