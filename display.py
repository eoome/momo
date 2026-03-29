"""
终端显示模块 - Rich 美化输出
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from datetime import datetime

from strategies import Signal, SignalType, combine_signals
from position import Position, calc_pnl


console = Console()


def signal_color(sig: SignalType) -> str:
    return {
        SignalType.STRONG_BUY: "bold green",
        SignalType.BUY: "green",
        SignalType.HOLD: "dim",
        SignalType.SELL: "yellow",
        SignalType.STRONG_SELL: "bold red",
    }.get(sig, "white")


def print_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print()
    console.print(Panel(
        f"[bold cyan]ETF T+0 信号提醒系统[/bold cyan]  │  {now}",
        box=box.DOUBLE,
        style="cyan",
    ))


def print_realtime_table(etf_data: list[dict]):
    """打印实时行情表"""
    table = Table(
        title="📊 实时行情",
        box=box.ROUNDED,
        show_lines=False,
        title_style="bold white",
    )
    table.add_column("代码", style="cyan", width=8)
    table.add_column("名称", style="white", width=14)
    table.add_column("最新价", justify="right", width=8)
    table.add_column("涨跌%", justify="right", width=8)
    table.add_column("最高", justify="right", width=8)
    table.add_column("最低", justify="right", width=8)

    for d in etf_data:
        change = d.get("change_pct", 0)
        if change > 0:
            color = "red"  # A股红涨
        elif change < 0:
            color = "green"
        else:
            color = "white"

        table.add_row(
            d["code"],
            d["name"],
            f"{d['price']:.3f}",
            f"[{color}]{change:+.2f}%[/{color}]",
            f"{d['high']:.3f}",
            f"{d['low']:.3f}",
        )

    console.print(table)


def print_signals(code: str, name: str, signals: list[Signal], pos: Position | None,
                  current_price: float, action: str):
    """打印单只ETF的信号"""
    combined, summary = combine_signals(signals)

    # 标题行
    title_parts = [f"[bold]{code} {name}[/bold]"]
    if pos and pos.shares > 0:
        pnl = calc_pnl(pos, current_price)
        pnl_color = "red" if pnl["pnl_pct"] > 0 else "green"
        title_parts.append(f"持仓:{pos.shares}股 成本:{pos.cost:.3f} 盈亏:[{pnl_color}]{pnl['pnl_pct']:+.2f}%[/{pnl_color}]")
    title_parts.append(f"综合:[{signal_color(combined)}]{combined.value}[/{signal_color(combined)}] {summary}")

    console.print("  ".join(title_parts))

    # 各策略信号
    for s in signals:
        if s.signal == SignalType.HOLD:
            continue
        color = signal_color(s.signal)
        conf_bar = "█" * int(s.confidence * 10) + "░" * (10 - int(s.confidence * 10))
        console.print(f"    [{color}]{s.signal.value}[/{color}]  {s.strategy}: {s.reason}  [{conf_bar}]")

    # 操作建议
    if action:
        console.print(f"  {action}")
    console.print()


def print_position_summary(positions: dict[str, Position], prices: dict[str, float]):
    """打印持仓汇总"""
    if not positions:
        return

    table = Table(
        title="💼 我的持仓",
        box=box.ROUNDED,
        title_style="bold white",
    )
    table.add_column("代码", style="cyan")
    table.add_column("成本", justify="right")
    table.add_column("现价", justify="right")
    table.add_column("持仓", justify="right")
    table.add_column("盈亏", justify="right")
    table.add_column("盈亏%", justify="right")
    table.add_column("备注")

    total_pnl = 0
    for code, pos in positions.items():
        price = prices.get(code, 0)
        pnl_info = calc_pnl(pos, price)
        pnl_color = "red" if pnl_info["pnl"] > 0 else "green"
        table.add_row(
            code,
            f"{pos.cost:.3f}",
            f"{price:.3f}" if price else "N/A",
            str(pos.shares),
            f"[{pnl_color}]{pnl_info['pnl']:+,.2f}[/{pnl_color}]",
            f"[{pnl_color}]{pnl_info['pnl_pct']:+.2f}%[/{pnl_color}]",
            pos.note,
        )
        total_pnl += pnl_info["pnl"]

    total_color = "red" if total_pnl > 0 else "green"
    console.print(table)
    console.print(f"  总盈亏: [{total_color}]¥{total_pnl:+,.2f}[/{total_color}]\n")


def print_alert(code: str, name: str, message: str, level: str = "info"):
    """弹出醒目提醒"""
    styles = {
        "info": ("blue", "ℹ️"),
        "buy": ("green", "🟢"),
        "sell": ("yellow", "🟡"),
        "strong_buy": ("bold green", "🚀"),
        "strong_sell": ("bold red", "🚨"),
    }
    color, icon = styles.get(level, ("white", "📌"))
    console.print(Panel(
        f"[{color}]{icon} {code} {name}: {message}[/{color}]",
        border_style=color,
    ))


def print_trades_table(trades: list[dict]):
    """打印实盘交易记录"""
    if not trades:
        return

    table = Table(
        title="📝 实盘交易记录",
        box=box.ROUNDED,
        title_style="bold white",
    )
    table.add_column("日期", style="dim", width=10)
    table.add_column("代码", style="cyan", width=8)
    table.add_column("名称", width=10)
    table.add_column("方向", width=6)
    table.add_column("买价", justify="right", width=8)
    table.add_column("卖价", justify="right", width=8)
    table.add_column("仓位", justify="right", width=8)
    table.add_column("手续费", justify="right", width=8)
    table.add_column("盈亏", justify="right", width=8)
    table.add_column("盈亏比", justify="right", width=8)
    table.add_column("累计盈亏", justify="right", width=10)
    table.add_column("备注", width=12)

    for t in trades:
        dir_color = "green" if t["direction"] == "买" else "red"
        dir_text = "实际买" if t["direction"] == "买" else "实际卖"
        pnl_color = "red" if t["pnl"] > 0 else ("green" if t["pnl"] < 0 else "dim")
        cum_color = "red" if t["cumulative_pnl"] > 0 else ("green" if t["cumulative_pnl"] < 0 else "dim")

        table.add_row(
            t.get("date", ""),
            t.get("code", ""),
            t.get("name", ""),
            f"[{dir_color}]{dir_text}[/{dir_color}]",
            f"{t['buy_price']:.3f}" if t["buy_price"] > 0 else "--",
            f"{t['sell_price']:.3f}" if t.get("sell_price", 0) > 0 else "--",
            f"{t['shares']:,}",
            f"¥{t.get('commission', 0):.2f}" if t.get("commission", 0) > 0 else "--",
            f"[{pnl_color}]{'+' if t['pnl']>=0 else ''}{t['pnl']:.0f}[/{pnl_color}]" if t["direction"] == "卖" else "--",
            f"[{pnl_color}]{'+' if t['pnl_pct']>=0 else ''}{t['pnl_pct']:.2f}%[/{pnl_color}]" if t.get("pnl_pct", 0) != 0 else "--",
            f"[{cum_color}]{'+' if t['cumulative_pnl']>=0 else ''}{t['cumulative_pnl']:.0f}[/{cum_color}]",
            t.get("note", ""),
        )

    console.print(table)
