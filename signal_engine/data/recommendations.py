"""
推荐交易管理
信号触发 → 生成推荐单 → 用户确认/忽略 → 确认后写入交易记录
"""
import os
import time
from datetime import datetime

from signal_engine.data.store import load_json, save_json
from signal_engine.data import trades as trades_mod

RECS_FILE = "recommendations.json"
REC_COOLDOWN = 600  # 10分钟

# 冷却时间戳
_last_rec_time: dict[str, float] = {}


def _is_rec_cooled_down(code: str, direction: str) -> bool:
    key = f"{code}_{direction}"
    now = time.time()
    last = _last_rec_time.get(key, 0)
    if now - last < REC_COOLDOWN:
        return False
    _last_rec_time[key] = now
    return True


def _load_recs() -> list[dict]:
    return load_json(RECS_FILE, [])


def _save_recs(recs: list[dict]):
    save_json(RECS_FILE, recs)


def suggest_shares(code: str, price: float, direction: str,
                    current_shares: int = 0) -> int:
    if direction == "卖" and current_shares > 0:
        return current_shares
    if price and price > 0:
        return max(10000, int(13000 / price / 100) * 100)
    return 10000


def create_recommendation(code: str, name: str, direction: str,
                           price: float, strategy: str, reason: str,
                           confidence: float, current_shares: int = 0,
                           cost: float = 0) -> dict | None:
    if not _is_rec_cooled_down(code, direction):
        return None

    if direction == "卖" and current_shares <= 0:
        return None

    suggested_shares = suggest_shares(code, price, direction, current_shares)

    recs = _load_recs()
    max_id = max((r.get("id", 0) for r in recs), default=0)

    rec = {
        "id": max_id + 1,
        "date": datetime.now().strftime("%Y/%m/%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "code": code,
        "name": name,
        "direction": direction,
        "suggested_price": round(price, 3),
        "suggested_shares": suggested_shares,
        "strategy": strategy,
        "reason": reason,
        "confidence": round(confidence, 2),
        "current_shares": current_shares,
        "cost": cost,
        "pnl_pct": round((price - cost) / cost * 100, 2) if cost > 0 and direction == "卖" else 0,
        "status": "pending",
    }

    recs.append(rec)
    if len(recs) > 200:
        recs = recs[-200:]
    _save_recs(recs)
    return rec


def get_pending() -> list[dict]:
    return [r for r in _load_recs() if r.get("status") == "pending"]


def get_all() -> list[dict]:
    return _load_recs()


def confirm_recommendation(rec_id: int, actual_price: float,
                            actual_shares: int, note: str = "") -> dict | None:
    recs = _load_recs()
    for rec in recs:
        if rec["id"] == rec_id:
            rec["status"] = "confirmed"
            rec["actual_price"] = actual_price
            rec["actual_shares"] = actual_shares
            _save_recs(recs)

            if rec["direction"] == "买":
                trade = trades_mod.add_trade(
                    date=rec["date"],
                    code=rec["code"],
                    name=rec["name"],
                    direction="买",
                    buy_price=actual_price,
                    sell_price=0,
                    shares=actual_shares,
                    note=note or f"推荐确认 ({rec['strategy']})",
                )
            else:
                trade = trades_mod.add_trade(
                    date=rec["date"],
                    code=rec["code"],
                    name=rec["name"],
                    direction="卖",
                    buy_price=rec.get("cost", actual_price),
                    sell_price=actual_price,
                    shares=actual_shares,
                    note=note or f"推荐确认 ({rec['strategy']})",
                )
            return trade
    return None


def ignore_recommendation(rec_id: int) -> bool:
    recs = _load_recs()
    for rec in recs:
        if rec["id"] == rec_id:
            rec["status"] = "ignored"
            _save_recs(recs)
            return True
    return False


def cleanup_old(days: int = 7):
    from datetime import timedelta
    recs = _load_recs()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    keep = [r for r in recs
            if r.get("status") == "pending"
            or r.get("date", "9999/99/99") >= cutoff]
    _save_recs(keep)
