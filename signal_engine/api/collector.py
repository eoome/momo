"""
数据采集调度 — 运行 collect_data() 驱动主循环
状态由 AppState 统一管理
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial

from signal_engine.config import STRATEGY_PARAMS, RUN_CONFIG, DATA_DIR
from signal_engine.core.signal import Signal, SignalType, combine_signals
from signal_engine.core.strategies import STRATEGY_FNS, strategy_momentum
from signal_engine.core.state import AppState
from signal_engine.data.store import load_json, save_json, ensure_data_dir
from signal_engine.data.positions import Position, calc_pnl, suggest_action
from signal_engine.data.recommendations import create_recommendation
from signal_engine.services.feed import (
    fetch_batch, fetch_realtime, fetch_history_kline, fetch_minute_kline,
    fetch_batch_kline, is_market_open,
)
from signal_engine.services.t0_fetcher import get_t0_etfs, fetch_all_etf, save_t0_list
from signal_engine.api.search import search_etf as _search_etf

log = logging.getLogger("signal_engine.collector")

_thread_pool = ThreadPoolExecutor(max_workers=8)

# ── 持久化文件 ──
POSITIONS_FILE = "positions.json"

# ── 全局状态实例 ──
state = AppState()


# ── 初始化 ──

def init_api():
    """初始化数据目录和持久化路径"""
    ensure_data_dir()
    state.initialize()


# ── 持久化快捷方式 ──

def _load_positions_file() -> dict:
    return load_json(POSITIONS_FILE, {})


def _save_positions_file(data: dict):
    save_json(POSITIONS_FILE, data)


# ── T+0 类型查询 ──

def _get_t0_type(code: str, name: str = "") -> str | None:
    for e in state.get_t0_list():
        if e["code"] == code:
            return e.get("t0_type")
    from signal_engine.services.t0_fetcher import is_t0_by_name, is_t0_by_code
    if name:
        t = is_t0_by_name(name)
        if t:
            return t
    return is_t0_by_code(code)


# ── 策略运行 ──

def _serialize_signal(s: Signal) -> dict:
    return {
        "strategy": s.strategy, "signal": s.signal.value,
        "type": s.signal.name, "reason": s.reason,
        "confidence": round(s.confidence, 2), "score": round(s.score, 1),
        "details": s.details,
        "time": state.get_signal_time(s.strategy, s.signal.name),
    }


def _run_strategies_for_etf(code, market, realtime, df_daily=None, df_min=None) -> list[dict]:
    signals = []
    params = STRATEGY_PARAMS

    if df_daily is None:
        df_daily = fetch_history_kline(code, market, RUN_CONFIG.get("history_days", 60))

    if df_daily is not None and not df_daily.empty:
        for key, fn in STRATEGY_FNS.items():
            if key == "momentum":
                continue
            p = params.get(key, {})
            if not p.get("enabled", True):
                continue
            kw = {k: v for k, v in p.items() if k != "enabled"}
            try:
                s = fn(df_daily, **kw)
                if s:
                    signals.append(s)
            except Exception as e:
                log.debug(f"Strategy {key} error for {code}: {e}")

    if params.get("momentum", {}).get("enabled") and is_market_open():
        if df_min is None:
            df_min = fetch_minute_kline(code, market, minutes=5, count=60)
        if df_min is not None and not df_min.empty:
            mp = params["momentum"]
            window = max(1, mp["window_minutes"] // 5)
            try:
                s = strategy_momentum(df_min, window=window, alert_pct=mp["alert_pct"])
                if s:
                    signals.append(s)
            except Exception:
                pass

    return [_serialize_signal(s) for s in signals]


# ── 批量 K 线拉取 (带缓存) ──

def _fetch_all_daily_klines(etfs) -> dict:
    results = {}
    need_fetch = []
    for secid, code, name, market in etfs:
        cache_key = f"{code}_daily"
        cached = state.get_kline_cached(cache_key)
        if cached is not None:
            results[code] = cached
        else:
            need_fetch.append((secid, code, name, market))
    if need_fetch:
        fetched = fetch_batch_kline(need_fetch, klt="daily", count=60, max_workers=5)
        for code, df in fetched.items():
            state.set_kline_cached(f"{code}_daily", df)
            results[code] = df
    return results


# ── 数据采集主循环 ──

def collect_data() -> dict:
    now = datetime.now()
    positions = _load_positions_file()

    if not positions:
        return {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "market_open": is_market_open(),
            "etfs": [], "alerts": [], "total_pnl": 0,
            "history": state.signal_history[-state.dashboard_history_limit:],
        }

    etfs = []
    for code, pos in positions.items():
        market = pos.get("market", "sh")
        name = pos.get("name", code)
        secid = f"1.{code}" if market == "sh" else f"0.{code}"
        etfs.append((secid, code, name, market))

    # 并发拉取
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_realtime = pool.submit(fetch_batch, etfs)
        f_daily = pool.submit(_fetch_all_daily_klines, etfs)
        f_minute = None
        if is_market_open() and STRATEGY_PARAMS.get("momentum", {}).get("enabled"):
            f_minute = pool.submit(partial(fetch_batch_kline, etfs, klt="5min", count=60, max_workers=5))

        prices_batch = f_realtime.result()
        daily_klines = f_daily.result()
        minute_klines = f_minute.result() if f_minute else {}

    # 兜底：逐个拉取
    for secid, code, name, market in etfs:
        if code not in prices_batch or prices_batch[code].get("price", 0) <= 0:
            data = fetch_realtime(code, market, secid)
            if data and data.get("price", 0) > 0:
                prices_batch[code] = data

    etf_results = []
    alerts = []

    for secid, code, name, market in etfs:
        if code not in prices_batch or prices_batch[code].get("price", 0) <= 0:
            continue
        rt = prices_batch[code]
        price = rt["price"]

        state.update_price(code, now.strftime("%H:%M"), price)

        df_daily = daily_klines.get(code)
        df_min = minute_klines.get(code)
        signals = _run_strategies_for_etf(code, market, rt, df_daily=df_daily, df_min=df_min)

        sig_objects = [
            Signal(strategy=s["strategy"], signal=SignalType[s["type"]],
                   reason=s["reason"], confidence=s["confidence"],
                   details=s.get("details", {}))
            for s in signals
        ]
        combined_type, combined_summary = combine_signals(sig_objects)

        pos = positions.get(code)
        pos_info = None
        pos_obj = None
        if pos and pos.get("shares", 0) > 0:
            pos_obj = Position(code=code, cost=pos["cost"], shares=pos["shares"], note=pos.get("note", ""))
            pnl = calc_pnl(pos_obj, price)
            pos_info = {**pos, "pnl": pnl["pnl"], "pnl_pct": pnl["pnl_pct"], "market_value": pnl["market_value"]}

        t0_type = _get_t0_type(code, rt.get("name", name))
        is_t0 = t0_type is not None
        action = suggest_action(code, price, pos_obj, combined_type, sig_objects, is_t0=is_t0)

        etf_results.append({
            "code": code, "name": rt.get("name", name), "price": price,
            "open": rt.get("open", 0), "high": rt.get("high", 0),
            "low": rt.get("low", 0), "change_pct": rt.get("change_pct", 0),
            "volume": rt.get("volume", 0), "signals": signals,
            "combined": combined_type.value, "combined_type": combined_type.name,
            "summary": combined_summary, "position": pos_info, "action": action,
            "chart": state.price_history[code][-60:], "market": market,
            "is_t0": is_t0, "t0_type": t0_type,
        })

        # 强信号 → 生成推荐单
        if combined_type.name in ("STRONG_BUY", "STRONG_SELL"):
            if not state.is_signal_cooled_down(code, combined_type.name):
                continue
            alert_entry = {
                "time": now.strftime("%H:%M:%S"), "code": code, "name": rt.get("name", name),
                "signal": combined_type.value, "type": combined_type.name,
                "summary": combined_summary, "price": price,
                "has_position": pos is not None and pos.get("shares", 0) > 0,
                "shares": pos.get("shares", 0) if pos else 0,
                "cost": pos.get("cost", 0) if pos else 0,
                "pnl_pct": round((price - pos["cost"]) / pos["cost"] * 100, 2) if pos and pos.get("cost", 0) > 0 else 0,
            }
            alerts.append(alert_entry)
            state.append_signal(alert_entry)

            direction = "买" if "BUY" in combined_type.name else "卖"
            best_strategy = max(sig_objects, key=lambda s: abs(s.score)).strategy if sig_objects else "综合"
            create_recommendation(
                code=code, name=rt.get("name", name), direction=direction,
                price=price, strategy=best_strategy, reason=combined_summary,
                confidence=max(s.confidence for s in sig_objects) if sig_objects else 0.5,
                current_shares=pos.get("shares", 0) if pos else 0,
                cost=pos.get("cost", 0) if pos else 0,
            )

    total_pnl = 0
    for code, pos in positions.items():
        price_data = prices_batch.get(code)
        if price_data and pos.get("shares", 0) > 0:
            p = Position(code=code, cost=pos["cost"], shares=pos["shares"])
            pnl = calc_pnl(p, price_data["price"])
            total_pnl += pnl["pnl"]

    return {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "market_open": is_market_open(),
        "etfs": etf_results, "alerts": alerts,
        "total_pnl": round(total_pnl, 2),
        "history": state.signal_history[-state.dashboard_history_limit:],
    }


# ── 对外接口 (routes.py 调用) ──

def search_etf(q: str) -> list[dict]:
    return _search_etf(q, get_t0_type=_get_t0_type)


def do_update_t0() -> list[dict]:
    etf_list = fetch_all_etf()
    t0_etfs = get_t0_etfs(etf_list)
    save_t0_list(t0_etfs)
    state.refresh_t0_cache(t0_etfs)
    return t0_etfs


def get_refresh_event():
    return state.refresh_event


def get_signal_history() -> list[dict]:
    return state.signal_history


def get_state() -> AppState:
    """获取全局状态实例 (供 routes.py 等需要直接访问缓存的场景)"""
    return state
