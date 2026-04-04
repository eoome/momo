"""
API 路由 + WebSocket + 数据循环
所有端点与原始 dashboard_api.py 完全一致，仪表盘无需任何修改
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.requests import Request

from signal_engine.config import STRATEGY_PARAMS, RUN_CONFIG
from signal_engine.core.strategies import STRATEGY_FNS
from signal_engine.data.positions import Position, calc_pnl, suggest_action
from signal_engine.data.trades import (
    load_trades, add_trade, delete_trade, update_trade, get_trade_summary,
)
from signal_engine.data.recommendations import (
    get_pending, get_all, confirm_recommendation, ignore_recommendation,
)
from signal_engine.data.store import load_json, save_json
from signal_engine.services.feed import fetch_realtime, fetch_history_kline, fetch_minute_kline, fetch_batch_kline, is_market_open
from signal_engine.services.t0_fetcher import load_t0_list, get_update_age
from signal_engine.services.backtest import run_backtest
from signal_engine.api.collector import (
    init_api, collect_data, search_etf, do_update_t0,
    _load_positions_file, _save_positions_file, _get_t0_type,
    get_refresh_event, get_state,
)

log = logging.getLogger("signal_engine.api")

router = APIRouter()
_thread_pool = ThreadPoolExecutor(max_workers=8)

# WebSocket 客户端
connected_clients: set[WebSocket] = set()


# ══════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════

@router.get("/api/kline/{code}")
async def get_kline(code: str,
                    period: str = Query(default="daily", pattern="^(daily|weekly|monthly|1min|5min|15min|30min|60min)$"),
                    count: int = Query(default=120, ge=10, le=500),
                    market: str = Query(default="sh")):
    import time as _time
    mkt = market
    positions = _load_positions_file()
    if code in positions:
        mkt = positions[code].get("market", market)
    secid = f"1.{code}" if mkt == "sh" else f"0.{code}"
    name = positions.get(code, {}).get("name", code)

    _state = get_state()
    cache_key = f"{code}_{period}"
    now = _time.time()
    cached = _state.get_kline_cached(cache_key)
    if cached is not None:
        df = cached
    else:
        loop = asyncio.get_event_loop()
        if period == "daily":
            df = await loop.run_in_executor(_thread_pool, partial(fetch_history_kline, code, mkt, count))
        elif "min" in period:
            mins = int(period.replace("min", ""))
            df = await loop.run_in_executor(_thread_pool, partial(fetch_minute_kline, code, mkt, minutes=mins, count=count))
        else:
            batch = await loop.run_in_executor(
                _thread_pool, partial(fetch_batch_kline, [(secid, code, name, mkt)], klt=period, count=count))
            df = batch.get(code) if batch else None
        if df is not None and not df.empty:
            _state.set_kline_cached(cache_key, df)

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


@router.get("/api/realtime/{code}")
async def api_realtime(code: str, market: str = Query(default="sh")):
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(_thread_pool, lambda: fetch_realtime(code, market))
    if data and data.get("price", 0) > 0:
        return {"ok": True, "price": data["price"], "change_pct": data.get("change_pct", 0),
                "high": data.get("high", 0), "low": data.get("low", 0), "name": data.get("name", "")}
    return {"ok": False, "price": 0}


@router.get("/api/positions")
async def api_get_positions():
    return _load_positions_file()


@router.post("/api/positions/{code}")
async def api_add_position(code: str, request: Request):
    body = await request.json()
    positions = _load_positions_file()
    t0_type = _get_t0_type(code, body.get("name", ""))
    positions[code] = {
        "cost": float(body.get("cost", 0)),
        "shares": int(body.get("shares", 0)),
        "name": body.get("name", ""),
        "note": body.get("note", ""),
        "market": body.get("market", "sh"),
        "commission_rate": float(body.get("commission_rate", 0.0003)),
        "trade_type": body.get("trade_type", "T+1"),
        "is_t0": t0_type is not None,
        "t0_type": t0_type,
    }
    _save_positions_file(positions)
    get_refresh_event().set()
    return {"ok": True, "positions": positions}


@router.post("/api/positions/{code}/update")
async def api_update_position(code: str, request: Request):
    body = await request.json()
    direction = body.get("direction", "买")
    actual_price = float(body.get("actual_price", 0))
    actual_shares = int(body.get("actual_shares", 0))
    if actual_price <= 0 or actual_shares <= 0:
        return {"ok": False, "error": "价格和股数必须大于0"}

    positions = _load_positions_file()
    existing = positions.get(code)

    if direction == "买":
        if existing and existing.get("shares", 0) > 0:
            old_shares = existing["shares"]
            old_cost = existing["cost"]
            new_shares = old_shares + actual_shares
            new_cost = round((old_cost * old_shares + actual_price * actual_shares) / new_shares, 4)
            existing["cost"] = new_cost
            existing["shares"] = new_shares
            existing["note"] = existing.get("note", "") + f" [加仓 {actual_shares}股@{actual_price}]"
        else:
            positions[code] = {
                "cost": actual_price,
                "shares": actual_shares,
                "name": existing.get("name", "") if existing else "",
                "market": existing.get("market", "sh") if existing else "sh",
                "note": f"新建仓 {actual_shares}股@{actual_price}",
            }
    elif direction == "卖":
        if existing and existing.get("shares", 0) > 0:
            new_shares = existing["shares"] - actual_shares
            if new_shares <= 0:
                positions.pop(code, None)
            else:
                existing["shares"] = new_shares
                existing["note"] = existing.get("note", "") + f" [减仓 {actual_shares}股@{actual_price}]"
        else:
            return {"ok": False, "error": "无持仓可卖"}

    _save_positions_file(positions)
    get_refresh_event().set()
    return {"ok": True, "positions": positions}


@router.delete("/api/positions/{code}")
async def api_delete_position(code: str):
    positions = _load_positions_file()
    positions.pop(code, None)
    _save_positions_file(positions)
    get_refresh_event().set()
    return {"ok": True, "positions": positions}


@router.get("/api/search_etf")
async def api_search_etf(q: str = Query(default="", min_length=1)):
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_thread_pool, lambda: search_etf(q))
    return {"query": q, "results": results}


@router.get("/api/signals")
async def api_get_signals(limit: int = Query(default=100, ge=1, le=500)):
    return get_state().signal_history[-limit:]


@router.get("/api/t0_etfs")
async def api_get_t0_etfs():
    t0_list = load_t0_list()
    age = None
    try:
        age = get_update_age()
    except Exception:
        pass
    return {"count": len(t0_list), "age_hours": round(age, 1) if age is not None else None, "etfs": t0_list}


@router.post("/api/t0_etfs/update")
async def api_update_t0_etfs():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_thread_pool, do_update_t0)
    return {"ok": True, "count": len(result), "message": f"已更新 {len(result)} 只 T+0 品种"}


# ── 交易记录 API ──
@router.get("/api/trades")
async def api_get_trades():
    return {"trades": load_trades(), "summary": get_trade_summary()}


@router.post("/api/trades")
async def api_add_trade(request: Request):
    body = await request.json()
    code = body.get("code", "")
    shares = int(body.get("shares", 0))
    if not code or shares <= 0:
        return {"ok": False, "error": "代码和仓位不能为空"}
    trade = add_trade(
        date=body.get("date", datetime.now().strftime("%Y/%m/%d")),
        code=code, name=body.get("name", ""),
        direction=body.get("direction", "买"),
        buy_price=float(body.get("buy_price", 0)),
        sell_price=float(body.get("sell_price", 0)),
        shares=shares, note=body.get("note", ""),
    )
    return {"ok": True, "trade": trade, "summary": get_trade_summary()}


@router.delete("/api/trades/{trade_id}")
async def api_delete_trade(trade_id: int):
    return {"ok": delete_trade(trade_id), "summary": get_trade_summary()}


@router.put("/api/trades/{trade_id}")
async def api_update_trade(trade_id: int, request: Request):
    body = await request.json()
    trade = update_trade(trade_id, body)
    return {"ok": trade is not None, "trade": trade, "summary": get_trade_summary()}


# ── 推荐单 API ──
@router.get("/api/recommendations")
async def api_get_recommendations():
    pending = get_pending()
    all_recs = get_all()
    recent = [r for r in all_recs if r.get("status") != "pending"][-20:]
    return {"pending": pending, "recent": recent, "pending_count": len(pending)}


@router.post("/api/recommendations/{rec_id}/confirm")
async def api_confirm_recommendation(rec_id: int, request: Request):
    body = await request.json()
    actual_price = float(body.get("actual_price", 0))
    actual_shares = int(body.get("actual_shares", 0))
    if actual_price <= 0 or actual_shares <= 0:
        return {"ok": False, "error": "实际价格和仓位不能为空"}
    trade = confirm_recommendation(rec_id, actual_price, actual_shares, body.get("note", ""))
    get_refresh_event().set()
    return {"ok": trade is not None, "trade": trade, "summary": get_trade_summary()}


@router.post("/api/recommendations/{rec_id}/ignore")
async def api_ignore_recommendation(rec_id: int):
    return {"ok": ignore_recommendation(rec_id)}


# ── 回测 API ──
@router.post("/api/backtest")
async def api_backtest(request: Request):
    body = await request.json()
    code = body.get("code", "")
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    initial_capital = float(body.get("initial_capital", 100000))

    market = "sh"
    name = code
    positions = _load_positions_file()
    if code in positions:
        market = positions[code].get("market", "sh")
        name = positions[code].get("name", code)

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(_thread_pool, lambda: fetch_history_kline(code, market, 500))

    if df is None or df.empty:
        return {"error": "无法获取K线数据"}

    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    if df.empty:
        return {"error": "所选日期范围内无K线数据"}

    results = []
    from signal_engine.config import STRATEGY_PARAMS as _sp
    for key, fn in STRATEGY_FNS.items():
        try:
            kw = {k: v for k, v in _sp.get(key, {}).items() if k != "enabled"}
            r = await loop.run_in_executor(_thread_pool,
                lambda f=fn, k=kw: run_backtest(df, f, k, initial_capital))
            r["strategy"] = key
            results.append(r)
        except Exception as e:
            results.append({"strategy": key, "error": str(e)})

    return {
        "code": code, "name": name,
        "start_date": str(df.iloc[0]["date"])[:10],
        "end_date": str(df.iloc[-1]["date"])[:10],
        "bars": len(df), "strategies": results,
    }


# ── WebSocket ──
@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(ws)


# ── 数据循环 ──
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
        refresh = get_refresh_event()
        refresh.clear()
        try:
            await asyncio.wait_for(refresh.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
