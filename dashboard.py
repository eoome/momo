#!/usr/bin/env python3
"""
ETF T+0 可视化仪表盘
启动: python3 dashboard.py
浏览器访问 http://localhost:8888
"""
import asyncio
import json
import sys
import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from curl_cffi import requests as cffi_requests

from config import STRATEGY_PARAMS, RUN_CONFIG
from t0_fetcher import load_t0_list, load_or_update, get_t0_etfs, fetch_all_etf, save_t0_list
from datafeed import (
    fetch_batch, fetch_realtime, fetch_history_kline, fetch_minute_kline,
    fetch_batch_kline, is_market_open, KLT_MAP,
)
from strategies import (
    strategy_dual_ma, strategy_rsi, strategy_bollinger,
    strategy_momentum, strategy_volume, strategy_macd, strategy_kdj,
    strategy_cci, strategy_williams, strategy_adx, strategy_sar, strategy_obv, strategy_trix,
    Signal, SignalType, combine_signals, STRATEGY_FNS,
)
from position import load_positions, calc_pnl, Position, suggest_action
from backtest import run_backtest
from trades import load_trades, add_trade, delete_trade, update_trade, get_trade_summary, recalc_trades, save_trades
from recommendations import create_recommendation, get_pending, get_all, confirm_recommendation, ignore_recommendation

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger("dashboard")

_thread_pool = ThreadPoolExecutor(max_workers=8)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ===================== 持久化 =====================
POSITIONS_FILE = os.path.join(DATA_DIR, "positions.json")
SIGNALS_FILE = os.path.join(DATA_DIR, "signals_history.json")
MAX_HISTORY = 500


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Load {path} failed: {e}")
    return default


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"Save {path} failed: {e}")


def _load_positions_file() -> dict:
    return _load_json(POSITIONS_FILE, {})


def _save_positions_file(data: dict):
    _save_json(POSITIONS_FILE, data)


def _load_signal_history() -> list:
    return _load_json(SIGNALS_FILE, [])


def _save_signal_history(data: list):
    # 只保留最近 MAX_HISTORY 条
    if len(data) > MAX_HISTORY:
        data = data[-MAX_HISTORY:]
    _save_json(SIGNALS_FILE, data)


# ===================== 应用 =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时加载历史信号
    global signal_history
    signal_history = _load_signal_history()
    task = asyncio.create_task(data_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

signal_history: list[dict] = []
price_history: dict[str, list[dict]] = {}
MAX_PRICE_POINTS = 120
_kline_cache: dict[str, dict] = {}
KLINE_CACHE_TTL = 60
connected_clients: set[WebSocket] = set()

# T+0 ETF 缓存
_t0_cache: list[dict] = []
_t0_cache_ts: float = 0
_T0_CACHE_TTL = 3600  # 1小时


def _get_t0_cache() -> list[dict]:
    global _t0_cache, _t0_cache_ts
    now = time.time()
    if not _t0_cache or (now - _t0_cache_ts) > _T0_CACHE_TTL:
        _t0_cache = load_t0_list()
        _t0_cache_ts = now
    return _t0_cache


def _is_t0_code(code: str) -> bool:
    """检查代码是否为 T+0 ETF"""
    return any(e["code"] == code for e in _get_t0_cache())


def _get_t0_type(code: str) -> str | None:
    """获取 T+0 类型，非 T+0 返回 None"""
    for e in _get_t0_cache():
        if e["code"] == code:
            return e.get("t0_type")
    return None

# ===================== 信号冷却 =====================
_last_signal_time: dict[str, float] = {}  # {f"{code}_{signal_type}": timestamp}


def _is_signal_cooled_down(code: str, signal_type: str) -> bool:
    """
    检查信号是否已过冷却期。
    返回 True = 允许发送（已冷却）, False = 冷却中（禁止发送）。
    仅在允许发送时才更新时间戳。
    """
    key = f"{code}_{signal_type}"
    cooldown = RUN_CONFIG.get("alert_cooldown", 300)
    now = time.time()
    last = _last_signal_time.get(key, 0)
    if now - last < cooldown:
        return False
    _last_signal_time[key] = now
    return True


def _run_strategies_for_etf(code, market, realtime, df_daily=None, df_min=None):
    signals = []
    params = STRATEGY_PARAMS

    if df_daily is None:
        days = RUN_CONFIG.get("history_days", 60)
        df_daily = fetch_history_kline(code, market, days)

    if not df_daily.empty:
        for key, fn in STRATEGY_FNS.items():
            if key == "momentum":
                continue  # 涨速监控单独处理（需要分钟线）
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
        if not df_min.empty:
            mp = params["momentum"]
            window = max(1, mp["window_minutes"] // 5)
            try:
                s = strategy_momentum(df_min, window=window, alert_pct=mp["alert_pct"])
                if s:
                    signals.append(s)
            except Exception:
                pass

    return [_serialize_signal(s) for s in signals]


def _serialize_signal(s):
    return {
        "strategy": s.strategy,
        "signal": s.signal.value,
        "type": s.signal.name,
        "reason": s.reason,
        "confidence": round(s.confidence, 2),
        "score": round(s.score, 1),
        "details": s.details,
    }


# ===================== 数据采集 =====================
def _fetch_all_daily_klines(etfs):
    now = time.time()
    results = {}
    need_fetch = []
    for secid, code, name, market in etfs:
        cached = _kline_cache.get(code)
        if cached and (now - cached["ts"]) < KLINE_CACHE_TTL:
            results[code] = cached["data"]
        else:
            need_fetch.append((secid, code, name, market))
    if need_fetch:
        fetched = fetch_batch_kline(need_fetch, klt="daily", count=60, max_workers=5)
        for code, df in fetched.items():
            _kline_cache[code] = {"data": df, "ts": now}
            results[code] = df
    return results


def collect_data():
    now = datetime.now()
    positions = _load_positions_file()

    # 从持仓构建监控列表
    if not positions:
        return {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "market_open": is_market_open(),
            "etfs": [], "alerts": [],
            "total_pnl": 0,
            "history": signal_history[-50:],
        }

    etfs = []
    for code, pos in positions.items():
        market = pos.get("market", "sh")
        name = pos.get("name", code)
        secid = f"1.{code}" if market == "sh" else f"0.{code}"
        etfs.append((secid, code, name, market))

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_realtime = pool.submit(fetch_batch, etfs)
        f_daily = pool.submit(_fetch_all_daily_klines, etfs)
        f_minute = None
        if is_market_open() and STRATEGY_PARAMS.get("momentum", {}).get("enabled"):
            f_minute = pool.submit(lambda: fetch_batch_kline(etfs, klt="5min", count=60, max_workers=5))

        prices_batch = f_realtime.result()
        daily_klines = f_daily.result()
        minute_klines = f_minute.result() if f_minute else {}

    # 补充：批量获取失败的，逐个用 fetch_realtime 重试
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

        if code not in price_history:
            price_history[code] = []
        price_history[code].append({"time": now.strftime("%H:%M"), "price": price})
        if len(price_history[code]) > MAX_PRICE_POINTS:
            price_history[code] = price_history[code][-MAX_PRICE_POINTS:]

        df_daily = daily_klines.get(code)
        df_min = minute_klines.get(code)
        signals = _run_strategies_for_etf(code, market, rt, df_daily=df_daily, df_min=df_min)

        sig_objects = [Signal(strategy=s["strategy"], signal=SignalType[s["type"]],
                              reason=s["reason"], confidence=s["confidence"],
                              details=s.get("details", {})) for s in signals]
        combined_type, combined_summary = combine_signals(sig_objects)

        pos = positions.get(code)
        pos_info = None
        pos_obj = None
        if pos and pos.get("shares", 0) > 0:
            p = Position(code=code, cost=pos["cost"], shares=pos["shares"], note=pos.get("note", ""))
            pos_obj = p
            pnl = calc_pnl(p, price)
            pos_info = {**pos, "pnl": pnl["pnl"], "pnl_pct": pnl["pnl_pct"], "market_value": pnl["market_value"]}

        action = suggest_action(code, price, pos_obj, combined_type, sig_objects)

        etf_results.append({
            "code": code, "name": rt.get("name", name), "price": price,
            "open": rt.get("open", 0), "high": rt.get("high", 0),
            "low": rt.get("low", 0), "change_pct": rt.get("change_pct", 0),
            "volume": rt.get("volume", 0), "signals": signals,
            "combined": combined_type.value, "combined_type": combined_type.name,
            "summary": combined_summary, "position": pos_info, "action": action,
            "chart": price_history[code][-60:], "market": market,
        })

        if combined_type.name in ("STRONG_BUY", "STRONG_SELL"):
            # 信号冷却: 同一品种+同类型信号, 间隔不够则跳过提醒
            if not _is_signal_cooled_down(code, combined_type.name):
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
            signal_history.append(alert_entry)
            if len(signal_history) > MAX_HISTORY:
                signal_history.pop(0)

            # 生成推荐单
            direction = "买" if "BUY" in combined_type.name else "卖"
            best_strategy = max(sig_objects, key=lambda s: abs(s.score)).strategy if sig_objects else "综合"
            create_recommendation(
                code=code,
                name=rt.get("name", name),
                direction=direction,
                price=price,
                strategy=best_strategy,
                reason=combined_summary,
                confidence=max(s.confidence for s in sig_objects) if sig_objects else 0.5,
                current_shares=pos.get("shares", 0) if pos else 0,
                cost=pos.get("cost", 0) if pos else 0,
            )

    # 持久化信号
    if alerts:
        _save_signal_history(signal_history)

    # 总盈亏
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
        "history": signal_history[-50:],
    }


# ===================== API =====================
@app.get("/api/kline/{code}")
async def get_kline(code: str,
                    period: str = Query(default="daily", regex="^(daily|weekly|monthly|1min|5min|15min|30min|60min)$"),
                    count: int = Query(default=120, ge=10, le=500),
                    market: str = Query(default="sh")):
    # 从持仓查，没有就用参数自动拼 secid
    secid = None; mkt = market; name = code
    positions = _load_positions_file()
    if code in positions:
        mkt = positions[code].get("market", market)
        name = positions[code].get("name", code)
    secid = f"1.{code}" if mkt == "sh" else f"0.{code}"

    loop = asyncio.get_event_loop()
    if period == "daily":
        df = await loop.run_in_executor(_thread_pool, lambda: fetch_history_kline(code, mkt, count))
    elif "min" in period:
        mins = int(period.replace("min", ""))
        df = await loop.run_in_executor(_thread_pool, lambda: fetch_minute_kline(code, mkt, minutes=mins, count=count))
    else:
        df = await loop.run_in_executor(_thread_pool,
            lambda: fetch_batch_kline([(secid, code, name, mkt)], klt=period, count=count).get(code))

    if df is None or df.empty:
        return {"code": code, "name": name, "data": []}
    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row.get("date", row.get("datetime", ""))),
            "open": round(row["open"], 4), "close": round(row["close"], 4),
            "high": round(row["high"], 4), "low": round(row["low"], 4),
            "volume": int(row["volume"]),
        })
    return {"code": code, "name": name, "period": period, "data": records}


@app.get("/api/realtime/{code}")
async def api_realtime(code: str, market: str = Query(default="sh")):
    """获取单只 ETF 实时行情"""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(_thread_pool, lambda: fetch_realtime(code, market))
    if data and data.get("price", 0) > 0:
        return {"ok": True, "price": data["price"], "change_pct": data.get("change_pct", 0),
                "high": data.get("high", 0), "low": data.get("low", 0), "name": data.get("name", "")}
    return {"ok": False, "price": 0}


@app.get("/api/positions")
async def api_get_positions():
    return _load_positions_file()


@app.post("/api/positions/{code}")
async def api_add_position(code: str, request: Request):
    body = await request.json()
    positions = _load_positions_file()
    positions[code] = {
        "cost": float(body.get("cost", 0)),
        "shares": int(body.get("shares", 0)),
        "name": body.get("name", ""),
        "note": body.get("note", ""),
    }
    _save_positions_file(positions)
    return {"ok": True, "positions": positions}


@app.delete("/api/positions/{code}")
async def api_delete_position(code: str):
    positions = _load_positions_file()
    positions.pop(code, None)
    _save_positions_file(positions)
    return {"ok": True, "positions": positions}


@app.get("/api/search_etf")
async def api_search_etf(q: str = Query(default="", min_length=1)):
    """在线搜索ETF（接东方财富），返回代码/名称/最新价/类型"""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_thread_pool, lambda: _search_etf_online(q))
    return {"query": q, "results": results}


def _search_etf_online(keyword: str) -> list[dict]:
    """通过东方财富搜索接口查找 ETF"""
    try:
        r = cffi_requests.get(
            "https://searchapi.eastmoney.com/api/suggest/get",
            params={
                "input": keyword,
                "type": "14",
                "token": "D43BF722C8E33BDC906FB84D85E326E8",
                "count": "20",
            },
            timeout=5, impersonate="chrome"
        )
        data = r.json()
        items = data.get("QuotationCodeTable", {}).get("Data", [])
        results = []
        t0_list = _get_t0_cache()
        t0_map = {e["code"]: e for e in t0_list}
        for item in items:
            code = item.get("Code", "")
            name = item.get("Name", "")
            mktid = item.get("MktNum", "")
            secid = f"{mktid}.{code}"
            t0_info = t0_map.get(code)
            results.append({
                "code": code,
                "name": name,
                "secid": secid,
                "market": "sh" if str(mktid) == "1" else "sz",
                "is_t0": t0_info is not None,
                "t0_type": t0_info.get("t0_type") if t0_info else None,
            })
        # 批量获取最新价
        if results:
            _fetch_prices_for_search(results)
        return results
    except Exception as e:
        log.warning(f"search_etf error: {e}")
        return []


def _fetch_prices_for_search(results: list[dict]):
    """批量获取搜索结果的最新价（东方财富）"""
    try:
        secids = ",".join(r["secid"] for r in results)
        r = cffi_requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fields": "f2,f3,f12,f14",
                "secids": secids,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            },
            timeout=5, impersonate="chrome"
        )
        items = r.json().get("data", {}).get("diff", [])
        price_map = {}
        for item in items:
            code = item.get("f12", "")
            price = item.get("f2")
            if price and price != "-":
                price_map[code] = price / 1000 if price > 10000 else price
        for res in results:
            res["price"] = price_map.get(res["code"], 0)
    except Exception:
        for res in results:
            res.setdefault("price", 0)


@app.get("/api/signals")
async def api_get_signals(limit: int = Query(default=100, ge=1, le=500)):
    return signal_history[-limit:]


@app.get("/api/t0_etfs")
async def api_get_t0_etfs():
    """获取 T+0 ETF 列表"""
    t0_list = load_t0_list()
    age = None
    try:
        from t0_fetcher import get_update_age
        age = get_update_age()
    except Exception:
        pass
    return {
        "count": len(t0_list),
        "age_hours": round(age, 1) if age is not None else None,
        "etfs": t0_list,
    }


@app.post("/api/t0_etfs/update")
async def api_update_t0_etfs():
    """手动触发更新 T+0 ETF 列表"""
    global _t0_cache, _t0_cache_ts
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_thread_pool, _do_update_t0)
    _t0_cache = result
    _t0_cache_ts = time.time()
    return {"ok": True, "count": len(result), "message": f"已更新 {len(result)} 只 T+0 ETF"}


def _do_update_t0() -> list[dict]:
    etf_list = fetch_all_etf()
    t0_etfs = get_t0_etfs(etf_list)
    save_t0_list(t0_etfs)
    return t0_etfs


# ===================== 交易记录 API =====================
@app.get("/api/trades")
async def api_get_trades():
    """获取所有交易记录"""
    trades = load_trades()
    summary = get_trade_summary()
    return {"trades": trades, "summary": summary}


@app.post("/api/trades")
async def api_add_trade(request: Request):
    """添加一笔交易记录"""
    body = await request.json()
    date = body.get("date", datetime.now().strftime("%Y/%m/%d"))
    code = body.get("code", "")
    name = body.get("name", "")
    direction = body.get("direction", "买")
    buy_price = float(body.get("buy_price", 0))
    sell_price = float(body.get("sell_price", 0))
    shares = int(body.get("shares", 0))
    note = body.get("note", "")

    if not code or shares <= 0:
        return {"ok": False, "error": "代码和仓位不能为空"}

    trade = add_trade(date, code, name, direction, buy_price, sell_price, shares, note)
    summary = get_trade_summary()
    return {"ok": True, "trade": trade, "summary": summary}


@app.delete("/api/trades/{trade_id}")
async def api_delete_trade(trade_id: int):
    """删除一笔交易记录"""
    ok = delete_trade(trade_id)
    summary = get_trade_summary()
    return {"ok": ok, "summary": summary}


@app.put("/api/trades/{trade_id}")
async def api_update_trade(trade_id: int, request: Request):
    """更新交易记录"""
    body = await request.json()
    trade = update_trade(trade_id, body)
    summary = get_trade_summary()
    return {"ok": trade is not None, "trade": trade, "summary": summary}


# ===================== 推荐单 API =====================
@app.get("/api/recommendations")
async def api_get_recommendations():
    """获取待确认推荐 + 已处理推荐"""
    pending = get_pending()
    all_recs = get_all()
    recent = [r for r in all_recs if r.get("status") != "pending"][-20:]  # 最近20条已处理
    return {"pending": pending, "recent": recent, "pending_count": len(pending)}


@app.post("/api/recommendations/{rec_id}/confirm")
async def api_confirm_recommendation(rec_id: int, request: Request):
    """确认推荐 → 自动写入交易记录"""
    body = await request.json()
    actual_price = float(body.get("actual_price", 0))
    actual_shares = int(body.get("actual_shares", 0))
    note = body.get("note", "")

    if actual_price <= 0 or actual_shares <= 0:
        return {"ok": False, "error": "实际价格和仓位不能为空"}

    trade = confirm_recommendation(rec_id, actual_price, actual_shares, note)
    summary = get_trade_summary()
    return {"ok": trade is not None, "trade": trade, "summary": summary}


@app.post("/api/recommendations/{rec_id}/ignore")
async def api_ignore_recommendation(rec_id: int):
    """忽略推荐"""
    ok = ignore_recommendation(rec_id)
    return {"ok": ok}


@app.post("/api/backtest")
async def api_backtest(request: Request):
    body = await request.json()
    code = body.get("code", "")
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    initial_capital = float(body.get("initial_capital", 100000))

    # 从持仓查，没有就用参数自动拼 secid
    market = "sh"; name = code
    positions = _load_positions_file()
    if code in positions:
        market = positions[code].get("market", "sh")
        name = positions[code].get("name", code)
    secid = f"1.{code}" if market == "sh" else f"0.{code}"

    # 拉日K线（默认拉足够多，后面按日期截取）
    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(_thread_pool, lambda: fetch_history_kline(code, market, 500))

    if df is None or df.empty:
        return {"error": "无法获取K线数据"}

    # 按日期范围截取
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    if df.empty:
        return {"error": "所选日期范围内无K线数据"}

    # 跑全部策略
    results = []
    for key, fn in STRATEGY_FNS.items():
        try:
            r = await loop.run_in_executor(_thread_pool,
                lambda f=fn: run_backtest(df, f, {}, initial_capital))
            r["strategy"] = key
            results.append(r)
        except Exception as e:
            results.append({"strategy": key, "error": str(e)})

    return {
        "code": code, "name": name,
        "start_date": str(df.iloc[0]["date"])[:10],
        "end_date": str(df.iloc[-1]["date"])[:10],
        "bars": len(df),
        "strategies": results,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(ws)


async def data_loop():
    while True:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(_thread_pool, collect_data)
            msg = json.dumps(data, ensure_ascii=False)
            disconnected = set()
            for client in connected_clients:
                try:
                    await client.send_text(msg)
                except Exception:
                    disconnected.add(client)
            connected_clients.difference_update(disconnected)
        except Exception as e:
            log.error(f"data_loop error: {e}")
        interval = RUN_CONFIG["refresh_seconds"] if is_market_open() else 60
        await asyncio.sleep(interval)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF T+0 信号仪表盘</title>
<style>
:root{--bg:#0f1117;--card:#1a1d28;--card-hover:#1e2130;--border:#2a2d3a;--text:#e0e0e0;--dim:#888;--red:#ef4444;--green:#22c55e;--blue:#3b82f6;--yellow:#eab308;--cyan:#06b6d4;--purple:#a855f7}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,'SF Pro','Helvetica Neue','PingFang SC',sans-serif;padding:12px;min-height:100vh}

/* ===== Header ===== */
.header{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:var(--card);border:1px solid var(--border);border-radius:12px;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.header h1{font-size:18px;font-weight:700;background:linear-gradient(135deg,var(--cyan),var(--blue));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px;animation:pulse 2s infinite}
.status-dot.open{background:var(--green)}.status-dot.closed{background:var(--red);animation:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
.time-display{font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums}
.total-pnl{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}
.conn-status{font-size:11px;padding:2px 8px;border-radius:6px}
.conn-connected{background:rgba(34,197,94,0.15);color:var(--green)}
.conn-disconnected{background:rgba(239,68,68,0.15);color:var(--red)}

/* ===== Tabs ===== */
.tabs{display:flex;gap:4px;margin-bottom:12px;overflow-x:auto}
.tab{padding:8px 20px;border-radius:10px;border:1px solid var(--border);background:transparent;color:var(--dim);cursor:pointer;font-size:14px;transition:all .2s;white-space:nowrap}
.tab:hover{border-color:var(--cyan);color:var(--text)}
.tab.active{background:var(--cyan);color:#000;border-color:var(--cyan);font-weight:600}

/* ===== Tab Content ===== */
.tab-content{display:none}.tab-content.active{display:block}

/* ===== Alert ===== */
.alert-panel{margin-bottom:12px}
.alert-item{display:flex;align-items:center;gap:10px;padding:8px 14px;background:var(--card);border-radius:10px;margin-bottom:4px;border:1px solid var(--border);animation:slideIn .3s ease;font-size:13px}
@keyframes slideIn{from{opacity:0;transform:translateX(-20px)}to{opacity:1;transform:translateX(0)}}
.alert-icon{font-size:18px}.alert-time{color:var(--dim);font-size:11px;min-width:60px}

/* ===== Grid ===== */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:10px;margin-bottom:12px}

/* ===== ETF Card ===== */
.etf-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;transition:all .2s;cursor:pointer;position:relative}
.etf-card:hover{border-color:var(--cyan);background:var(--card-hover)}
.etf-card.signal-strong-buy{border-left:3px solid var(--green);box-shadow:inset 0 0 20px rgba(34,197,94,0.05)}
.etf-card.signal-strong-sell{border-left:3px solid var(--red);box-shadow:inset 0 0 20px rgba(239,68,68,0.05)}
.etf-card.signal-buy{border-left:3px solid var(--green)}.etf-card.signal-sell{border-left:3px solid var(--red)}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.card-name{font-size:14px;font-weight:600}.card-code{font-size:11px;color:var(--dim);margin-top:2px}
.card-price{text-align:right;font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.card-change{font-size:12px;font-weight:500;font-variant-numeric:tabular-nums}
.up{color:var(--red)}.down{color:var(--green)}.flat{color:var(--dim)}
.sparkline{height:36px;margin:6px 0}.sparkline canvas{width:100%;height:100%}
.signal-badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;margin-bottom:6px}
.badge-STRONG_BUY{background:rgba(34,197,94,0.15);color:var(--green)}.badge-BUY{background:rgba(59,130,246,0.15);color:var(--blue)}
.badge-HOLD{background:rgba(136,136,136,0.15);color:var(--dim)}.badge-SELL{background:rgba(234,179,8,0.15);color:var(--yellow)}
.badge-STRONG_SELL{background:rgba(239,68,68,0.15);color:var(--red)}
.signal-list{display:flex;flex-direction:column;gap:3px}
.signal-item{display:flex;align-items:center;gap:6px;font-size:11px;padding:3px 0}
.signal-icon{font-size:12px;flex-shrink:0}.signal-strategy{color:var(--dim);min-width:50px}.signal-reason{flex:1}
.confidence-bar{display:inline-block;width:36px;height:3px;background:var(--border);border-radius:2px;overflow:hidden;flex-shrink:0}
.confidence-fill{height:100%;border-radius:2px}
.position-info{margin-top:6px;padding-top:6px;border-top:1px solid var(--border);font-size:11px;display:flex;gap:10px;color:var(--dim)}
.position-info .pnl-val{font-weight:600}
.action-tip{margin-top:6px;padding:6px 10px;background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.2);border-radius:8px;font-size:12px;color:var(--cyan);line-height:1.5}

/* ===== Recommendation Cards ===== */
@keyframes borderGlow {
  0%{background-position:0% 50%}
  50%{background-position:100% 50%}
  100%{background-position:0% 50%}
}
@keyframes pulseGlow {
  0%,100%{box-shadow:0 0 8px var(--glow-color,rgba(6,182,212,0.3))}
  50%{box-shadow:0 0 20px var(--glow-color,rgba(6,182,212,0.5))}
}
.etf-card.has-rec{position:relative;padding:2px;border-radius:14px;animation:pulseGlow 2.5s ease-in-out infinite}
.etf-card.has-rec.rec-buy{--glow-color:rgba(34,197,94,0.4);background:linear-gradient(135deg,#22c55e,#06b6d4,#3b82f6,#22c55e);background-size:300% 300%;animation:borderGlow 3s ease infinite,pulseGlow 2.5s ease-in-out infinite}
.etf-card.has-rec.rec-sell{--glow-color:rgba(239,68,68,0.4);background:linear-gradient(135deg,#ef4444,#f59e0b,#ef4444,#f59e0b);background-size:300% 300%;animation:borderGlow 3s ease infinite,pulseGlow 2.5s ease-in-out infinite}
.etf-card.has-rec .etf-card-inner{background:var(--card);border-radius:12px;padding:14px;height:100%}

.rec-section{margin-top:10px;padding-top:10px;border-top:1px dashed var(--border)}
.rec-header{display:flex;align-items:center;gap:6px;margin-bottom:8px}
.rec-badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:0.5px}
.rec-badge.buy{background:linear-gradient(135deg,rgba(34,197,94,0.15),rgba(6,182,212,0.15));color:var(--green);border:1px solid rgba(34,197,94,0.3)}
.rec-badge.sell{background:linear-gradient(135deg,rgba(239,68,68,0.15),rgba(245,158,11,0.15));color:var(--red);border:1px solid rgba(239,68,68,0.3)}
.rec-meta{font-size:11px;color:var(--dim);line-height:1.6}
.rec-meta b{color:var(--text);font-weight:600}
.rec-meta .conf-bar{display:inline-block;letter-spacing:-1px;font-size:9px;margin-left:2px}
.rec-form{display:flex;gap:8px;align-items:flex-end;margin-top:8px;flex-wrap:wrap}
.rec-field{display:flex;flex-direction:column;gap:3px}
.rec-field label{font-size:10px;color:var(--dim);white-space:nowrap}
.rec-field input{padding:5px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:12px;width:95px;text-align:right;font-variant-numeric:tabular-nums}
.rec-field input:focus{border-color:var(--cyan);outline:none}
.rec-btns{display:flex;gap:6px;margin-left:auto}
.rec-btn{padding:6px 16px;border-radius:8px;border:none;font-size:12px;font-weight:600;cursor:pointer;transition:all .2s;white-space:nowrap}
.rec-btn-confirm{background:linear-gradient(135deg,#22c55e,#06b6d4);color:#000}
.rec-btn-confirm:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(34,197,94,0.3)}
.rec-btn-ignore{background:var(--border);color:var(--dim)}
.rec-btn-ignore:hover{background:rgba(255,255,255,0.1);color:var(--text)}

/* ===== Section ===== */
.section-title{font-size:14px;font-weight:600;margin:14px 0 8px;display:flex;align-items:center;gap:8px}

/* ===== History Table ===== */
.history-table{width:100%;border-collapse:collapse;font-size:12px}
.history-table th{text-align:left;color:var(--dim);font-weight:500;padding:5px 10px;border-bottom:1px solid var(--border)}
.history-table td{padding:5px 10px;border-bottom:1px solid rgba(42,45,58,0.5)}

/* ===== Positions Tab ===== */
.pos-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.pos-header h2{font-size:16px;font-weight:600}
.btn{padding:6px 16px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text);cursor:pointer;font-size:13px;transition:all .2s}
.btn:hover{border-color:var(--cyan)}.btn-primary{background:var(--cyan);color:#000;border-color:var(--cyan);font-weight:600}
.btn-danger{border-color:var(--red);color:var(--red)}.btn-danger:hover{background:var(--red);color:#fff}
.pos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.pos-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px}
.pos-card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.pos-card-name{font-size:15px;font-weight:600}.pos-card-code{font-size:12px;color:var(--dim)}
.pos-card-body{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px}
.pos-label{color:var(--dim);font-size:11px}.pos-value{font-weight:500;font-variant-numeric:tabular-nums}
.pos-card-actions{margin-top:10px;display:flex;gap:6px}

/* ===== Backtest Tab ===== */
.bt-form{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px}
.bt-field{display:flex;flex-direction:column;gap:4px}
.bt-field label{font-size:11px;color:var(--dim)}
.bt-field select,.bt-field input{padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:13px;outline:none}
.bt-field select:focus,.bt-field input:focus{border-color:var(--cyan)}
.bt-results{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:16px}
.bt-metric{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center}
.bt-metric-value{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.bt-metric-label{font-size:11px;color:var(--dim);margin-top:4px}
.bt-trades{font-size:12px}
.bt-equity{height:200px;margin:12px 0}
.bt-equity canvas{width:100%;height:100%}
.bt-loading{display:flex;justify-content:center;align-items:center;height:200px;color:var(--dim)}

/* ===== K线弹窗 ===== */
.kline-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:1000;justify-content:center;align-items:center}
.kline-overlay.show{display:flex}
.kline-modal{background:var(--card);border:1px solid var(--border);border-radius:16px;width:92vw;max-width:1000px;max-height:92vh;overflow-y:auto;padding:16px}
.kline-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.kline-title{font-size:16px;font-weight:700}
.kline-close{background:none;border:1px solid var(--border);color:var(--text);width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center}
.kline-close:hover{background:var(--border)}
.period-tabs{display:flex;gap:4px;margin-bottom:12px;overflow-x:auto}
.period-tab{padding:5px 14px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--dim);cursor:pointer;font-size:12px;transition:all .2s;white-space:nowrap}
.period-tab:hover{border-color:var(--cyan);color:var(--text)}
.period-tab.active{background:var(--cyan);color:#000;border-color:var(--cyan);font-weight:600}
.kline-chart{width:100%;position:relative}
.kline-chart canvas{width:100%;display:block;border-radius:8px}
.kline-loading{display:flex;justify-content:center;align-items:center;height:300px;color:var(--dim);font-size:14px}
.kline-info{position:absolute;top:8px;left:12px;font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums;pointer-events:none}

/* ===== Modal ===== */
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:900;justify-content:center;align-items:center}
.modal-overlay.show{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:16px;width:90vw;max-width:400px;padding:20px}
.modal h3{font-size:16px;font-weight:600;margin-bottom:14px}
.modal-field{margin-bottom:10px}
.modal-field label{display:block;font-size:12px;color:var(--dim);margin-bottom:4px}
.modal-field input{width:100%;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;outline:none}
.modal-field input:focus{border-color:var(--cyan)}
.modal-field select{width:100%;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;outline:none}

/* ===== Search Select ===== */
.search-select{position:relative}
.search-select input{width:100%;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;outline:none}
.search-select input:focus{border-color:var(--cyan)}
.search-dropdown{display:none;position:absolute;top:calc(100% + 4px);left:0;right:0;max-height:220px;overflow-y:auto;background:var(--card);border:1px solid var(--border);border-radius:8px;z-index:10;box-shadow:0 8px 24px rgba(0,0,0,0.4)}
.search-dropdown.show{display:block}
.search-item{padding:8px 12px;cursor:pointer;font-size:13px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(42,45,58,0.4)}
.search-item:last-child{border-bottom:none}
.search-item:hover,.search-item.active{background:rgba(6,182,212,0.12)}
.search-item-code{color:var(--cyan);font-weight:600;font-variant-numeric:tabular-nums}
.search-item-name{color:var(--dim);flex:1;margin-left:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.search-item-type{font-size:10px;color:var(--dim);padding:2px 6px;border-radius:4px;background:rgba(136,136,136,0.1);margin-left:6px;white-space:nowrap}
.search-empty{padding:12px;text-align:center;color:var(--dim);font-size:12px}
.modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}

/* ===== Responsive ===== */
@media(max-width:768px){
  body{padding:8px}
  .header{padding:8px 12px}.header h1{font-size:15px}
  .header-right{gap:8px}
  .grid{grid-template-columns:1fr}
  .pos-grid{grid-template-columns:1fr}
  .kline-modal{width:100vw;height:100vh;max-width:none;max-height:none;border-radius:0}
  .bt-form{flex-direction:column}
  .bt-field{width:100%}
  .bt-field select,.bt-field input{width:100%}
  .tab{padding:6px 14px;font-size:13px}
  .bt-results{grid-template-columns:repeat(2,1fr)}
}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <h1>📊 ETF T+0 信号仪表盘</h1>
  <div class="header-right">
    <div class="total-pnl" id="totalPnl">--</div>
    <div><span class="status-dot" id="statusDot"></span><span id="marketStatus">连接中...</span></div>
    <div class="time-display" id="updateTime">--</div>
    <span class="conn-status conn-disconnected" id="connStatus">未连接</span>
  </div>
</div>

<!-- Tabs -->
<div class="tabs">
  <button class="tab active" data-tab="dashboard">📡 信号监控</button>
  <button class="tab" data-tab="positions">💼 我的持仓</button>
  <button class="tab" data-tab="backtest">📈 策略回测</button>
</div>

<!-- Tab: Dashboard -->
<div class="tab-content active" id="tab-dashboard">
  <div class="alert-panel" id="alertPanel"></div>
  <div id="recStandalone" style="margin-bottom:12px"></div>
  <div class="grid" id="etfGrid"></div>
  <div id="tradeSection" style="margin-top:16px">
    <div class="pos-header">
      <h2>📝 实盘交易记录</h2>
      <div style="display:flex;gap:8px;align-items:center">
        <div id="tradeSummary" style="font-size:13px;color:var(--dim)"></div>
        <button class="btn btn-primary" onclick="showAddTrade()">+ 记录交易</button>
      </div>
    </div>
    <div style="overflow-x:auto">
      <table class="history-table" id="tradeTable">
        <thead><tr>
          <th>日期</th><th>代码</th><th>名称</th><th>方向</th>
          <th>买价</th><th>卖价</th><th>仓位</th><th>手续费</th>
          <th>盈亏</th><th>盈亏比</th><th>累计盈亏</th><th>备注</th><th></th>
        </tr></thead>
        <tbody id="tradeBody"></tbody>
      </table>
    </div>
  </div>
</div>
<div class="tab-content" id="tab-positions">
  <div class="pos-header">
    <h2>💼 持仓管理</h2>
    <button class="btn btn-primary" onclick="showAddPosition()">+ 添加持仓</button>
  </div>
  <div class="pos-grid" id="posGrid"><div class="bt-loading">加载中...</div></div>
</div>

<!-- Tab: Backtest -->
<div class="tab-content" id="tab-backtest">
  <div class="bt-form">
    <div class="bt-field"><label>品种</label>
      <div class="search-select" id="btCodeWrap">
        <input type="text" id="btCode" placeholder="输入代码或名称搜索，如 纳指、518、黄金" autocomplete="off">
        <div class="search-dropdown" id="btCodeDropdown"></div>
      </div>
    </div>
    <div class="bt-field"><label>开始日期</label><input type="date" id="btStartDate"></div>
    <div class="bt-field"><label>结束日期</label><input type="date" id="btEndDate"></div>
    <div class="bt-field"><label>初始资金</label><input type="number" id="btCapital" value="100000"></div>
    <button class="btn btn-primary" onclick="runBacktest()">▶ 开始回测</button>
  </div>
  <div id="btResults"></div>
</div>

<!-- K线弹窗 -->
<div class="kline-overlay" id="klineOverlay">
  <div class="kline-modal">
    <div class="kline-header">
      <div class="kline-title" id="klineTitle">--</div>
      <button class="kline-close" onclick="closeKline()">✕</button>
    </div>
    <div class="period-tabs" id="periodTabs">
      <button class="period-tab active" data-period="5min">分时</button>
      <button class="period-tab" data-period="daily">日K</button>
      <button class="period-tab" data-period="weekly">周K</button>
      <button class="period-tab" data-period="monthly">月K</button>
    </div>
    <div class="kline-chart" id="klineChart">
      <div class="kline-loading">加载中...</div>
    </div>
  </div>
</div>

<!-- 添加/编辑持仓弹窗 -->
<div class="modal-overlay" id="posModal">
  <div class="modal">
    <h3 id="posModalTitle">添加持仓</h3>
    <div class="modal-field"><label>🔍 搜索 ETF</label>
      <div class="search-select" id="posCodeWrap">
        <input type="text" id="posCode" placeholder="输入代码或名称在线搜索，如 纳指、518、黄金" autocomplete="off">
        <div class="search-dropdown" id="posCodeDropdown"></div>
      </div>
    </div>
    <div class="modal-field"><label>名称</label><input type="text" id="posName" placeholder="选择后自动填入" readonly></div>
    <div class="modal-field"><label>最新价（成本价）</label><input type="number" step="0.001" id="posCost" placeholder="选择后自动填入当前价"></div>
    <div class="modal-field"><label>持仓数量</label><input type="number" id="posShares" placeholder="输入持仓数量，如 10000"></div>
    <div class="modal-field"><label>备注</label><input type="text" id="posNote" placeholder="如 纳指底仓"></div>
    <div class="modal-actions">
      <button class="btn" onclick="closePosModal()">取消</button>
      <button class="btn btn-primary" onclick="savePosition()">保存</button>
    </div>
  </div>
</div>

<!-- 添加交易记录弹窗 -->
<div class="modal-overlay" id="tradeModal">
  <div class="modal">
    <h3 id="tradeModalTitle">记录交易</h3>
    <div class="modal-field"><label>日期</label><input type="date" id="tradeDate"></div>
    <div class="modal-field"><label>🔍 搜索 ETF</label>
      <div class="search-select" id="tradeCodeWrap">
        <input type="text" id="tradeCode" placeholder="输入代码或名称搜索，如 纳指、513300" autocomplete="off">
        <div class="search-dropdown" id="tradeCodeDropdown"></div>
      </div>
    </div>
    <div class="modal-field"><label>名称</label><input type="text" id="tradeName" placeholder="选择后自动填入" readonly></div>
    <div class="modal-field"><label>方向</label>
      <select id="tradeDirection">
        <option value="买">实际买</option>
        <option value="卖">实际卖</option>
      </select>
    </div>
    <div class="modal-field"><label>实际买价</label><input type="number" step="0.001" id="tradeBuyPrice" placeholder="买入价格"></div>
    <div class="modal-field" id="tradeSellPriceField"><label>实际卖价</label><input type="number" step="0.001" id="tradeSellPrice" placeholder="卖出价格（选"卖"时填）"></div>
    <div class="modal-field"><label>实际仓位（股数）</label><input type="number" id="tradeShares" placeholder="如 10000"></div>
    <div class="modal-field"><label>备注</label><input type="text" id="tradeNote" placeholder="可选"></div>
    <div class="modal-actions">
      <button class="btn" onclick="closeTradeModal()">取消</button>
      <button class="btn btn-primary" onclick="saveTrade()">保存</button>
    </div>
  </div>
</div>

<script>
// ==================== 交易记录 ====================
let tradeSearchTimer = null;
let tradeSelectedMarket = '';
let tradeSearchIdx = -1;
const tradeCodeInput = document.getElementById('tradeCode');
const tradeDropdown = document.getElementById('tradeCodeDropdown');

// 方向切换：显示/隐藏卖价
document.getElementById('tradeDirection').addEventListener('change', function() {
  const isSell = this.value === '卖';
  const sellField = document.getElementById('tradeSellPriceField');
  sellField.style.display = isSell ? '' : 'none';
});

async function tradeSearchEtf(query) {
  query = (query || '').trim();
  if (query.length < 1) { tradeDropdown.classList.remove('show'); return; }
  tradeDropdown.innerHTML = `<div class="search-empty">🔍 搜索中...</div>`;
  tradeDropdown.classList.add('show');
  tradeSearchIdx = -1;
  try {
    const r = await fetch(`/api/search_etf?q=${encodeURIComponent(query)}`);
    const data = await r.json();
    const items = data.results || [];
    if (!items.length) {
      tradeDropdown.innerHTML = `<div class="search-empty">未找到 "${query}"</div>`;
    } else {
      tradeDropdown.innerHTML = items.map((e, i) => {
        const safeName = (e.name || '').replace(/'/g, "\\'");
        const price = e.price ? e.price.toFixed(3) : '--';
        return `<div class="search-item" data-idx="${i}"
          onclick="tradeSelectEtf('${e.code}','${safeName}',${e.price||0},'${e.market||''}')">
          <span class="search-item-code">${e.code}</span>
          <span class="search-item-name">${e.name}</span>
          <span class="search-item-type">${price}</span>
        </div>`;
      }).join('');
    }
  } catch(err) { tradeDropdown.innerHTML = `<div class="search-empty">搜索失败</div>`; }
  tradeDropdown.classList.add('show');
}

function tradeSelectEtf(code, name, price, market) {
  tradeCodeInput.value = code;
  document.getElementById('tradeName').value = name || '';
  tradeSelectedMarket = market || '';
  if (price && price > 0) {
    document.getElementById('tradeBuyPrice').value = price.toFixed(3);
  }
  tradeDropdown.classList.remove('show');
  document.getElementById('tradeShares').focus();
}

tradeCodeInput.addEventListener('input', () => {
  clearTimeout(tradeSearchTimer);
  tradeSearchTimer = setTimeout(() => tradeSearchEtf(tradeCodeInput.value), 300);
});
tradeCodeInput.addEventListener('focus', () => { if (tradeCodeInput.value.trim()) tradeSearchEtf(tradeCodeInput.value); });
tradeCodeInput.addEventListener('keydown', e => {
  const items = tradeDropdown.querySelectorAll('.search-item');
  if (!items.length || !tradeDropdown.classList.contains('show')) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); tradeSearchIdx = Math.min(tradeSearchIdx+1, items.length-1); items.forEach((el,i)=>el.classList.toggle('active',i===tradeSearchIdx)); if(items[tradeSearchIdx]) items[tradeSearchIdx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); tradeSearchIdx = Math.max(tradeSearchIdx-1, 0); items.forEach((el,i)=>el.classList.toggle('active',i===tradeSearchIdx)); if(items[tradeSearchIdx]) items[tradeSearchIdx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'Enter' && tradeSearchIdx >= 0) { e.preventDefault(); items[tradeSearchIdx].click(); }
  else if (e.key === 'Escape') { tradeDropdown.classList.remove('show'); }
});
document.addEventListener('click', e => {
  if (!document.getElementById('tradeCodeWrap').contains(e.target)) tradeDropdown.classList.remove('show');
});

function showAddTrade() {
  document.getElementById('tradeModalTitle').textContent = '记录交易';
  document.getElementById('tradeDate').value = new Date().toISOString().slice(0, 10);
  document.getElementById('tradeCode').value = '';
  document.getElementById('tradeCode').disabled = false;
  document.getElementById('tradeName').value = '';
  document.getElementById('tradeDirection').value = '买';
  document.getElementById('tradeSellPriceField').style.display = 'none';
  document.getElementById('tradeBuyPrice').value = '';
  document.getElementById('tradeSellPrice').value = '';
  document.getElementById('tradeShares').value = '';
  document.getElementById('tradeNote').value = '';
  tradeSelectedMarket = '';
  document.getElementById('tradeModal').classList.add('show');
  setTimeout(() => document.getElementById('tradeDate').focus(), 100);
}

function closeTradeModal() {
  document.getElementById('tradeModal').classList.remove('show');
  tradeSelectedMarket = '';
}
document.getElementById('tradeModal').addEventListener('click', e => { if(e.target.id==='tradeModal') closeTradeModal(); });

function quickTrade(code, name, direction, buyPrice, sellPrice, shares) {
  // 从信号提醒快速记录交易
  document.getElementById('tradeModalTitle').textContent = direction === '买' ? '🟢 实际买入' : '🔴 实际卖出';
  document.getElementById('tradeDate').value = new Date().toISOString().slice(0, 10);
  document.getElementById('tradeCode').value = code;
  document.getElementById('tradeCode').disabled = true;
  document.getElementById('tradeName').value = name || code;
  document.getElementById('tradeDirection').value = direction;
  document.getElementById('tradeBuyPrice').value = buyPrice > 0 ? buyPrice.toFixed(3) : '';
  document.getElementById('tradeSellPriceField').style.display = direction === '卖' ? '' : 'none';
  document.getElementById('tradeSellPrice').value = sellPrice > 0 ? sellPrice.toFixed(3) : '';
  document.getElementById('tradeShares').value = shares > 0 ? shares : '';
  document.getElementById('tradeNote').value = direction === '买' ? '信号买入' : '信号卖出';
  tradeSelectedMarket = '';
  document.getElementById('tradeModal').classList.add('show');
  if (shares > 0) {
    document.getElementById(direction === '卖' ? 'tradeSellPrice' : 'tradeBuyPrice').focus();
  } else {
    document.getElementById('tradeShares').focus();
  }
}

async function saveTrade() {
  const date = document.getElementById('tradeDate').value;
  const code = document.getElementById('tradeCode').value.trim();
  const name = document.getElementById('tradeName').value.trim();
  const direction = document.getElementById('tradeDirection').value;
  const buy_price = parseFloat(document.getElementById('tradeBuyPrice').value) || 0;
  const sell_price = parseFloat(document.getElementById('tradeSellPrice').value) || 0;
  const shares = parseInt(document.getElementById('tradeShares').value) || 0;
  const note = document.getElementById('tradeNote').value;

  if (!code || code.length < 5) { alert('请输入有效的ETF代码'); return; }
  if (buy_price <= 0) { alert('请填写实际买价'); return; }
  if (direction === '卖' && sell_price <= 0) { alert('卖出时请填写实际卖价'); return; }
  if (shares <= 0) { alert('请填写仓位（股数）'); return; }

  // 格式化日期
  const dateStr = date.replace(/-/g, '/');

  await fetch('/api/trades', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({date: dateStr, code, name, direction, buy_price, sell_price, shares, note}),
  });
  closeTradeModal();
  loadTrades();
}

async function deleteTrade(id) {
  if (!confirm('确认删除这条交易记录？')) return;
  await fetch(`/api/trades/${id}`, {method: 'DELETE'});
  loadTrades();
}

async function loadTrades() {
  try {
    const resp = await fetch('/api/trades');
    const data = await resp.json();
    const trades = data.trades || [];
    const summary = data.summary || {};

    // 汇总信息
    const sumEl = document.getElementById('tradeSummary');
    if (summary.total_trades > 0) {
      const pnlCl = summary.total_pnl >= 0 ? 'var(--red)' : 'var(--green)';
      sumEl.innerHTML = `共 <b>${summary.total_trades}</b> 笔卖出 · 盈亏 <b style="color:${pnlCl}">¥${summary.total_pnl>=0?'+':''}${summary.total_pnl.toFixed(2)}</b> · 胜率 <b>${summary.win_rate}%</b> (${summary.win_count}胜${summary.lose_count}负)`;
    } else {
      sumEl.textContent = '';
    }

    // 表格
    const body = document.getElementById('tradeBody');
    if (!trades.length) {
      body.innerHTML = '<tr><td colspan="13" style="text-align:center;color:var(--dim);padding:40px">暂无交易记录，点击右上角「+ 记录交易」添加</td></tr>';
      return;
    }

    body.innerHTML = trades.slice().reverse().map(t => {
      const dirCl = t.direction === '买' ? 'var(--green)' : 'var(--red)';
      const dirIcon = t.direction === '买' ? '🟢' : '🔴';
      const pnlCl = t.pnl > 0 ? 'var(--red)' : t.pnl < 0 ? 'var(--green)' : 'var(--dim)';
      const cumCl = t.cumulative_pnl > 0 ? 'var(--red)' : t.cumulative_pnl < 0 ? 'var(--green)' : 'var(--dim)';
      return `<tr>
        <td style="color:var(--dim);white-space:nowrap">${t.date}</td>
        <td>${t.code}</td>
        <td>${t.name}</td>
        <td style="color:${dirCl};font-weight:600;white-space:nowrap">${dirIcon} ${t.direction === '买' ? '实际买' : '实际卖'}</td>
        <td style="font-variant-numeric:tabular-nums">${t.buy_price > 0 ? t.buy_price.toFixed(3) : '--'}</td>
        <td style="font-variant-numeric:tabular-nums">${t.sell_price > 0 ? t.sell_price.toFixed(3) : '--'}</td>
        <td style="font-variant-numeric:tabular-nums">${t.shares.toLocaleString()}</td>
        <td style="color:var(--dim);font-variant-numeric:tabular-nums">${t.commission > 0 ? '¥'+t.commission.toFixed(2) : '--'}</td>
        <td style="color:${pnlCl};font-weight:600;font-variant-numeric:tabular-nums">${t.direction==='卖'?(t.pnl>=0?'+':'')+t.pnl.toFixed(0):'--'}</td>
        <td style="color:${pnlCl};font-variant-numeric:tabular-nums">${t.pnl_pct!==0?(t.pnl_pct>=0?'+':'')+t.pnl_pct.toFixed(2)+'%':'--'}</td>
        <td style="color:${cumCl};font-weight:600;font-variant-numeric:tabular-nums">${t.cumulative_pnl>=0?'+':''}${t.cumulative_pnl.toFixed(0)}</td>
        <td style="color:var(--dim);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.note||''}</td>
        <td><button class="btn btn-danger" style="padding:2px 8px;font-size:11px" onclick="deleteTrade(${t.id})">删</button></td>
      </tr>`;
    }).join('');
  } catch(e) {
    document.getElementById('tradeBody').innerHTML = `<tr><td colspan="13" style="text-align:center;color:var(--red)">加载失败</td></tr>`;
  }
}

// ==================== Tabs ====================
const btCodeInput = document.getElementById('btCode');
const btCodeDropdown = document.getElementById('btCodeDropdown');
let btSearchIdx = -1;
let btSearchTimer = null;
let btSelectedMarket = '';

async function btSearchEtf(query) {
  query = (query || '').trim();
  if (query.length < 1) { btCodeDropdown.classList.remove('show'); return; }
  btCodeDropdown.innerHTML = `<div class="search-empty">🔍 搜索中...</div>`;
  btCodeDropdown.classList.add('show');
  btSearchIdx = -1;
  try {
    const r = await fetch(`/api/search_etf?q=${encodeURIComponent(query)}`);
    const data = await r.json();
    const items = data.results || [];
    if (!items.length) {
      btCodeDropdown.innerHTML = `<div class="search-empty">未找到 "${query}" 相关 ETF</div>`;
    } else {
      btCodeDropdown.innerHTML = items.map((e, i) => {
        const safeName = (e.name || '').replace(/'/g, "\\'");
        const price = e.price ? e.price.toFixed(3) : '--';
        const t0Badge = e.is_t0 ? `<span class="search-item-type" style="background:rgba(34,197,94,0.15);color:var(--green)">T+0</span>` : `<span class="search-item-type">T+1</span>`;
        return `<div class="search-item" data-idx="${i}"
          onclick="btSelectEtf('${e.code}','${safeName}','${e.market||''}')">
          <span class="search-item-code">${e.code}</span>
          <span class="search-item-name">${e.name}</span>
          ${t0Badge}
          <span class="search-item-type">${price}</span>
        </div>`;
      }).join('');
    }
  } catch(err) { btCodeDropdown.innerHTML = `<div class="search-empty">搜索失败</div>`; }
  btCodeDropdown.classList.add('show');
}

function btSelectEtf(code, name, market) {
  btCodeInput.value = `${code} ${name}`;
  btCodeInput.dataset.code = code;
  btCodeInput.dataset.name = name;
  btSelectedMarket = market || '';
  btCodeDropdown.classList.remove('show');
}

btCodeInput.addEventListener('input', () => {
  clearTimeout(btSearchTimer);
  btSearchTimer = setTimeout(() => btSearchEtf(btCodeInput.value), 300);
});
btCodeInput.addEventListener('focus', () => { if (btCodeInput.value.trim()) btSearchEtf(btCodeInput.value); });
btCodeInput.addEventListener('keydown', e => {
  const items = btCodeDropdown.querySelectorAll('.search-item');
  if (!items.length || !btCodeDropdown.classList.contains('show')) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); btSearchIdx = Math.min(btSearchIdx+1, items.length-1); items.forEach((el,i)=>el.classList.toggle('active',i===btSearchIdx)); if(items[btSearchIdx]) items[btSearchIdx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); btSearchIdx = Math.max(btSearchIdx-1, 0); items.forEach((el,i)=>el.classList.toggle('active',i===btSearchIdx)); if(items[btSearchIdx]) items[btSearchIdx].scrollIntoView({block:'nearest'}); }
  else if (e.key === 'Enter' && btSearchIdx >= 0) { e.preventDefault(); items[btSearchIdx].click(); }
  else if (e.key === 'Escape') { btCodeDropdown.classList.remove('show'); }
});
document.addEventListener('click', e => {
  if (!document.getElementById('btCodeWrap').contains(e.target)) btCodeDropdown.classList.remove('show');
});

// 设置默认日期（近一年）
const today = new Date(); const oneYearAgo = new Date(today); oneYearAgo.setFullYear(today.getFullYear()-1);
document.getElementById('btEndDate').value = today.toISOString().slice(0,10);
document.getElementById('btStartDate').value = oneYearAgo.toISOString().slice(0,10);

// ==================== 持仓搜索 ====================
const posCodeEl = document.getElementById('posCode');
const posDropdown = document.getElementById('posCodeDropdown');
let searchIdx = -1;
let searchTimer = null;
let selectedPosMarket = '';

// ==================== 在线搜索 ETF ====================
async function searchEtfOnline(query) {
  query = (query || '').trim();
  if (query.length < 1) {
    posDropdown.classList.remove('show');
    return;
  }
  // 显示加载状态
  posDropdown.innerHTML = `<div class="search-empty">🔍 搜索中...</div>`;
  posDropdown.classList.add('show');
  searchIdx = -1;

  try {
    const r = await fetch(`/api/search_etf?q=${encodeURIComponent(query)}`);
    const data = await r.json();
    const items = data.results || [];

    if (!items.length) {
      posDropdown.innerHTML = `<div class="search-empty">未找到 "${query}" 相关 ETF</div>`;
    } else {
      posDropdown.innerHTML = items.map((e, i) => {
        const safeName = (e.name || '').replace(/'/g, "\\'");
        const price = e.price ? e.price.toFixed(3) : '--';
        const t0Badge = e.is_t0 ? `<span class="search-item-type" style="background:rgba(34,197,94,0.15);color:var(--green)">T+0</span>` : `<span class="search-item-type">T+1</span>`;
        return `<div class="search-item" data-idx="${i}"
          onclick="selectEtf('${e.code}','${safeName}',${e.price||0},'${e.market||''}')">
          <span class="search-item-code">${e.code}</span>
          <span class="search-item-name">${e.name}</span>
          ${t0Badge}
          <span class="search-item-type">${price}</span>
        </div>`;
      }).join('');
    }
  } catch (err) {
    posDropdown.innerHTML = `<div class="search-empty">搜索失败，请重试</div>`;
  }
  posDropdown.classList.add('show');
  searchIdx = -1;
}

function selectEtf(code, name, price, market) {
  posCodeEl.value = code;
  document.getElementById('posName').value = name || '';
  selectedPosMarket = market || '';
  // 自动填入当前价作为成本价
  if (price && price > 0) {
    document.getElementById('posCost').value = price.toFixed(3);
  }
  posDropdown.classList.remove('show');
  document.getElementById('posShares').focus();
}

// 输入防抖：300ms 后触发搜索
posCodeEl.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => searchEtfOnline(posCodeEl.value), 300);
});
posCodeEl.addEventListener('focus', () => {
  if (posCodeEl.value.trim()) searchEtfOnline(posCodeEl.value);
});

// 键盘导航
posCodeEl.addEventListener('keydown', e => {
  const items = posDropdown.querySelectorAll('.search-item');
  if (!items.length || !posDropdown.classList.contains('show')) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); searchIdx = Math.min(searchIdx + 1, items.length - 1); highlightItem(items); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); searchIdx = Math.max(searchIdx - 1, 0); highlightItem(items); }
  else if (e.key === 'Enter' && searchIdx >= 0) { e.preventDefault(); items[searchIdx].click(); }
  else if (e.key === 'Escape') { posDropdown.classList.remove('show'); }
});

function highlightItem(items) {
  items.forEach((el, i) => el.classList.toggle('active', i === searchIdx));
  if (searchIdx >= 0 && items[searchIdx]) items[searchIdx].scrollIntoView({block: 'nearest'});
}

// 点击外部关闭
document.addEventListener('click', e => {
  if (!document.getElementById('posCodeWrap').contains(e.target)) posDropdown.classList.remove('show');
});

// ==================== 推荐单 ====================
let pendingRecs = [];  // 全局缓存，供 render 使用
let recsByCode = {};   // {code: rec} 快速查找

async function loadRecommendations() {
  try {
    const resp = await fetch('/api/recommendations');
    const data = await resp.json();
    pendingRecs = data.pending || [];
    recsByCode = {};
    pendingRecs.forEach(r => { recsByCode[r.code] = r; });

    // 有推荐时重新渲染 ETF 卡片
    if (latestData) render(latestData);
  } catch(e) {}
}

async function confirmRec(id) {
  const priceEl = document.getElementById('recPrice_' + id);
  const sharesEl = document.getElementById('recShares_' + id);
  const actual_price = parseFloat(priceEl.value);
  const actual_shares = parseInt(sharesEl.value);
  if (!actual_price || !actual_shares) { alert('请填写实际价格和仓位'); return; }

  await fetch(`/api/recommendations/${id}/confirm`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({actual_price, actual_shares}),
  });
  // 立即更新本地缓存
  pendingRecs = pendingRecs.filter(r => r.id !== id);
  recsByCode = {};
  pendingRecs.forEach(r => { recsByCode[r.code] = r; });
  if (latestData) render(latestData);
  loadTrades();
}

async function ignoreRec(id) {
  await fetch(`/api/recommendations/${id}/ignore`, {method: 'POST'});
  // 立即更新本地缓存
  pendingRecs = pendingRecs.filter(r => r.id !== id);
  recsByCode = {};
  pendingRecs.forEach(r => { recsByCode[r.code] = r; });
  if (latestData) render(latestData);
}

// ==================== Tabs ====================
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('tab-' + t.dataset.tab).classList.add('active');
    if (t.dataset.tab === 'positions') loadPositions();
  });
});

// ==================== WebSocket ====================
const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
let ws = null, latestData = null;
function connect() {
  ws = new WebSocket(`${wsProto}//${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById('connStatus').textContent = '已连接';
    document.getElementById('connStatus').className = 'conn-status conn-connected';
  };
  ws.onmessage = e => { try { latestData = JSON.parse(e.data); render(latestData); loadRecommendations(); } catch(x){} };
  ws.onclose = () => {
    document.getElementById('connStatus').textContent = '已断开';
    document.getElementById('connStatus').className = 'conn-status conn-disconnected';
    setTimeout(connect, 3000);
  };
  ws.onerror = () => ws.close();
}
connect();
loadTrades();
loadRecommendations();

// ==================== Render Dashboard ====================
function render(data) {
  document.getElementById('updateTime').textContent = data.time;
  document.getElementById('marketStatus').textContent = data.market_open ? '交易中' : '已休市';
  document.getElementById('statusDot').className = 'status-dot ' + (data.market_open ? 'open' : 'closed');
  const pnl = data.total_pnl;
  const pnlEl = document.getElementById('totalPnl');
  pnlEl.textContent = `¥${pnl>=0?'+':''}${pnl.toLocaleString('zh-CN',{minimumFractionDigits:2})}`;
  pnlEl.className = 'total-pnl ' + (pnl >= 0 ? 'up' : 'down');

  const grid = document.getElementById('etfGrid');
  if (!data.etfs || data.etfs.length === 0) {
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--dim)">
      <div style="font-size:48px;margin-bottom:16px">📡</div>
      <div style="font-size:16px;margin-bottom:8px">暂无监控品种</div>
      <div style="font-size:13px">请先到「💼 我的持仓」添加 ETF，添加后自动开始信号监控</div>
    </div>`;
    document.getElementById('alertPanel').innerHTML = '';
    return;
  }
  grid.innerHTML = data.etfs.map(etf => {
    const cc = etf.change_pct>0?'up':etf.change_pct<0?'down':'flat';
    const cardC = `signal-${etf.combined_type.toLowerCase().replace('_','-')}`;
    const sigs = etf.signals.filter(s=>s.type!=='HOLD').map(s=>{
      const ic={STRONG_BUY:'🟢',BUY:'🔵',HOLD:'⚪',SELL:'🟡',STRONG_SELL:'🔴'};
      const cl={STRONG_BUY:'var(--green)',BUY:'var(--blue)',HOLD:'var(--dim)',SELL:'var(--yellow)',STRONG_SELL:'var(--red)'};
      return `<div class="signal-item"><span class="signal-icon">${ic[s.type]||'⚪'}</span><span class="signal-strategy">${s.strategy}</span><span class="signal-reason">${s.reason}</span><span class="confidence-bar"><span class="confidence-fill" style="width:${s.confidence*100}%;background:${cl[s.type]}"></span></span></div>`;
    }).join('');
    const pos = etf.position ? `<div class="position-info"><span>持仓 ${etf.position.shares}股</span><span>成本 ${etf.position.cost.toFixed(3)}</span><span class="pnl-val ${etf.position.pnl_pct>=0?'up':'down'}">${etf.position.pnl_pct>=0?'+':''}${etf.position.pnl_pct.toFixed(2)}% (¥${etf.position.pnl>=0?'+':''}${etf.position.pnl.toFixed(2)})</span></div>` : '';

    // 推荐单嵌入
    const rec = recsByCode[etf.code];
    let recHtml = '';
    let wrapperClass = cardC;
    if (rec) {
      const isBuy = rec.direction === '买';
      const dirCl = isBuy ? 'var(--green)' : 'var(--red)';
      const dirIcon = isBuy ? '🟢' : '🔴';
      const dirLabel = isBuy ? '推荐买入' : '推荐卖出';
      const badgeClass = isBuy ? 'buy' : 'sell';
      const confPct = Math.round(rec.confidence * 100);
      const confCl = confPct >= 70 ? 'var(--green)' : confPct >= 50 ? 'var(--yellow)' : 'var(--dim)';
      const confBar = '█'.repeat(Math.round(rec.confidence*10)) + '░'.repeat(10-Math.round(rec.confidence*10));

      let posLine = '';
      if (!isBuy && rec.current_shares > 0) {
        posLine = `持仓 <b>${rec.current_shares.toLocaleString()}</b> 股 · 成本 <b>${rec.cost.toFixed(3)}</b> · 当前盈亏 <b style="color:${rec.pnl_pct>=0?'var(--red)':'var(--green)'}">${rec.pnl_pct>=0?'+':''}${rec.pnl_pct.toFixed(2)}%</b>`;
      } else if (isBuy) {
        posLine = '当前无持仓';
      }

      wrapperClass += ` has-rec ${isBuy ? 'rec-buy' : 'rec-sell'}`;
      recHtml = `<div class="rec-section" onclick="event.stopPropagation()">
        <div class="rec-header">
          <span class="rec-badge ${badgeClass}">${dirIcon} ${dirLabel}</span>
          <span style="font-size:11px;color:var(--dim)">${rec.time}</span>
        </div>
        <div class="rec-meta">
          策略: <b>${rec.strategy}</b> · 置信度: <b style="color:${confCl}">${confPct}%</b> <span class="conf-bar" style="color:${confCl}">${confBar}</span>
          ${posLine ? ' · ' + posLine : ''}
          <br>${rec.reason}
        </div>
        <div class="rec-form">
          <div class="rec-field"><label>实际价</label><input type="number" step="0.001" id="recPrice_${rec.id}" value="${rec.suggested_price.toFixed(3)}"></div>
          <div class="rec-field"><label>仓位（股）</label><input type="number" step="100" id="recShares_${rec.id}" value="${rec.suggested_shares}"></div>
          <div class="rec-btns">
            <button class="rec-btn rec-btn-confirm" onclick="event.stopPropagation();confirmRec(${rec.id})">✅ 确认交易</button>
            <button class="rec-btn rec-btn-ignore" onclick="event.stopPropagation();ignoreRec(${rec.id})">❌ 忽略</button>
          </div>
        </div>
      </div>`;
    }

    const inner = rec ? 'etf-card-inner' : '';
    const clickKline = `onclick="openKline('${etf.code}','${etf.name}','${etf.market||'sh'}',${etf.position?.cost||0})"`;

    return `<div class="etf-card ${wrapperClass}" ${clickKline}>
      ${rec ? '<div class="'+inner+'">' : ''}
      <div class="card-top"><div><div class="card-name">${etf.name}</div><div class="card-code">${etf.code}</div></div>
      <div><div class="card-price ${cc}">${etf.price.toFixed(3)}</div><div class="card-change ${cc}">${etf.change_pct>=0?'+':''}${etf.change_pct.toFixed(2)}%</div></div></div>
      <div class="sparkline"><canvas id="c-${etf.code}"></canvas></div>
      <span class="signal-badge badge-${etf.combined_type}">${etf.combined} ${etf.summary}</span>
      <div class="signal-list">${sigs||'<div class="signal-item"><span class="signal-reason" style="color:var(--dim)">无活跃信号</span></div>'}</div>${pos}
      ${rec ? '</div>' : ''}${recHtml}</div>`;
  }).join('');
  data.etfs.forEach(e => drawSparkline('c-'+e.code, e.chart, e.change_pct>=0));

  // 不在监控列表中的独立推荐
  const etfCodes = new Set(data.etfs.map(e => e.code));
  const standaloneRecs = pendingRecs.filter(r => !etfCodes.has(r.code));
  const standaloneEl = document.getElementById('recStandalone');
  if (standaloneRecs.length) {
    standaloneEl.innerHTML = standaloneRecs.map(r => {
      const isBuy = r.direction === '买';
      const dirCl = isBuy ? 'var(--green)' : 'var(--red)';
      const dirIcon = isBuy ? '🟢' : '🔴';
      const dirLabel = isBuy ? '推荐买入' : '推荐卖出';
      const badgeClass = isBuy ? 'buy' : 'sell';
      const confPct = Math.round(r.confidence * 100);
      const confCl = confPct >= 70 ? 'var(--green)' : confPct >= 50 ? 'var(--yellow)' : 'var(--dim)';
      const confBar = '█'.repeat(Math.round(r.confidence*10)) + '░'.repeat(10-Math.round(r.confidence*10));
      const glowClass = isBuy ? 'rec-buy' : 'rec-sell';
      return `<div class="etf-card has-rec ${glowClass}" style="margin-bottom:8px">
        <div class="etf-card-inner">
          <div class="card-top"><div><div class="card-name">${r.name}</div><div class="card-code">${r.code}</div></div></div>
          <div class="rec-section">
            <div class="rec-header">
              <span class="rec-badge ${badgeClass}">${dirIcon} ${dirLabel}</span>
              <span style="font-size:11px;color:var(--dim)">${r.time}</span>
            </div>
            <div class="rec-meta">
              策略: <b>${r.strategy}</b> · 参考价: <b>${r.suggested_price.toFixed(3)}</b> · 置信度: <b style="color:${confCl}">${confPct}%</b> <span class="conf-bar" style="color:${confCl}">${confBar}</span>
              <br>${r.reason}
            </div>
            <div class="rec-form">
              <div class="rec-field"><label>实际价</label><input type="number" step="0.001" id="recPrice_${r.id}" value="${r.suggested_price.toFixed(3)}"></div>
              <div class="rec-field"><label>仓位（股）</label><input type="number" step="100" id="recShares_${r.id}" value="${r.suggested_shares}"></div>
              <div class="rec-btns">
                <button class="rec-btn rec-btn-confirm" onclick="confirmRec(${r.id})">✅ 确认交易</button>
                <button class="rec-btn rec-btn-ignore" onclick="ignoreRec(${r.id})">❌ 忽略</button>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    }).join('');
  } else {
    standaloneEl.innerHTML = '';
  }

  if (data.alerts?.length) {
    document.getElementById('alertPanel').innerHTML = data.alerts.map(a => {
      const ic=a.type==='STRONG_BUY'?'🚀':'🚨', cl=a.type==='STRONG_BUY'?'var(--green)':'var(--red)';
      return `<div class="alert-item"><span class="alert-icon">${ic}</span><span class="alert-time">${a.time}</span><span style="color:${cl};font-weight:600">${a.name}</span><span>${a.signal}</span><span style="color:var(--dim)">${a.summary}</span></div>`;
    }).join('');
  }
}

function drawSparkline(id, data, isUp) {
  const canvas = document.getElementById(id);
  if (!canvas||!data||data.length<2) return;
  const ctx = canvas.getContext('2d'), dpr = window.devicePixelRatio||1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width=rect.width*dpr; canvas.height=rect.height*dpr;
  ctx.scale(dpr,dpr);
  const w=rect.width, h=rect.height;
  const prices=data.map(d=>d.price), mn=Math.min(...prices), mx=Math.max(...prices), rng=mx-mn||0.001;
  ctx.clearRect(0,0,w,h);
  const col=isUp?'rgba(239,68,68,':'rgba(34,197,94,';
  const g=ctx.createLinearGradient(0,0,0,h); g.addColorStop(0,col+'0.2)'); g.addColorStop(1,col+'0)');
  ctx.beginPath(); ctx.moveTo(0,h);
  data.forEach((d,i)=>{ctx.lineTo((i/(data.length-1))*w,h-((d.price-mn)/rng)*(h-4)-2);});
  ctx.lineTo(w,h); ctx.fillStyle=g; ctx.fill();
  ctx.beginPath();
  data.forEach((d,i)=>{const y=h-((d.price-mn)/rng)*(h-4)-2; i===0?ctx.moveTo(0,y):ctx.lineTo((i/(data.length-1))*w,y);});
  ctx.strokeStyle=isUp?'#ef4444':'#22c55e'; ctx.lineWidth=1.5; ctx.stroke();
  const ly=h-((prices[prices.length-1]-mn)/rng)*(h-4)-2;
  ctx.beginPath(); ctx.arc(w,ly,2.5,0,Math.PI*2); ctx.fillStyle=isUp?'#ef4444':'#22c55e'; ctx.fill();
}

// ==================== K线弹窗 ====================
let currentKlineCode='', currentKlineMarket='sh', currentPeriod='5min', klineData=[], currentCostPrice=0;

function openKline(code, name, market, cost) {
  currentKlineCode=code;
  currentKlineMarket=market||'sh';
  currentCostPrice=cost||0;
  document.getElementById('klineTitle').textContent=`${code} ${name}`;
  document.getElementById('klineOverlay').classList.add('show');
  switchPeriod('5min');
}
function closeKline() { document.getElementById('klineOverlay').classList.remove('show'); }
document.getElementById('klineOverlay').addEventListener('click', e => { if(e.target.id==='klineOverlay') closeKline(); });
document.getElementById('periodTabs').addEventListener('click', e => { if(e.target.classList.contains('period-tab')) switchPeriod(e.target.dataset.period); });
document.addEventListener('keydown', e => { if(e.key==='Escape') { closeKline(); closePosModal(); closeTradeModal(); }});

async function switchPeriod(period) {
  currentPeriod=period;
  document.querySelectorAll('.period-tab').forEach(t=>t.classList.toggle('active',t.dataset.period===period));
  const chart=document.getElementById('klineChart');
  // 先锁死当前容器尺寸，防止内容替换时布局抖动
  const rect=chart.getBoundingClientRect();
  chart.style.width=rect.width+'px';
  chart.style.minWidth=rect.width+'px';
  chart.style.minHeight='420px';
  chart.style.opacity='0';
  chart.style.transition='opacity 0.12s';
  await new Promise(r=>setTimeout(r,120));
  chart.innerHTML='<div class="kline-loading">加载中...</div>';
  try {
    const r=await fetch(`/api/kline/${currentKlineCode}?period=${period}&count=120&market=${currentKlineMarket}`);
    const j=await r.json();
    klineData=j.data||[];
    if(!klineData.length){chart.innerHTML='<div class="kline-loading">暂无数据</div>';chart.style.opacity='1';return;}
    chart.innerHTML='<canvas id="klineCanvas"></canvas><div class="kline-info" id="klineInfo"></div>';
    drawKlineChart('klineCanvas',klineData,period);
    chart.style.opacity='1';
    // 画完后释放锁定，让 canvas 自然撑开
    chart.style.width=''; chart.style.minWidth='';
  } catch(e) { chart.innerHTML=`<div class="kline-loading">加载失败: ${e.message}</div>`; chart.style.opacity='1'; chart.style.width=''; chart.style.minWidth=''; }
}

// ==================== 蜡烛图 + 十字线 ====================
function drawKlineChart(canvasId, data, period) {
  const canvas=document.getElementById(canvasId);
  if(!canvas||!data.length) return;
  const dpr=window.devicePixelRatio||1;
  const container=canvas.parentElement;
  // 锁定容器尺寸，防止重绘时内容变化引起容器宽度抖动
  container.style.minHeight='420px';
  const w=container.clientWidth, h=420, volH=55, chartH=h-volH-30;
  const pad={top:16,right:55,bottom:25,left:8};
  canvas.width=w*dpr; canvas.height=h*dpr;
  canvas.style.width=w+'px'; canvas.style.height=h+'px';
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr);

  const isMin=period.includes('min'), n=data.length;
  const availW=w-pad.left-pad.right;
  const barW=Math.max(2,Math.min(18,(availW/n)*0.7));
  const gap=(availW-barW*n)/(n-1||1);

  let pMin=Infinity,pMax=-Infinity,vMax=0;
  data.forEach(d=>{if(d.high>pMax)pMax=d.high;if(d.low<pMin)pMin=d.low;if(d.volume>vMax)vMax=d.volume;});
  const pR=pMax-pMin||0.001; pMin-=pR*0.05; pMax+=pR*0.05;
  const tPR=pMax-pMin;
  const yS=v=>pad.top+(1-(v-pMin)/tPR)*chartH;
  const xS=i=>pad.left+i*(barW+gap)+barW/2;

  // 预渲染底图到离屏 canvas，crosshair 只叠加线条不重绘全图
  const off=document.createElement('canvas');
  off.width=w*dpr; off.height=h*dpr;
  const oc=off.getContext('2d'); oc.scale(dpr,dpr);

  // 绘制底图（蜡烛+均线+网格+量柱）
  oc.fillStyle='#0f1117'; oc.fillRect(0,0,w,h);
  oc.strokeStyle='rgba(42,45,58,0.5)'; oc.lineWidth=0.5;
  for(let i=0;i<=5;i++){
    const y=pad.top+chartH/5*i;
    oc.beginPath(); oc.moveTo(pad.left,y); oc.lineTo(w-pad.right,y); oc.stroke();
    oc.fillStyle='#666'; oc.font='10px -apple-system,sans-serif'; oc.textAlign='left';
    oc.fillText((pMax-tPR/5*i).toFixed(3),w-pad.right+3,y+3);
  }
  if(!isMin&&n>=20){drawMA(oc,data,5,'#eab308',barW,gap,pad,chartH,pMin,tPR);drawMA(oc,data,20,'#3b82f6',barW,gap,pad,chartH,pMin,tPR);}
  data.forEach((d,i)=>{
    const x=xS(i), up=d.close>=d.open, col=up?'#ef4444':'#22c55e';
    oc.strokeStyle=col; oc.lineWidth=1;
    oc.beginPath(); oc.moveTo(x,yS(d.high)); oc.lineTo(x,yS(d.low)); oc.stroke();
    const bt=yS(Math.max(d.open,d.close)), bb=yS(Math.min(d.open,d.close));
    oc.fillStyle=col; oc.fillRect(x-barW/2,bt,barW,Math.max(1,bb-bt));
    const vh=(d.volume/vMax)*volH;
    oc.fillStyle=up?'rgba(239,68,68,0.35)':'rgba(34,197,94,0.35)';
    oc.fillRect(x-barW/2,h-pad.bottom-vh,barW,vh);
  });
  oc.fillStyle='#666'; oc.font='10px -apple-system,sans-serif'; oc.textAlign='center';
  const step=Math.max(1,Math.floor(n/7));
  for(let i=0;i<n;i+=step){const lbl=isMin?data[i].date.slice(11,16):data[i].date.slice(5,10);oc.fillText(lbl,xS(i),h-5);}
  if(!isMin&&n>=20){
    const ma5=calcMA(data,5),ma20=calcMA(data,20);
    oc.font='11px -apple-system,sans-serif'; oc.textAlign='left';
    oc.fillStyle='#eab308'; oc.fillText('MA5: '+(ma5[ma5.length-1]?.toFixed(3)||'--'),pad.left+4,pad.top+12);
    oc.fillStyle='#3b82f6'; oc.fillText('MA20: '+(ma20[ma20.length-1]?.toFixed(3)||'--'),pad.left+90,pad.top+12);
  }

  // 成本价横线
  if(currentCostPrice>0&&currentCostPrice>=pMin&&currentCostPrice<=pMax){
    const cy=yS(currentCostPrice);
    oc.save(); oc.setLineDash([6,4]); oc.strokeStyle='#f59e0b'; oc.lineWidth=1.2;
    oc.beginPath(); oc.moveTo(pad.left,cy); oc.lineTo(w-pad.right,cy); oc.stroke();
    oc.setLineDash([]);
    oc.fillStyle='#f59e0b'; oc.font='bold 10px -apple-system,sans-serif'; oc.textAlign='right';
    oc.fillText('成本 '+currentCostPrice.toFixed(3),w-pad.right-4,cy-5);
    oc.restore();
  }

  // 首次绘制
  ctx.drawImage(off,0,0,w,h);

  // Crosshair — 从离屏恢复底图再叠十字线，不触发完整重绘
  const infoEl=document.getElementById('klineInfo');
  let lastI=-1;

  function clearCross(){
    if(lastI<0)return;
    ctx.clearRect(0,0,w,h); ctx.drawImage(off,0,0,w,h);
    lastI=-1; if(infoEl)infoEl.innerHTML='';
  }

  canvas.onmousemove=e=>{
    const rect=canvas.getBoundingClientRect();
    const mx=(e.clientX-rect.left)*(w/rect.width);
    const my=(e.clientY-rect.top)*(h/rect.height);
    let nearI=-1,nd=Infinity;
    for(let i=0;i<n;i++){const d2=Math.abs(mx-xS(i));if(d2<nd){nd=d2;nearI=i;}}
    if(nearI<0||nd>barW+gap){clearCross();return;}
    // 恢复底图 + 叠加十字线
    ctx.clearRect(0,0,w,h); ctx.drawImage(off,0,0,w,h);
    const x=xS(nearI);
    ctx.strokeStyle='rgba(255,255,255,0.3)'; ctx.lineWidth=0.5;
    ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,h-pad.bottom); ctx.stroke();
    const price=pMin+tPR*(1-(my-pad.top)/chartH);
    if(my>=pad.top&&my<=pad.top+chartH){
      ctx.beginPath(); ctx.moveTo(pad.left,my); ctx.lineTo(w-pad.right,my); ctx.stroke();
      ctx.fillStyle='#555'; ctx.fillRect(w-pad.right,my-8,52,16);
      ctx.fillStyle='#fff'; ctx.font='10px -apple-system,sans-serif'; ctx.textAlign='left';
      ctx.fillText(price.toFixed(3),w-pad.right+3,my+3);
    }
    const d=data[nearI],up=d.close>=d.open;
    infoEl.innerHTML=`<span style="color:${up?'var(--red)':'var(--green)'}">${d.date}  O:${d.open.toFixed(3)} H:${d.high.toFixed(3)} L:${d.low.toFixed(3)} C:${d.close.toFixed(3)} V:${(d.volume/10000).toFixed(0)}万</span>`;
    lastI=nearI;
  };
  canvas.onmouseleave=clearCross;
}

function calcMA(data,period){
  const r=[];for(let i=0;i<data.length;i++){if(i<period-1){r.push(null);continue;}let s=0;for(let j=i-period+1;j<=i;j++)s+=data[j].close;r.push(s/period);}return r;
}
function drawMA(ctx,data,period,color,barW,gap,pad,chartH,pMin,tPR){
  const ma=calcMA(data,period),n=data.length;
  const yS=v=>pad.top+(1-(v-pMin)/tPR)*chartH;
  ctx.strokeStyle=color;ctx.lineWidth=1;ctx.beginPath();let started=false;
  ma.forEach((v,i)=>{if(v===null)return;const x=pad.left+i*(barW+gap)+barW/2,y=yS(v);if(!started){ctx.moveTo(x,y);started=true;}else ctx.lineTo(x,y);});
  ctx.stroke();
}

// ==================== 持仓管理 ====================
let editingPosCode = null;

async function loadPositions() {
  const grid = document.getElementById('posGrid');
  grid.innerHTML = '<div class="bt-loading">加载中...</div>';
  try {
    const positions = await (await fetch('/api/positions')).json();
    if (!Object.keys(positions).length) {
      grid.innerHTML = '<div class="bt-loading">暂无持仓，点击右上角添加</div>';
      return;
    }

    // 先从 WebSocket 缓存拿价格
    const prices = {};
    if (latestData?.etfs) latestData.etfs.forEach(e => prices[e.code] = e.price);

    // 对没有价格的持仓，在线拉取
    const fetchPromises = Object.entries(positions).map(async ([code, pos]) => {
      if (!prices[code]) {
        try {
          const r = await fetch(`/api/realtime/${code}?market=${pos.market || 'sh'}`);
          const d = await r.json();
          if (d.ok && d.price > 0) prices[code] = d.price;
        } catch(e) {}
      }
    });
    await Promise.all(fetchPromises);

    grid.innerHTML = Object.entries(positions).map(([code, pos]) => {
      const displayName = pos.name || code;
      const price = prices[code] || 0;
      const pnl = price && pos.cost ? (price - pos.cost) * pos.shares : 0;
      const pnlPct = pos.cost ? ((price - pos.cost) / pos.cost * 100) : 0;
      const pnlClass = pnl >= 0 ? 'up' : 'down';
      return `<div class="pos-card">
        <div class="pos-card-header">
          <div><div class="pos-card-name">${displayName}</div><div class="pos-card-code">${code}</div></div>
          <div class="${pnlClass}" style="font-size:16px;font-weight:700">${pnlPct>=0?'+':''}${pnlPct.toFixed(2)}%</div>
        </div>
        <div class="pos-card-body">
          <div><div class="pos-label">成本价</div><div class="pos-value">${pos.cost.toFixed(3)}</div></div>
          <div><div class="pos-label">现价</div><div class="pos-value">${price?price.toFixed(3):'--'}</div></div>
          <div><div class="pos-label">持仓数量</div><div class="pos-value">${pos.shares.toLocaleString()} 股</div></div>
          <div><div class="pos-label">市值</div><div class="pos-value">¥${price?(price*pos.shares).toLocaleString(undefined,{minimumFractionDigits:2}):'--'}</div></div>
          <div><div class="pos-label">盈亏</div><div class="pos-value ${pnlClass}">¥${pnl>=0?'+':''}${pnl.toFixed(2)}</div></div>
          <div><div class="pos-label">备注</div><div class="pos-value">${pos.note||'--'}</div></div>
        </div>
        <div class="pos-card-actions">
          <button class="btn" onclick="editPosition('${code}')">编辑</button>
          <button class="btn btn-danger" onclick="deletePosition('${code}')">删除</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { grid.innerHTML = `<div class="bt-loading">加载失败</div>`; }
}

function showAddPosition() {
  editingPosCode = null;
  selectedPosMarket = '';
  document.getElementById('posModalTitle').textContent = '添加持仓';
  document.getElementById('posCode').value = '';
  document.getElementById('posCode').disabled = false;
  document.getElementById('posName').value = '';
  document.getElementById('posCost').value = '';
  document.getElementById('posShares').value = '';
  document.getElementById('posNote').value = '';
  document.getElementById('posModal').classList.add('show');
  setTimeout(() => document.getElementById('posCode').focus(), 100);
}

function editPosition(code) {
  editingPosCode = code;
  document.getElementById('posModalTitle').textContent = '编辑持仓';
  document.getElementById('posCode').value = code;
  document.getElementById('posCode').disabled = true;
  fetch('/api/positions').then(r=>r.json()).then(positions => {
    const p = positions[code];
    if (p) {
      document.getElementById('posName').value = p.name || code;
      document.getElementById('posCost').value = p.cost;
      document.getElementById('posShares').value = p.shares;
      document.getElementById('posNote').value = p.note || '';
    }
  });
  document.getElementById('posModal').classList.add('show');
}

function closePosModal() { document.getElementById('posModal').classList.remove('show'); selectedPosMarket = ''; }
document.getElementById('posModal').addEventListener('click', e => { if(e.target.id==='posModal') closePosModal(); });

async function savePosition() {
  const code = document.getElementById('posCode').value.trim();
  const name = document.getElementById('posName').value.trim();
  const cost = parseFloat(document.getElementById('posCost').value);
  const shares = parseInt(document.getElementById('posShares').value);
  const note = document.getElementById('posNote').value;
  if (!code || code.length < 5) { alert('请输入有效的ETF代码（6位数字）'); return; }
  if (!cost || !shares) { alert('请填写成本价和数量'); return; }
  await fetch(`/api/positions/${code}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({cost, shares, name: name || code, note, market: selectedPosMarket}),
  });
  closePosModal();
  loadPositions();
}

async function deletePosition(code) {
  if (!confirm(`确认删除 ${code} 的持仓？`)) return;
  await fetch(`/api/positions/${code}`, {method: 'DELETE'});
  loadPositions();
}

// ==================== 回测 ====================
const STRATEGY_NAMES = {dual_ma:'双均线',rsi:'RSI',bollinger:'布林带',momentum:'涨速监控',volume_anomaly:'量价异动',macd:'MACD',kdj:'KDJ',cci:'CCI',williams:'Williams %R',adx:'ADX',sar:'SAR',obv:'OBV',trix:'TRIX'};

async function runBacktest() {
  const code = btCodeInput.dataset.code || btCodeInput.value.trim();
  const name = btCodeInput.dataset.name || '';
  if (!code) { alert('请先搜索选择 ETF'); return; }
  const start_date = document.getElementById('btStartDate').value;
  const end_date = document.getElementById('btEndDate').value;
  const capital = parseFloat(document.getElementById('btCapital').value) || 100000;
  const resDiv = document.getElementById('btResults');
  resDiv.innerHTML = '<div class="bt-loading">回测全部策略中，请稍候...</div>';

  try {
    const r = await fetch('/api/backtest', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code, name, start_date, end_date, initial_capital: capital}),
    });
    const data = await r.json();
    if (data.error) { resDiv.innerHTML = `<div class="bt-loading">错误: ${data.error}</div>`; return; }

    const strats = (data.strategies || []).filter(s => !s.error && s.total_trades > 0);
    const empty = (data.strategies || []).filter(s => !s.error && s.total_trades === 0);
    const errors = (data.strategies || []).filter(s => s.error);

    let html = `<div class="section-title">📊 ${data.name || data.code}  ${data.start_date} ~ ${data.end_date}  (${data.bar_count || data.bars || '?'} 根K线)</div>`;

    if (!strats.length) {
      html += '<div class="bt-loading">所有策略在该区间内均未产生交易</div>';
      resDiv.innerHTML = html; return;
    }

    // 对比表格
    html += `<table class="history-table" style="margin-bottom:16px">
      <thead><tr><th>策略</th><th>总收益</th><th>年化</th><th>交易次数</th><th>胜率</th><th>最大回撤</th><th>盈亏比</th><th>夏普</th><th>最终资金</th><th></th></tr></thead>
      <tbody>${strats.sort((a,b)=>b.total_return_pct-a.total_return_pct).map((s,i)=>{
        const retCl = s.total_return_pct>=0?'up':'down';
        const wcl = s.win_rate>=50?'up':'down';
        const ddCl = s.max_drawdown_pct>15?'down':s.max_drawdown_pct>8?'flat':'up';
        return `<tr style="cursor:pointer" onclick="btShowDetail(${i})">
          <td style="font-weight:600">${STRATEGY_NAMES[s.strategy]||s.strategy}</td>
          <td class="${retCl}">${s.total_return_pct>=0?'+':''}${s.total_return_pct}%</td>
          <td class="${retCl}">${s.ann_return_pct>=0?'+':''}${s.ann_return_pct}%</td>
          <td>${s.total_trades}</td>
          <td class="${wcl}">${s.win_rate}%</td>
          <td class="${ddCl}">-${s.max_drawdown_pct}%</td>
          <td>${s.profit_factor}</td>
          <td>${s.sharpe_ratio}</td>
          <td>¥${s.final_equity.toLocaleString()}</td>
          <td><button class="btn" style="padding:2px 8px;font-size:11px" onclick="event.stopPropagation();btShowDetail(${i})">详情</button></td>
        </tr>`;
      }).join('')}</tbody></table>`;

    // 详情区域
    html += '<div id="btDetail"></div>';
    resDiv.innerHTML = html;

    // 存储数据供详情展示
    window._btStrategies = strats;
    if (strats.length) btShowDetail(0);

  } catch(e) { resDiv.innerHTML = `<div class="bt-loading">回测失败: ${e.message}</div>`; }
}

function btShowDetail(idx) {
  const s = window._btStrategies[idx];
  if (!s) return;
  const det = document.getElementById('btDetail');
  const tradesHtml = s.trades?.length ? `<div class="section-title">${STRATEGY_NAMES[s.strategy]||s.strategy} — 最近交易</div>
    <table class="history-table bt-trades">
      <thead><tr><th>买入日期</th><th>卖出日期</th><th>买入价</th><th>卖出价</th><th>盈亏</th><th>盈亏%</th></tr></thead>
      <tbody>${s.trades.map(t=>`<tr>
        <td style="color:var(--dim)">${t.entry_date.slice(0,10)}</td>
        <td style="color:var(--dim)">${t.exit_date.slice(0,10)}</td>
        <td>${t.entry_price}</td><td>${t.exit_price}</td>
        <td class="${t.pnl>=0?'up':'down'}">${t.pnl>=0?'+':''}${t.pnl.toFixed(2)}</td>
        <td class="${t.pnl_pct>=0?'up':'down'}">${t.pnl_pct>=0?'+':''}${t.pnl_pct.toFixed(2)}%</td>
      </tr>`).join('')}</tbody></table>` : '';
  det.innerHTML = `<div class="bt-equity"><canvas id="equityCanvas"></canvas></div>${tradesHtml}`;
  if (s.equity_curve?.length) drawEquityCurve('equityCanvas', s.equity_curve);
}

function drawEquityCurve(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !data.length) return;
  const dpr = window.devicePixelRatio || 1;
  const container = canvas.parentElement;
  const w = container.clientWidth, h = 200;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);
  const pad = {top: 10, right: 10, bottom: 25, left: 10};
  const cw = w - pad.left - pad.right, ch = h - pad.top - pad.bottom;

  const vals = data.map(d => d.equity);
  const mn = Math.min(...vals), mx = Math.max(...vals), rng = mx - mn || 1;
  const xS = i => pad.left + (i / (data.length - 1)) * cw;
  const yS = v => pad.top + (1 - (v - mn) / rng) * ch;

  ctx.fillStyle = '#0f1117'; ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(42,45,58,0.5)'; ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + ch / 4 * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
  }
  const isUp = vals[vals.length - 1] >= vals[0];
  ctx.strokeStyle = isUp ? '#ef4444' : '#22c55e'; ctx.lineWidth = 2; ctx.beginPath();
  data.forEach((d, i) => { i === 0 ? ctx.moveTo(xS(i), yS(d.equity)) : ctx.lineTo(xS(i), yS(d.equity)); });
  ctx.stroke();
  const grad = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
  grad.addColorStop(0, isUp ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.lineTo(xS(data.length - 1), h - pad.bottom); ctx.lineTo(xS(0), h - pad.bottom); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  ctx.fillStyle = '#666'; ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'center';
  if (data.length > 1) {
    ctx.fillText(data[0].date.slice(5, 10), xS(0), h - 5);
    ctx.fillText(data[data.length - 1].date.slice(5, 10), xS(data.length - 1), h - 5);
  }
  ctx.textAlign = 'left'; ctx.fillText('¥' + mx.toLocaleString(undefined,{maximumFractionDigits:0}), pad.left + 4, yS(mx) - 4);
  ctx.fillText('¥' + mn.toLocaleString(undefined,{maximumFractionDigits:0}), pad.left + 4, yS(mn) + 12);
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("🚀 ETF T+0 可视化仪表盘启动中...")
    print("   浏览器访问: http://127.0.0.1:8888")
    print("   按 Ctrl+C 退出\n")
    uvicorn.run(app, host="127.0.0.1", port=8888)
