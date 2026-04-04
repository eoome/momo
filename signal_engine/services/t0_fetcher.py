"""
T+0 品种自动发现模块
从交易所/财经数据源获取品种列表，自动判断是否支持 T+0 当日回转交易
"""
import json
import os
from datetime import datetime
from curl_cffi import requests as cffi_requests

from signal_engine.config import DATA_DIR

T0_FILE = os.path.join(DATA_DIR, "t0_etf_list.json")

# ================================================================
# T+0 判断规则
# ================================================================
_T0_NAME_KEYWORDS = {
    "纳指": "跨境", "标普": "跨境", "日经": "跨境", "恒生": "跨境",
    "德国": "跨境", "法国": "跨境", "东南亚": "跨境", "沙特": "跨境",
    "中概": "跨境", "美股": "跨境", "港股": "跨境", "H股": "跨境",
    "互联网": "跨境", "海外": "跨境",
    "恒指": "跨境", "恒科": "跨境", "东证": "跨境", "纳斯达克": "跨境",
    "道琼": "跨境", "香港": "跨境",
    "黄金": "黄金", "金ETF": "黄金",
    "国债": "债券", "政金债": "债券", "企业债": "债券",
    "信用债": "债券", "城投债": "债券", "地方债": "债券",
    "短融": "债券", "公司债": "债券", "利率债": "债券",
    "可转债": "债券", "转债": "债券",
    "原油": "商品", "豆粕": "商品", "有色金属": "商品",
    "能源化工": "商品", "白银": "商品", "铜": "商品",
    "货币": "货币", "华宝添益": "货币", "银华日利": "货币",
}

_T0_NAME_EXCLUDES = ["黄金股票", "黄金股"]

_T0_CODE_PREFIXES = {
    "511": "债券/货币",
    "518": "黄金",
}


def is_t0_by_name(name: str) -> str | None:
    for excl in _T0_NAME_EXCLUDES:
        if excl in name:
            return None
    for kw, t0_type in _T0_NAME_KEYWORDS.items():
        if kw in name:
            return t0_type
    return None


def is_t0_by_code(code: str) -> str | None:
    for prefix, t0_type in _T0_CODE_PREFIXES.items():
        if code.startswith(prefix):
            return t0_type
    return None


# ================================================================
# 数据源 1: AKShare 上交所
# ================================================================
def _fetch_sse_etf_akshare() -> list[dict]:
    try:
        import akshare as ak
        df = ak.fund_etf_scale_sse()
        results = []
        for _, row in df.iterrows():
            code = str(row["基金代码"])
            name = str(row["基金简称"])
            etf_type = str(row.get("ETF类型", ""))
            market = "sh"

            is_t0 = False
            t0_type = None

            if etf_type == "跨境":
                is_t0 = True
                t0_type = "跨境"
            else:
                t0_type = is_t0_by_name(name) or is_t0_by_code(code)
                if t0_type:
                    is_t0 = True

            results.append({
                "code": code, "name": name, "market": market,
                "is_t0": is_t0, "t0_type": t0_type or etf_type,
                "source": "sse_akshare",
            })
        return results
    except Exception as e:
        print(f"[WARN] AKShare 上交所获取失败: {e}")
        return []


# ================================================================
# 数据源 2: 东方财富全量
# ================================================================
def _fetch_eastmoney_etf() -> list[dict]:
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        results = []
        for _, row in df.iterrows():
            code = str(row["代码"]).zfill(6)
            name = str(row["名称"])
            market = "sh" if code.startswith(("5", "6")) else "sz"

            t0_type = is_t0_by_name(name) or is_t0_by_code(code)
            is_t0 = t0_type is not None

            results.append({
                "code": code, "name": name, "market": market,
                "is_t0": is_t0, "t0_type": t0_type,
                "source": "eastmoney",
            })
        return results
    except Exception as e:
        print(f"[WARN] 东财品种获取失败: {e}")
        return []


# ================================================================
# 数据源 3: 深交所
# ================================================================
def _fetch_szse_etf_curl() -> list[dict]:
    try:
        url = "https://www.szse.cn/api/report/ShowReport/data"
        params = {
            "SHOWTYPE": "JSON", "CATALOGID": "1945",
            "txtETFName": "", "txtCode": "",
            "tab1PAGENUMBER": 1, "PAGECOUNT": 500,
        }
        r = cffi_requests.get(url, params=params, timeout=15, impersonate="chrome")
        data = r.json()
        if not data or not isinstance(data, list):
            return []

        rows = data[0].get("data", [])
        results = []
        for row in rows:
            code = str(row.get("jjdm", row.get("基金代码", ""))).zfill(6)
            name = str(row.get("jjjc", row.get("基金简称", "")))
            if not code or code == "000000":
                continue

            t0_type = is_t0_by_name(name) or is_t0_by_code(code)
            is_t0 = t0_type is not None

            results.append({
                "code": code, "name": name, "market": "sz",
                "is_t0": is_t0, "t0_type": t0_type,
                "source": "szse",
            })
        return results
    except Exception as e:
        print(f"[WARN] 深交所获取失败: {e}")
        return []


# ================================================================
# 合并 & 去重
# ================================================================
def fetch_all_etf() -> list[dict]:
    all_etfs = {}

    sse_list = _fetch_sse_etf_akshare()
    for etf in sse_list:
        all_etfs[etf["code"]] = etf
    print(f"  ✓ 上交所: {len(sse_list)} 只")

    em_list = _fetch_eastmoney_etf()
    added = 0
    for etf in em_list:
        if etf["code"] not in all_etfs:
            all_etfs[etf["code"]] = etf
            added += 1
        else:
            existing = all_etfs[etf["code"]]
            if etf["is_t0"] and not existing["is_t0"]:
                existing["is_t0"] = True
                existing["t0_type"] = etf["t0_type"]
    print(f"  ✓ 东财: {len(em_list)} 只 (新增 {added} 只)")

    szse_list = _fetch_szse_etf_curl()
    added = 0
    for etf in szse_list:
        if etf["code"] not in all_etfs:
            all_etfs[etf["code"]] = etf
            added += 1
    print(f"  ✓ 深交所: {len(szse_list)} 只 (新增 {added} 只)")

    result = list(all_etfs.values())
    t0_count = sum(1 for e in result if e["is_t0"])
    print(f"  合计: {len(result)} 只品种, 其中 T+0: {t0_count} 只")

    return result


def get_t0_etfs(etf_list: list[dict] = None) -> list[dict]:
    if etf_list is None:
        etf_list = fetch_all_etf()
    return [e for e in etf_list if e["is_t0"]]


# ================================================================
# 保存 & 加载
# ================================================================
def save_t0_list(t0_etfs: list[dict], filepath: str = T0_FILE):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(t0_etfs),
        "etfs": t0_etfs,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 已保存到 {filepath}")


def load_t0_list(filepath: str = T0_FILE) -> list[dict]:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("etfs", [])


def get_update_age(filepath: str = T0_FILE) -> float | None:
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    updated = data.get("updated_at", "")
    if not updated:
        return None
    dt = datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
    return (datetime.now() - dt).total_seconds() / 3600


def load_or_update(max_age_hours: float = 24) -> list[dict]:
    age = get_update_age()
    if age is not None and age < max_age_hours:
        print(f"  📋 使用缓存 (更新于 {age:.1f}h 前)")
        return load_t0_list()

    print(f"  🔄 T+0 列表{'已过期' if age else '不存在'}，正在更新...")
    etf_list = fetch_all_etf()
    t0_etfs = get_t0_etfs(etf_list)
    save_t0_list(t0_etfs)
    return t0_etfs


def to_config_format(t0_etfs: list[dict] = None) -> list[tuple]:
    if t0_etfs is None:
        t0_etfs = load_t0_list()

    result = []
    for etf in t0_etfs:
        code = etf["code"]
        name = etf["name"]
        market = etf.get("market", "sh")
        secid = f"1.{code}" if market == "sh" else f"0.{code}"
        result.append((secid, code, name, market))

    return result


if __name__ == "__main__":
    print("=" * 50)
    print("T+0 品种自动发现工具")
    print("=" * 50)

    print("\n📡 正在从数据源获取品种列表...")
    etf_list = fetch_all_etf()

    t0_etfs = get_t0_etfs(etf_list)
    save_t0_list(t0_etfs)

    by_type = {}
    for e in t0_etfs:
        t = e.get("t0_type", "未知")
        by_type.setdefault(t, []).append(e)

    print(f"\n{'='*50}")
    print(f"📊 T+0 ETF 列表 (共 {len(t0_etfs)} 只)")
    print(f"{'='*50}")
    for t, items in sorted(by_type.items()):
        print(f"\n【{t}】{len(items)} 只:")
        for e in items[:10]:
            print(f"  {e['code']}  {e['name']}  ({e['market']})")
        if len(items) > 10:
            print(f"  ... 还有 {len(items)-10} 只")

    print(f"\n✅ 列表已保存到 {T0_FILE}")
