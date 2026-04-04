"""
数据源模块 - 双源轮询 (腾讯主力 + 东方财富备用)
通过错开不同接口的调用, 实现低成本近实时行情
"""
import os
import time
import threading
from datetime import datetime
from curl_cffi import requests as cffi_requests
import pandas as pd

# 东方财富 API ut 参数 (可通过环境变量覆盖)
_EASTMONEY_UT = os.environ.get(
    "EASTMONEY_UT", "fa5fd1943c7b386f172d6893dbfba10b"
)

# ================================================================
# 请求节流: 同一源的最小间隔 (线程安全)
# ================================================================
_SOURCE_TIMERS = {"eastmoney": 0, "tencent": 0}
_SOURCE_INTERVALS = {
    "eastmoney": 0.5,
    "tencent": 0.3,
}
_throttle_lock = threading.Lock()


def _throttle(source: str):
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
    _throttle("eastmoney")
    try:
        r = cffi_requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f169,f170",
                "ut": _EASTMONEY_UT,
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
_A_SHARE_LIMIT_PCT = 10.0
_GEM_STAR_LIMIT_PCT = 20.0
_CROSS_BORDER_LIMIT_PCT = 30.0


def _get_etf_change_limit(code: str) -> float:
    if code.startswith(("300", "301", "688")):
        return _GEM_STAR_LIMIT_PCT
    if code.startswith(("513", "159", "518", "511")):
        return _CROSS_BORDER_LIMIT_PCT
    return _A_SHARE_LIMIT_PCT


def _validate_realtime(data: dict | None) -> dict | None:
    if not data:
        return None
    price = data.get("price", 0)
    if price <= 0:
        return None
    change_pct = data.get("change_pct", 0)
    if not isinstance(change_pct, (int, float)):
        return None
    abs_change = abs(change_pct)
    code = data.get("code", "")
    limit = _get_etf_change_limit(code)
    if abs_change > limit * 1.5:
        return None
    high = data.get("high", 0)
    low = data.get("low", 0)
    if high > 0 and low > 0 and high < low:
        return None
    return data


def _validate_kline(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df[(df["close"] > 0) & (df["volume"] >= 0)]
    if "high" in df.columns and "low" in df.columns:
        df = df[df["high"] >= df["low"]]
    return df.reset_index(drop=True)


# ================================================================
# 统一接口: 双源自动切换
# ================================================================
def fetch_realtime(code: str, market: str = "sh", secid: str = None) -> dict | None:
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
    results = {}
    if not codes:
        return results

    _throttle("tencent")
    try:
        symbols = []
        code_map = {}
        for secid, code, name, market in codes:
            prefix = "sh" if code.startswith(("5", "6")) else "sz"
            sym = f"{prefix}{code}"
            symbols.append(sym)
            code_map[sym] = (secid, code, name, market)

        r = cffi_requests.get(
            f"https://qt.gtimg.cn/q={','.join(symbols)}",
            timeout=5, impersonate="chrome"
        )
        for line in r.text.strip().split(";"):
            line = line.strip()
            if '"' not in line:
                continue
            content = line.split('"')[1]
            parts = content.split("~")
            if len(parts) < 40:
                continue
            code = parts[2]
            data = {
                "code": code,
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
            data = _validate_realtime(data)
            if data:
                results[code] = data
    except Exception:
        pass

    need_fallback = [c for c in codes if c[1] not in results]
    if need_fallback:
        _throttle("eastmoney")
        for secid, code, name, market in need_fallback:
            data = _validate_realtime(_fetch_eastmoney(secid))
            if data:
                results[code] = data

    return results


# ================================================================
# K线数据 (仅用东方财富)
# ================================================================
def fetch_history_kline(code: str, market: str, days: int = 60) -> pd.DataFrame:
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
                "ut": _EASTMONEY_UT,
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
                "ut": _EASTMONEY_UT,
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
# 批量K线获取
# ================================================================
KLT_MAP = {
    "1min": "1", "5min": "5", "15min": "15", "30min": "30", "60min": "60",
    "daily": "101", "weekly": "102", "monthly": "103",
}


def _fetch_kline_single(secid: str, klt: str = "101", count: int = 60) -> pd.DataFrame:
    try:
        r = cffi_requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": klt, "fqt": "1",
                "end": "20500101", "lmt": str(count),
                "ut": _EASTMONEY_UT,
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
        is_minute = klt.isdigit() and int(klt) <= 60
        time_col = "datetime" if is_minute else "date"
        df[time_col] = pd.to_datetime(df["date"])
        if time_col != "date":
            df = df.drop(columns=["date"])
        return _validate_kline(df)
    except Exception:
        return pd.DataFrame()


def fetch_batch_kline(etfs: list[tuple], klt: str = "101", count: int = 60, max_workers: int = 5) -> dict[str, pd.DataFrame]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    klt_val = KLT_MAP.get(klt, klt)
    results = {}

    _throttle("eastmoney")

    def _fetch_one(item):
        secid, code, name, market = item
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
