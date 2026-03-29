#!/usr/bin/env python3
"""
ETF T+0 信号提醒系统 - 主入口
启动后自动循环监控, 每次刷新输出信号和操作建议
"""
import sys
import os
import time
import signal
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config import T0_ETFS, MY_POSITIONS, STRATEGY_PARAMS, RUN_CONFIG
from datafeed import fetch_realtime, fetch_batch, fetch_history_kline, fetch_minute_kline, is_market_open, fetch_batch_kline
from strategies import (
    strategy_dual_ma, strategy_rsi, strategy_bollinger,
    strategy_momentum, strategy_volume, Signal, combine_signals,
    STRATEGY_FNS,
)
from position import load_positions, suggest_action
from trades import load_trades, get_trade_summary
from display import (
    console, print_header, print_realtime_table,
    print_signals, print_position_summary, print_alert, print_trades_table,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger("main")

# 全局退出标志
_running = True

# 信号冷却: {f"{code}_{signal_type}": timestamp}
_last_signal_time: dict[str, float] = {}


def _is_cooled_down(code: str, signal_type: str) -> bool:
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


def signal_handler(sig, frame):
    global _running
    _running = False
    console.print("\n[bold yellow]收到退出信号, 正在停止...[/bold yellow]")


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# K线缓存: {code: {"data": DataFrame, "ts": float}}
_kline_cache: dict[str, dict] = {}
KLINE_CACHE_TTL = 60  # 秒


def _get_cached_daily(code: str, market: str, days: int):
    """获取日K线（带缓存）"""
    now = time.time()
    cached = _kline_cache.get(code)
    if cached and (now - cached["ts"]) < KLINE_CACHE_TTL:
        return cached["data"]
    df = fetch_history_kline(code, market, days)
    if not df.empty:
        _kline_cache[code] = {"data": df, "ts": now}
    return df


def _fetch_all_daily_klines(etfs: list[tuple], days: int) -> dict[str, any]:
    """用线程池批量获取所有ETF的日K线（带缓存）"""
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
        fetched = fetch_batch_kline(need_fetch, klt="daily", count=days, max_workers=5)
        for code, df in fetched.items():
            _kline_cache[code] = {"data": df, "ts": now}
            results[code] = df
        # 缓存命中但 fetch 失败的，标记为空
        for secid, code, name, market in need_fetch:
            if code not in results:
                results[code] = None

    return results


def run_strategies(code: str, market: str, realtime: dict, df_daily=None) -> list[Signal]:
    """对一只ETF运行所有启用的策略 (使用共享策略注册表)"""
    signals = []
    params = STRATEGY_PARAMS

    # 获取日K线（外部传入则复用，否则单独拉取）
    if df_daily is None:
        days = RUN_CONFIG.get("history_days", 60)
        df_daily = _get_cached_daily(code, market, days)

    # 日线策略
    if df_daily is not None and not df_daily.empty:
        for key, fn in STRATEGY_FNS.items():
            if key == "momentum":
                continue  # 涨速监控需要分钟线，单独处理
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

    # 分钟线策略 (涨速监控)
    if params.get("momentum", {}).get("enabled") and is_market_open():
        df_min = fetch_minute_kline(code, market, minutes=5, count=60)
        if not df_min.empty:
            mp = params["momentum"]
            window = max(1, mp["window_minutes"] // 5)
            try:
                s = strategy_momentum(df_min, window=window, alert_pct=mp["alert_pct"])
                if s:
                    signals.append(s)
            except Exception as e:
                log.debug(f"Momentum strategy error for {code}: {e}")

    return signals


def run_once():
    """执行一轮监控"""
    print_header()

    # 筛选要监控的品种
    show_codes = RUN_CONFIG.get("show_etfs")
    etfs = T0_ETFS
    if show_codes:
        etfs = [e for e in T0_ETFS if e[1] in show_codes]

    if not etfs:
        console.print("[yellow]⚠️ 无监控品种, 请检查 config.py 或 data/t0_etf_list.json[/yellow]")
        return

    # 加载持仓
    positions = load_positions(MY_POSITIONS)

    # 收集实时行情 (双源轮询)
    console.print("[dim]正在获取实时行情...[/dim]")
    prices_batch = fetch_batch(etfs)
    etf_data = []
    prices = {}
    for secid, code, name, market in etfs:
        if code in prices_batch:
            etf_data.append(prices_batch[code])
            prices[code] = prices_batch[code]["price"]

    if etf_data:
        print_realtime_table(etf_data)
    else:
        console.print("[red]⚠️ 无法获取实时行情, 请检查网络[/red]")
        return

    # 批量获取日K线 (线程池 + 缓存)
    console.print("[dim]正在批量获取 K 线数据...[/dim]")
    days = RUN_CONFIG.get("history_days", 60)
    daily_klines = _fetch_all_daily_klines(etfs, days)

    # 运行策略 + 输出信号
    console.print("\n[dim]正在计算策略信号...[/dim]")
    alerts = []

    for rt in etf_data:
        code = rt["code"]
        name = rt["name"]
        price = rt["price"]

        # 找到对应的 market 前缀
        market = "sh"
        for _, c, _, m in etfs:
            if c == code:
                market = m
                break

        # 传入预取的日K线，避免重复请求
        df_daily = daily_klines.get(code)
        signals = run_strategies(code, market, rt, df_daily=df_daily)
        combined, _ = combine_signals(signals)

        pos = positions.get(code)
        action = suggest_action(code, price, pos, combined, signals)

        print_signals(code, name, signals, pos, price, action)

        # 收集需要醒目提醒的信号
        if combined.value in ("🟢 强烈买入", "🔴 强烈卖出"):
            level = "strong_buy" if "买" in combined.value else "strong_sell"
            signal_type = combined.name
            if _is_cooled_down(code, signal_type):
                alerts.append((code, name, f"{combined.value} — {action}", level))

    # 打印持仓汇总
    print_position_summary(positions, prices)

    # 打印交易记录
    trades = load_trades()
    if trades:
        print_trades_table(trades)
        summary = get_trade_summary()
        if summary["total_trades"] > 0:
            pnl_color = "red" if summary["total_pnl"] >= 0 else "green"
            console.print(f"  交易汇总: [bold]共{summary['total_trades']}笔卖出[/bold] "
                          f"盈亏:[{pnl_color}]¥{'+' if summary['total_pnl']>=0 else ''}{summary['total_pnl']:.0f}[/{pnl_color}] "
                          f"胜率:[bold]{summary['win_rate']}%[/bold] ({summary['win_count']}胜{summary['lose_count']}负)")

    # 弹出醒目提醒
    for code, name, msg, level in alerts:
        print_alert(code, name, msg, level)

    if not alerts:
        console.print("[dim]本次扫描无醒目信号[/dim]")


def main():
    console.print(Panel(
        "[bold cyan]ETF T+0 信号提醒系统[/bold cyan]\n\n"
        "策略: 双均线 | RSI | 布林带 | 涨速监控 | 量价异动 | MACD | KDJ\n"
        f"监控品种: {len(T0_ETFS)} 只 T+0 ETF\n"
        f"持仓数量: {len(MY_POSITIONS)} 只\n"
        f"刷新间隔: {RUN_CONFIG['refresh_seconds']} 秒\n\n"
        "[dim]按 Ctrl+C 退出[/dim]",
        title="启动",
        box=box.DOUBLE,
        border_style="cyan",
    ))

    # 显示一次
    run_once()

    # 循环模式
    while _running:
        now = datetime.now()
        market_open = is_market_open()

        if market_open:
            # 盘中: 按刷新间隔轮询
            console.print(f"\n[dim]⏳ {RUN_CONFIG['refresh_seconds']}秒后刷新... (盘中模式)[/dim]")
            for _ in range(RUN_CONFIG["refresh_seconds"]):
                if not _running:
                    break
                time.sleep(1)
            if _running:
                console.clear()
                run_once()
        else:
            # 非交易时间: 只跑一次然后退出, 或者等待开盘
            t = now.strftime("%H:%M")
            if t < "09:30":
                console.print(f"\n[dim]💤 未开盘, 等待 09:30...[/dim]")
                # 等到开盘
                while _running and not is_market_open():
                    time.sleep(30)
                if _running:
                    console.clear()
                    run_once()
            else:
                console.print(f"\n[bold green]✅ 已收盘, 本次监控结束[/bold green]")
                break

    console.print("[bold cyan]👋 系统已退出[/bold cyan]")


if __name__ == "__main__":
    main()
