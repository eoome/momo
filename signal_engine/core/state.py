"""
应用运行时状态 — 集中管理所有可变全局状态
替换了原 collector.py 中的模块级变量
"""
import asyncio
import time
import logging
from dataclasses import dataclass, field

from signal_engine.config import RUN_CONFIG
from signal_engine.data.store import load_json, save_json

log = logging.getLogger("signal_engine.state")

# 持久化文件名
_SIGNALS_FILE = "signals_history.json"
_SIGNAL_TIMES_FILE = "signal_times.json"

# 信号历史上限
_MAX_HISTORY = 500


@dataclass
class AppState:
    """所有运行时可变状态的唯一持有者"""

    # ── 信号历史 ──
    signal_history: list[dict] = field(default_factory=list)

    # ── 分钟级价格轨迹 (用于前端折线图) ──
    price_history: dict[str, list[dict]] = field(default_factory=dict)
    max_price_points: int = 120

    # ── K 线缓存 ──
    kline_cache: dict[str, dict] = field(default_factory=dict)
    kline_cache_ttl: int = 60

    # ── T+0 品种缓存 ──
    t0_cache: list[dict] = field(default_factory=list)
    t0_cache_ts: float = 0.0
    t0_cache_ttl: int = 3600

    # ── 信号冷却 ──
    last_signal_time: dict[str, float] = field(default_factory=dict)

    # ── 信号首次触发时间持久化 ──
    signal_times: dict[str, str] = field(default_factory=dict)

    # ── 异步刷新触发器 ──
    _refresh_event: asyncio.Event | None = field(default=None, repr=False)

    # ── 历史分页 ──
    dashboard_history_limit: int = 200

    # ── 初始化标记 ──
    _initialized: bool = field(default=False, repr=False)

    # ── 持久化委托给 trades 模块 (避免循环导入) ──

    def initialize(self):
        """加载持久化数据，仅执行一次"""
        if self._initialized:
            return
        self.signal_history = load_json(_SIGNALS_FILE, [])
        self.signal_times = load_json(_SIGNAL_TIMES_FILE, {})
        self._initialized = True
        log.info("AppState initialized")

    # ── 异步事件 ──

    @property
    def refresh_event(self) -> asyncio.Event:
        if self._refresh_event is None:
            self._refresh_event = asyncio.Event()
        return self._refresh_event

    def trigger_refresh(self):
        """触发即时刷新"""
        self.refresh_event.set()

    # ── 信号冷却 ──

    def is_signal_cooled_down(self, code: str, signal_type: str) -> bool:
        cooldown = RUN_CONFIG.get("alert_cooldown", 300)
        key = f"{code}_{signal_type}"
        now = time.time()
        if now - self.last_signal_time.get(key, 0) < cooldown:
            return False
        self.last_signal_time[key] = now
        return True

    # ── 信号时间 ──

    def get_signal_time(self, strategy: str, signal_name: str) -> str:
        key = f"{strategy}_{signal_name}"
        if key in self.signal_times:
            return self.signal_times[key]
        now_str = time.strftime("%Y/%m/%d %H:%M:%S")
        self.signal_times[key] = now_str
        save_json(_SIGNAL_TIMES_FILE, self.signal_times)
        return now_str

    # ── 信号历史持久化 ──

    def append_signal(self, alert: dict):
        self.signal_history.append(alert)
        if len(self.signal_history) > _MAX_HISTORY:
            self.signal_history = self.signal_history[-_MAX_HISTORY:]
        save_json(_SIGNALS_FILE, self.signal_history)

    # ── 价格轨迹 ──

    def update_price(self, code: str, time_str: str, price: float):
        if code not in self.price_history:
            self.price_history[code] = []
        self.price_history[code].append({"time": time_str, "price": price})
        if len(self.price_history[code]) > self.max_price_points:
            self.price_history[code] = self.price_history[code][-self.max_price_points:]

    # ── K 线缓存 ──

    def get_kline_cached(self, key: str):
        import time as _time
        cached = self.kline_cache.get(key)
        if cached and (_time.time() - cached["ts"]) < self.kline_cache_ttl:
            return cached["data"]
        return None

    def set_kline_cached(self, key: str, data):
        import time as _time
        self.kline_cache[key] = {"data": data, "ts": _time.time()}

    # ── T+0 缓存 ──

    def get_t0_list(self) -> list[dict]:
        now = time.time()
        if not self.t0_cache or (now - self.t0_cache_ts) > self.t0_cache_ttl:
            from signal_engine.services.t0_fetcher import load_t0_list
            self.t0_cache = load_t0_list()
            self.t0_cache_ts = now
        return self.t0_cache

    def refresh_t0_cache(self, t0_etfs: list[dict]):
        self.t0_cache = t0_etfs
        self.t0_cache_ts = time.time()
