"""
数据源模块 - 双源轮询 (腾讯主力 + 东方财富备用)
通过错开不同接口的调用, 实现低成本近实时行情
"""
import time
import json
import threading
from datetime import datetime
from curl_cffi import requests as cffi_requests
import pandas as pd

# ================================================================
# 请求节流: 同一源的最小间隔 (线程安全)
# ================================================================
_SOURCE_TIMERS = {"eastmoney": 0, "tencent": 0}
_SOURCE_INTERVALS = {
    "eastmoney": 0.5,   # 批量模式下降低间隔
    "tencent": 0.3,
}
_throttle_lock = threading.Lock()


def _throttle(source: str):
    """按数据源独立节流 (线程安全)"""
    with _throttle_lock:
        interval = _SOURCE_INTERVALS.get(source, 1.0)
        elapsed = time.time() - _SOURCE_TIMERS[source]
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _SOURCE_TIMERS[source] = time.time()


# ================================================================
# 腾讯财经 (主力源, 速度快 ~100ms)
# ================================================================
def _fetch_tencent(code: str) -> dict | None:
    """腾讯财经实时行情"""
    _throttle("tencent")
    try:
        prefix = "sh" if code.startswith(("5", "6")) else "sz"
        r = cffi_requests.get(
            f"https://qt.gtimg.cn/q={prefix}{code}",
            timeout=5, impersonate="chrome"
        )
        text = r.text
        if '"' not in text:
            return None
        content = text.split('"')[1]
        parts = content.split("~")
        if len(parts) < 40:
            return None

        return {
            "code": parts[2],
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0,
            "open": float(parts[5]) if parts[5] else 0,
            "high": float(parts[33]) if parts[33] else 0,
            "low": float(parts[34]) if len(parts) > 34 and parts[34] else 0,
            "volume": int(parts[6]) if parts[6] else 0,
            "amount": float(parts[37]) if len(parts) > 37 and parts[37] else 0,
            "change_pct": float(parts[32]) if parts[32] else 0,
            "buy1": float(parts[9]) if parts[9] else 0,
            "sell1": float(parts[19]) if parts[19] else 0,
            "time": parts[30] if len(parts) > 30 else "",
            "source": "tencent",
        }
    except Exception:
        return None


# ================================================================
# 东方财富 (备用源)
# ================================================================
def _fetch_eastmoney(secid: str) -> dict | None:
    """东方财富实时行情"""
    _throttle("eastmoney")
    try:
        r = cffi_requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f169,f170",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            },
            timeout=8, impersonate="chrome"
        )
        d = r.json().get("data")
        if not d or d.get("f43") in ("-", "", None):
            return None
        return {
            "code": d.get("f57", ""),
            "name": d.get("f58", ""),
            "price": d["f43"] / 1000,
            "open": d.get("f46", 0) / 1000,
            "high": d.get("f44", 0) / 1000,
            "low": d.get("f45", 0) / 1000,
            "volume": d.get("f47", 0),
            "amount": d.get("f48", 0),
            "change_pct": d.get("f170", 0) / 100,
            "source": "eastmoney",
        }
    except Exception:
        return None


# ================================================================
# 数据校验: 过滤异常行情
# ================================================================
_MAX_DAILY_CHANGE_PCT = 20.0  # ETF 单日最大涨跌幅限制(%)


def _validate_realtime(data: dict | None) -> dict | None:
    """校验实时行情数据, 过滤异常值"""
    if not data:
        return None
    # 价格为 0 或负数
    price = data.get("price", 0)
    if price <= 0:
        return None
    # 涨跌幅异常 (超过单日限制的 2 倍, 肯定是脏数据)
    change_pct = abs(data.get("change_pct", 0))
    if change_pct > _MAX_DAILY_CHANGE_PCT * 2:
        return None
    # 最高价低于最低价 (数据异常)
    high = data.get("high", 0)
    low = data.get("low", 0)
    if high > 0 and low > 0 and high < low:
        return None
    return data


def _validate_kline(df: pd.DataFrame) -> pd.DataFrame:
    """校验K线数据, 过滤异常行"""
    if df.empty:
        return df
    # 过滤掉 close<=0 或 volume<0 的行
    df = df[(df["close"] > 0) & (df["volume"] >= 0)]
    # 过滤掉 high < low 的异常行
    if "high" in df.columns and "low" in df.columns:
        df = df[df["high"] >= df["low"]]
    return df.reset_index(drop=True)


# ================================================================
# 统一接口: 双源自动切换
# ================================================================
def fetch_realtime(code: str, market: str = "sh", secid: str = None) -> dict | None:
    """
    获取实时行情, 腾讯优先, 失败则切东方财富
    """
    data = _validate_realtime(_fetch_tencent(code))
    if data:
        return data

    if not secid:
        secid = f"1.{code}" if market == "sh" else f"0.{code}"
    data = _validate_realtime(_fetch_eastmoney(secid))
    if data:
        return data

    return None


def fetch_batch(codes: list[tuple[str, str, str, str]]) -> dict[str, dict]:
    """
    批量获取, 自动在两个源间轮询
    codes: [(secid, code, name, market), ...]
    返回: {code: data_dict}
    """
    results = {}
    for i, (secid, code, name, market) in enumerate(codes):
        # 奇数用腾讯, 偶数用东方财富 → 错开频率
        if i % 2 == 0:
            data = _fetch_eastmoney(secid)
        else:
            data = _fetch_tencent(code)

        # 校验第一个源的数据
        data = _validate_realtime(data)

        # 失败则切换另一个源
        if not data:
            if i % 2 == 0:
                data = _validate_realtime(_fetch_tencent(code))
            else:
                data = _validate_realtime(_fetch_eastmoney(secid))

        if data:
            results[code] = data

    return results


# ================================================================
# K线数据 (仅用东方财富, 腾讯无此接口)
# ================================================================
def fetch_history_kline(code: str, market: str, days: int = 60) -> pd.DataFrame:
    """获取日K线"""
    _throttle("eastmoney")
    try:
        secid = f"1.{code}" if market == "sh" else f"0.{code}"
        r = cffi_requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": "101", "fqt": "1",
                "end": "20500101", "lmt": str(days),
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            },
            timeout=10, impersonate="chrome"
        )
        klines = r.json().get("data", {}).get("klines", [])
        if not klines:
            return pd.DataFrame()
        rows = []
        for line in klines:
            p = line.split(",")
            rows.append({
                "date": p[0], "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]),
                "volume": float(p[5]), "amount": float(p[6]),
            })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return _validate_kline(df)
    except Exception:
        return pd.DataFrame()


def fetch_minute_kline(code: str, market: str, minutes: int = 5, count: int = 240) -> pd.DataFrame:
    """获取分钟K线"""
    _throttle("eastmoney")
    try:
        secid = f"1.{code}" if market == "sh" else f"0.{code}"
        klt_map = {1: "1", 5: "5", 15: "15", 30: "30", 60: "60"}
        r = cffi_requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": klt_map.get(minutes, "5"), "fqt": "1",
                "end": "20500101", "lmt": str(count),
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            },
            timeout=10, impersonate="chrome"
        )
        klines = r.json().get("data", {}).get("klines", [])
        if not klines:
            return pd.DataFrame()
        rows = []
        for line in klines:
            p = line.split(",")
            rows.append({
                "datetime": p[0], "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]),
                "volume": float(p[5]), "amount": float(p[6]),
            })
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        return _validate_kline(df)
    except Exception:
        return pd.DataFrame()


# ================================================================
# 批量K线获取 (并发, 解决逐个节流的性能问题)
# ================================================================
KLT_MAP = {
    "1min": "1", "5min": "5", "15min": "15", "30min": "30", "60min": "60",
    "daily": "101", "weekly": "102", "monthly": "103",
}


def _fetch_kline_single(secid: str, klt: str = "101", count: int = 60) -> pd.DataFrame:
    """获取单只K线 (无节流, 供批量函数内部调用)"""
    try:
        r = cffi_requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": klt, "fqt": "1",
                "end": "20500101", "lmt": str(count),
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            },
            timeout=10, impersonate="chrome"
        )
        klines = r.json().get("data", {}).get("klines", [])
        if not klines:
            return pd.DataFrame()
        rows = []
        for line in klines:
            p = line.split(",")
            rows.append({
                "date": p[0], "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]),
                "volume": float(p[5]), "amount": float(p[6]),
            })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return _validate_kline(df)
    except Exception:
        return pd.DataFrame()


def fetch_batch_kline(etfs: list[tuple], klt: str = "101", count: int = 60, max_workers: int = 5) -> dict[str, pd.DataFrame]:
    """
    批量获取K线, 使用线程池并发 + 整体节流
    etfs: [(secid, code, name, market), ...]
    klt: K线类型 (daily/5min/weekly/monthly 等)
    返回: {code: DataFrame}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    klt_val = KLT_MAP.get(klt, klt)
    results = {}

    def _fetch_one(item):
        secid, code, name, market = item
        _throttle("eastmoney")
        return code, _fetch_kline_single(secid, klt_val, count)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, e): e for e in etfs}
        for future in as_completed(futures):
            try:
                code, df = future.result()
                if not df.empty:
                    results[code] = df
            except Exception:
                pass

    return results


# ================================================================
# 交易时间判断
# ================================================================
def is_market_open() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return ("09:30" <= t <= "11:30") or ("13:00" <= t <= "15:00")


def is_trading_day() -> bool:
    return datetime.now().weekday() < 5
