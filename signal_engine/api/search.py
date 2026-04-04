"""
品种搜索模块 — 东方财富搜索 API + 腾讯行情补全
从 collector.py 拆出
"""
import os
import logging

from curl_cffi import requests as cffi_requests

log = logging.getLogger("signal_engine.search")

_EASTMONEY_SEARCH_TOKEN = os.environ.get(
    "EASTMONEY_SEARCH_TOKEN", "D43BF722C8E33BDC906FB84D85E326E8"
)


def search_etf(keyword: str, get_t0_type=None) -> list[dict]:
    """在线搜索品种，返回包含价格的结果列表"""
    try:
        r = cffi_requests.get(
            "https://searchapi.eastmoney.com/api/suggest/get",
            params={
                "input": keyword, "type": "14",
                "token": _EASTMONEY_SEARCH_TOKEN, "count": "20",
            },
            timeout=5, impersonate="chrome",
        )
        items = r.json().get("QuotationCodeTable", {}).get("Data", [])
        results = []
        for item in items:
            code = item.get("Code", "")
            name_str = item.get("Name", "")
            t0_type = get_t0_type(code, name_str) if get_t0_type else None
            results.append({
                "code": code, "name": name_str,
                "secid": f"{item.get('MktNum', '')}.{code}",
                "market": "sh" if str(item.get("MktNum", "")) == "1" else "sz",
                "is_t0": t0_type is not None,
                "t0_type": t0_type,
            })
        if results:
            _fetch_prices(results)
        return results
    except Exception as e:
        log.warning(f"search_etf error: {e}")
        return []


def _fetch_prices(results: list[dict]):
    """批量拉取搜索结果的实时价格"""
    if not results:
        return
    try:
        symbols = []
        for r in results:
            code = r.get("code", "")
            prefix = "sh" if code.startswith(("5", "6")) else "sz"
            symbols.append(f"{prefix}{code}")

        r = cffi_requests.get(
            f"https://qt.gtimg.cn/q={','.join(symbols)}",
            timeout=5, impersonate="chrome",
        )
        price_map = {}
        for line in r.text.strip().split(";"):
            line = line.strip()
            if '"' not in line:
                continue
            content = line.split('"')[1]
            parts = content.split("~")
            if len(parts) >= 4 and parts[2] and parts[3]:
                try:
                    price_map[parts[2]] = float(parts[3])
                except ValueError:
                    pass

        for res in results:
            res["price"] = price_map.get(res["code"], 0)
    except Exception:
        # 降级：逐个获取
        for res in results:
            try:
                code = res.get("code", "")
                prefix = "sh" if code.startswith(("5", "6")) else "sz"
                r2 = cffi_requests.get(
                    f"https://qt.gtimg.cn/q={prefix}{code}",
                    timeout=5, impersonate="chrome",
                )
                text = r2.text
                if '"' in text:
                    parts = text.split('"')[1].split("~")
                    if len(parts) >= 4 and parts[3]:
                        res["price"] = float(parts[3])
                        continue
            except Exception:
                pass
            res.setdefault("price", 0)
