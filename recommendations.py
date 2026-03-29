"""
推荐交易管理
信号触发 → 生成推荐单 → 用户确认/忽略 → 确认后写入交易记录
"""
import json
import os
import time
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RECS_FILE = os.path.join(DATA_DIR, "recommendations.json")

# 信号冷却：同品种+同方向的推荐间隔（秒），防止刷屏
REC_COOLDOWN = 600  # 10分钟


def _load_recs() -> list[dict]:
    if not os.path.exists(RECS_FILE):
        return []
    try:
        with open(RECS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_recs(recs: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RECS_FILE, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)


# 冷却时间戳
_last_rec_time: dict[str, float] = {}


def _is_rec_cooled_down(code: str, direction: str) -> bool:
    """同一品种+同方向，冷却期内不重复生成推荐"""
    key = f"{code}_{direction}"
    now = time.time()
    last = _last_rec_time.get(key, 0)
    if now - last < REC_COOLDOWN:
        return False
    _last_rec_time[key] = now
    return True


def suggest_shares(code: str, price: float, direction: str,
                    current_shares: int = 0) -> int:
    """
    根据方向和当前持仓，建议仓位
    卖出 → 建议全部卖出
    买入 → 建议 10000 起步（ETF 最小单位）
    """
    if direction == "卖" and current_shares > 0:
        return current_shares
    # 买入建议：按约 1.3 万市值估算
    if price > 0:
        return max(10000, int(13000 / price / 100) * 100)  # 取整百
    return 10000


def create_recommendation(code: str, name: str, direction: str,
                           price: float, strategy: str, reason: str,
                           confidence: float, current_shares: int = 0,
                           cost: float = 0) -> dict | None:
    """
    生成一条推荐单
    返回推荐 dict，或 None（冷却中/不满足条件）
    """
    # 冷却检查
    if not _is_rec_cooled_down(code, direction):
        return None

    # 卖出但没持仓 → 跳过
    if direction == "卖" and current_shares <= 0:
        return None

    suggested_shares = suggest_shares(code, price, direction, current_shares)

    rec = {
        "id": int(time.time() * 1000) % 100000000,  # 简易唯一 ID
        "date": datetime.now().strftime("%Y/%m/%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "code": code,
        "name": name,
        "direction": direction,          # "买" 或 "卖"
        "suggested_price": round(price, 3),
        "suggested_shares": suggested_shares,
        "strategy": strategy,
        "reason": reason,
        "confidence": round(confidence, 2),
        "current_shares": current_shares,
        "cost": cost,
        "pnl_pct": round((price - cost) / cost * 100, 2) if cost > 0 and direction == "卖" else 0,
        "status": "pending",             # pending / confirmed / ignored
    }

    recs = _load_recs()
    recs.append(rec)
    # 只保留最近 200 条
    if len(recs) > 200:
        recs = recs[-200:]
    _save_recs(recs)
    return rec


def get_pending() -> list[dict]:
    """获取所有待确认的推荐"""
    return [r for r in _load_recs() if r.get("status") == "pending"]


def get_all() -> list[dict]:
    """获取所有推荐（含已确认/已忽略）"""
    return _load_recs()


def confirm_recommendation(rec_id: int, actual_price: float,
                            actual_shares: int, note: str = "") -> dict | None:
    """
    确认推荐 → 自动写入交易记录
    返回交易记录 dict
    """
    from trades import add_trade

    recs = _load_recs()
    for rec in recs:
        if rec["id"] == rec_id:
            rec["status"] = "confirmed"
            rec["actual_price"] = actual_price
            rec["actual_shares"] = actual_shares
            _save_recs(recs)

            # 写入交易记录
            if rec["direction"] == "买":
                trade = add_trade(
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
                trade = add_trade(
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
    """忽略推荐"""
    recs = _load_recs()
    for rec in recs:
        if rec["id"] == rec_id:
            rec["status"] = "ignored"
            _save_recs(recs)
            return True
    return False


def cleanup_old(days: int = 7):
    """清理超过 N 天的已确认/已忽略推荐"""
    recs = _load_recs()
    cutoff = datetime.now().strftime("%Y/%m/%d")
    keep = []
    for r in recs:
        if r.get("status") == "pending":
            keep.append(r)
        else:
            keep.append(r)  # 暂时全保留，后续可按日期清理
    _save_recs(keep)
