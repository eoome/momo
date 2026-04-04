# XM-LH T+0 Signal Dashboard

基于 **14 种** 技术策略的 T+0 品种盘中信号提醒工具。

**不做自动交易，只告诉你什么时候买、什么时候卖。**

## 快速开始

```bash
pip install -r requirements.txt
python3 dashboard.py
# 浏览器打开 http://localhost:8888
```

## Dashboard 四个窗口

| 窗口 | 功能 |
|------|------|
| 📡 信号监控 | 实时行情 + 14种策略信号 + 综合建议 + K线弹窗 |
| 💼 我的持仓 | 添加/编辑/删除持仓，自动计算盈亏，支持手续费率设置 |
| 📈 策略回测 | 选择品种+时间范围，一键回测全部策略，输出收益/回撤/夏普 |
| 🧪 测试 | 极值交叉策略专用测试 — Canvas交互图表 + 7种周期切换 + 十字光标 |

## 内置策略 (14种)

| 策略 | 原理 | 买入 | 卖出 |
|------|------|------|------|
| 极值交叉 | 线A(H→L→H) × 线B(L→H→L) 交叉 | 收盘>交叉点 | 收盘<交叉点 |
| 双均线 | MA5 × MA20 | 金叉 | 死叉 |
| RSI | 相对强弱 (Wilder平滑) | <30 超卖 | >70 超买 |
| 布林带 | 价格通道 (2σ) | 触及下轨 | 触及上轨 |
| 涨速监控 | 分钟线短时涨跌 | 15min急跌>2% | 15min急涨>2% |
| 量价异动 | 成交量突变 | 放量上涨 | 放量下跌 |
| MACD | 指数平滑异同 | 金叉 | 死叉 |
| KDJ | 随机指标 | 超卖金叉 | 超买死叉 |
| CCI | 商品通道指数 | <-100 超卖 | >100 超买 |
| Williams %R | 威廉指标 | <-80 超卖 | >-20 超买 |
| ADX | 趋势强度 + DI | 强趋势+DI>-DI | 强趋势-DI>+DI |
| SAR | 抛物线转向 | 翻转至下方 | 翻转至上方 |
| OBV | 能量潮 (量价背离) | OBV确认多头 | OBV确认空头 |
| TRIX | 三重指数平滑 | 金叉 | 死叉 |

信号综合：加权评分制，-100 ~ +100，强买/强卖/中性五档。

## 数据源

三源轮询，自动切换：
- **腾讯财经** (主力源, ~100ms, 批量接口)
- **东方财富** (备用源, ~1200ms, 含K线接口)
- **AKShare** (T+0 品种列表自动发现)

实时行情校验：自动过滤异常价格、涨跌停超限、高低倒挂等脏数据。

## 配置

### 环境变量

复制 `.env.example` 为 `.env`，按需修改：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EASTMONEY_UT` | 东方财富 API ut 参数 | 内置默认值 |
| `EASTMONEY_SEARCH_TOKEN` | 东方财富搜索 token | 内置默认值 |

### 编辑 `signal_engine/config.py`

#### 策略参数

每个策略可独立开关、调整阈值：

```python
STRATEGY_PARAMS = {
    "dual_ma":   {"fast_period": 5, "slow_period": 20, "enabled": True},
    "rsi":       {"period": 14, "oversold": 30, "overbought": 70, "enabled": True},
    "bollinger": {"period": 20, "std_mult": 2.0, "enabled": True},
    "hl_cross":  {"tolerance_pct": 0.5, "enabled": True},
    # ...
}
```

#### 运行配置

```python
RUN_CONFIG = {
    "refresh_seconds": 30,   # 刷新间隔(秒)
    "history_days": 60,      # 拉取历史K线天数
    "market_open": "09:30",  # 开盘时间
    "market_close": "15:00", # 收盘时间
    "alert_cooldown": 300,   # 同一信号冷却时间(秒)
}
```

## 信号 → 推荐单 → 交易记录 流程

```
策略信号触发
  → 综合评分达到阈值 (强买/强卖)
    → 生成推荐单 (recommendations.py)
      → 用户在 Dashboard 确认/忽略
        → 确认后自动写入交易记录 (trades.py)
          → 自动计算手续费、盈亏、累计盈亏
```

## 安装 (可选)

```bash
pip install -e .           # 开发模式安装
pip install -e ".[dev]"    # 含测试依赖
pytest -v                  # 运行测试
```

---

## 项目结构

```
momo/                                    # 项目根目录
│
├── dashboard.py                         # ★ 主入口：FastAPI 应用，启动 uvicorn 服务
│                                        #   - 创建 FastAPI 实例，挂载路由和静态文件
│                                        #   - lifespan 中启动 data_loop 后台数据推送循环
│                                        #   - 监听 127.0.0.1:8888
│
├── pyproject.toml                       # Python 包配置 (hatchling)
│                                        #   - 包名: signal_engine
│                                        #   - CLI 入口: momo → signal_engine.dashboard:main
│                                        #   - 依赖: curl_cffi, pandas, numpy, fastapi, uvicorn, akshare
│
├── requirements.txt                     # pip 依赖列表 (与 pyproject.toml 同步)
├── .env.example                         # 环境变量模板 (东财 API ut/token)
├── .gitignore                           # 忽略 __pycache__, data/*.json
├── README.md                            # ← 本文件
│
├── signal_engine/                       # ★ Python 包 (核心后端)
│   │
│   ├── __init__.py                      # 包声明，__version__ = "1.0.0"
│   ├── __main__.py                      # python -m signal_engine 入口，调用 dashboard.main()
│   │
│   ├── config.py                        # ★ 全局配置中心
│   │                                    #   - PROJECT_DIR / DATA_DIR: 路径常量
│   │                                    #   - STRATEGY_PARAMS: 14种策略的参数 (周期、阈值、开关)
│   │                                    #   - RUN_CONFIG: 运行参数 (刷新间隔、交易时间、冷却时间)
│   │                                    #   - 纯配置，不含 I/O
│   │
│   ├── core/                            # 核心逻辑层
│   │   ├── __init__.py                  # 空
│   │   │
│   │   ├── signal.py                    # ★ 信号类型系统
│   │   │                              #   - SignalType 枚举: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
│   │   │                              #   - Signal 数据类: strategy, signal, reason, confidence, details
│   │   │                              #   - Signal.score 属性: 映射为 -100~+100 数值
│   │   │                              #   - combine_signals(): 多策略信号加权综合 → 综合建议
│   │   │                              #     评分阈值: >=60 强买, >=20 买, <=-60 强卖, <=-20 卖
│   │   │
│   │   ├── strategies.py                # ★ 14种技术策略实现
│   │   │                              #   - strategy_dual_ma(): 双均线 (MA5×MA20 金叉/死叉)
│   │   │                              #   - strategy_rsi(): RSI 超买超卖 (Wilder EMA 平滑)
│   │   │                              #   - strategy_bollinger(): 布林带 (MA±2σ 通道)
│   │   │                              #   - strategy_momentum(): 涨速监控 (N分钟急涨急跌)
│   │   │                              #   - strategy_volume(): 量价异动 (成交量突变×价格方向)
│   │   │                              #   - strategy_macd(): MACD (EMA12-EMA26 金叉/死叉)
│   │   │                              #   - strategy_kdj(): KDJ 随机指标 (超买超卖+交叉)
│   │   │                              #   - strategy_cci(): CCI 商品通道指数
│   │   │                              #   - strategy_williams(): Williams %R 威廉指标
│   │   │                              #   - strategy_adx(): ADX 趋势强度 + DI方向
│   │   │                              #   - strategy_sar(): Parabolic SAR 抛物线转向
│   │   │                              #   - strategy_obv(): OBV 能量潮 (量价背离检测)
│   │   │                              #   - strategy_trix(): TRIX 三重指数平滑
│   │   │                              #   - strategy_hl_cross(): 极值交叉 (线A×线B结构断裂)
│   │   │                              #   - _find_crossover(): 交叉点数学计算
│   │   │                              #   - STRATEGY_FNS: 策略注册表 dict
│   │   │
│   │   └── state.py                     # ★ 运行时状态管理 (AppState 数据类)
│   │                                    #   - signal_history: 信号历史 (持久化到 JSON)
│   │                                    #   - price_history: 分钟级价格轨迹 (前端折线图)
│   │                                    #   - kline_cache: K线缓存 (60s TTL)
│   │                                    #   - t0_cache: T+0 品种列表缓存 (1h TTL)
│   │                                    #   - last_signal_time: 信号冷却计时
│   │                                    #   - refresh_event: 异步刷新触发器
│   │                                    #   - 方法: initialize(), trigger_refresh(),
│   │                                    #     is_signal_cooled_down(), update_price(),
│   │                                    #     get_kline_cached(), set_kline_cached()
│   │
│   ├── api/                             # API 层
│   │   ├── __init__.py                  # 空
│   │   │
│   │   ├── collector.py                 # ★ 数据采集调度 (核心循环)
│   │   │                              #   - init_api(): 初始化数据目录和状态
│   │   │                              #   - collect_data(): 主采集函数
│   │   │                              #     1. 读取持仓列表
│   │   │                              #     2. 并发拉取: 实时行情(fetch_batch) + 日K线 + 5min线
│   │   │                              #     3. 运行所有启用策略 → 生成信号列表
│   │   │                              #     4. combine_signals() 综合评分
│   │   │                              #     5. 强信号 → create_recommendation() 推荐单
│   │   │                              #     6. 返回完整数据包 (etfs, alerts, total_pnl)
│   │   │                              #   - _run_strategies_for_etf(): 对单个品种运行全部策略
│   │   │                              #   - _fetch_all_daily_klines(): 批量拉取+缓存日K线
│   │   │                              #   - search_etf() / do_update_t0(): 对外接口
│   │   │                              #   - get_state() / get_refresh_event(): 状态访问
│   │   │
│   │   ├── routes.py                    # ★ FastAPI 路由 + WebSocket
│   │   │                              #   - REST API 端点:
│   │   │                              #     GET  /api/kline/{code}?period=&count=&market=  → K线数据
│   │   │                              #     GET  /api/realtime/{code}?market=              → 实时行情
│   │   │                              #     GET  /api/positions                             → 持仓列表
│   │   │                              #     POST /api/positions/{code}                      → 添加/更新持仓
│   │   │                              #     POST /api/positions/{code}/update               → 加仓/减仓
│   │   │                              #     DELETE /api/positions/{code}                    → 删除持仓
│   │   │                              #     GET  /api/search_etf?q=                         → 搜索品种
│   │   │                              #     GET  /api/signals?limit=                        → 信号历史
│   │   │                              #     GET  /api/t0_etfs                               → T+0 品种列表
│   │   │                              #     POST /api/t0_etfs/update                        → 刷新T+0列表
│   │   │                              #     GET  /api/trades                                → 交易记录
│   │   │                              #     POST /api/trades                                → 添加交易
│   │   │                              #     DELETE/PUT /api/trades/{id}                     → 删除/修改交易
│   │   │                              #     GET  /api/recommendations                       → 推荐单列表
│   │   │                              #     POST /api/recommendations/{id}/confirm          → 确认推荐
│   │   │                              #     POST /api/recommendations/{id}/ignore           → 忽略推荐
│   │   │                              #     POST /api/backtest                              → 运行回测
│   │   │                              #   - WebSocket /ws: 实时数据推送 (JSON)
│   │   │                              #   - data_loop(): 后台循环, 每30s采集+广播
│   │   │                              #   - 支持 refresh_event 即时触发刷新
│   │   │
│   │   └── search.py                    # 品种搜索模块
│   │                                    #   - search_etf(): 东方财富搜索 API + 腾讯行情补全
│   │                                    #   - _fetch_prices(): 批量拉取搜索结果实时价格
│   │                                    #   - 返回: code, name, market, is_t0, t0_type, price
│   │
│   ├── data/                            # 数据层 (持久化 + 业务逻辑)
│   │   ├── __init__.py                  # 空
│   │   │
│   │   ├── store.py                     # JSON 持久化工具
│   │   │                              #   - ensure_data_dir(): 确保 data/ 目录存在
│   │   │                              #   - load_json(filename, default): 从 data/ 读取
│   │   │                              #   - save_json(filename, data): 写入 data/
│   │   │
│   │   ├── positions.py                 # 持仓管理 + 操作建议
│   │   │                              #   - Position 数据类: code, cost, shares, note
│   │   │                              #   - load_positions(): 从配置加载持仓
│   │   │                              #   - calc_pnl(): 计算盈亏 (pnl, pnl_pct, market_value)
│   │   │                              #   - suggest_action(): 结合持仓+信号+T0/T1 给出操作建议
│   │   │                              #     T+0: 止盈1.5% 止损-2%; T+1: 止盈5% 止损-5%
│   │   │
│   │   ├── trades.py                    # 实盘交易记录管理
│   │   │                              #   - load_trades() / save_trades(): 读写 trades.json
│   │   │                              #   - add_trade(): 添加交易并重算所有盈亏
│   │   │                              #   - delete_trade() / update_trade(): CRUD
│   │   │                              #   - recalc_trades(): 按时间排序，逐笔计算
│   │   │                              #     - 买入: 记录开仓，计算手续费
│   │   │                              #     - 卖出: 匹配买入记录 (FIFO)，计算毛利/净利/累计
│   │   │                              #   - calc_commission(): 手续费 = 价格×股数×费率 (默认万三)
│   │   │                              #   - get_trade_summary(): 总交易/总盈亏/胜率
│   │   │
│   │   └── recommendations.py           # 推荐交易管理
│   │                                    #   - create_recommendation(): 信号触发 → 生成推荐单
│   │                                    #     - 10分钟冷却 (同品种同方向)
│   │                                    #     - 卖出推荐需有持仓
│   │                                    #     - suggest_shares(): 自动计算建议仓位 (~13000元)
│   │                                    #   - get_pending() / get_all(): 查询推荐单
│   │                                    #   - confirm_recommendation(): 确认 → 自动写入交易记录
│   │                                    #   - ignore_recommendation(): 忽略
│   │                                    #   - cleanup_old(): 清理7天前的已处理推荐
│   │
│   └── services/                        # 服务层 (外部数据源 + 计算引擎)
│       ├── __init__.py                  # 空
│       │
│       ├── feed.py                      # ★ 数据源模块 (双源轮询)
│       │                              #   - 腾讯财经 (主力, ~100ms):
│       │                              #     _fetch_tencent(): 单品种实时行情
│       │                              #     fetch_batch(): 批量实时行情 (一次请求多品种)
│       │                              #   - 东方财富 (备用, ~1200ms):
│       │                              #     _fetch_eastmoney(): 单品种实时行情
│       │                              #     fetch_history_kline(): 日K线 (东财 API)
│       │                              #     fetch_minute_kline(): 分钟K线 (5/15/30/60min)
│       │                              #     _fetch_kline_single(): 统一K线获取 (日/周/月/分钟)
│       │                              #     fetch_batch_kline(): 批量K线 (ThreadPoolExecutor)
│       │                              #   - 请求节流: _throttle() 线程安全，同源最小间隔
│       │                              #   - 数据校验:
│       │                              #     _validate_realtime(): 过滤异常价/涨跌停超限/高低倒挂
│       │                              #     _validate_kline(): 过滤零价/负量/高<低
│       │                              #   - fetch_realtime(): 统一接口，腾讯失败自动切东财
│       │                              #   - is_market_open(): 判断交易时间 (工作日 9:30-11:30, 13:00-15:00)
│       │                              #   - KLT_MAP: 周期映射 (1min→"1", daily→"101", weekly→"102"...)
│       │
│       ├── backtest.py                  # ★ 回测引擎
│       │                              #   - run_backtest(): 策略回测
│       │                              #     - 遍历K线，每根调用策略函数
│       │                              #     - 买入: 下一根开盘价+滑点 (0.1%)
│       │                              #     - 卖出: 下一根开盘价-滑点
│       │                              #     - 手续费: 万三双边
│       │                              #     - 资金管理: 95% 仓位，整数股
│       │                              #   - _calc_metrics(): 计算指标
│       │                              #     - 总收益/年化/最大回撤/夏普/盈亏比/胜率
│       │                              #   - _STRATEGY_MIN_BARS: 各策略最小K线数
│       │
│       └── t0_fetcher.py                # T+0 品种自动发现
│                                        #   - T+0 判断规则:
│                                        #     _T0_NAME_KEYWORDS: 名称关键词 → 跨境/黄金/债券/商品/货币
│                                        #     _T0_CODE_PREFIXES: 代码前缀 (511→债券, 518→黄金)
│                                        #   - 三数据源合并去重:
│                                        #     _fetch_sse_etf_akshare(): 上交所 (AKShare)
│                                        #     _fetch_eastmoney_etf(): 东方财富全量
│                                        #     _fetch_szse_etf_curl(): 深交所 (API)
│                                        #   - fetch_all_etf(): 合并三源，T+0标记取最高优先级
│                                        #   - save_t0_list() / load_t0_list(): 缓存到 JSON
│                                        #   - load_or_update(): 24小时自动刷新
│                                        #   - to_config_format(): 转为 (secid, code, name, market) 元组
│                                        #   - 可独立运行: python -m signal_engine.services.t0_fetcher
│
├── static/                              # 前端静态资源
│   ├── index.html                       # ★ Web 仪表盘 (单文件 SPA)
│   │                                    #   四个 Tab: 信号监控/持仓/回测/测试
│   │                                    #   - 信号监控:
│   │                                    #     - WebSocket 实时数据接收
│   │                                    #     - ETF 卡片渲染 (价格/涨跌/信号/持仓/推荐单)
│   │                                    #     - Canvas 迷你走势图 (drawSparkline)
│   │                                    #     - K线弹窗 (蜡烛图+MA+十字光标+缩放拖动)
│   │                                    #     - 策略表 (买卖行/实际价格/确认锁定)
│   │                                    #     - 推荐单确认/忽略流程
│   │                                    #   - 持仓管理:
│   │                                    #     - 添加/编辑/删除 (在线搜索品种)
│   │                                    #     - 手续费率设置 (万分之)
│   │                                    #   - 策略回测:
│   │                                    #     - 品种搜索+日期范围+初始资金
│   │                                    #     - 全策略对比表格 (收益/回撤/夏普/胜率)
│   │                                    #     - 权益曲线 Canvas
│   │                                    #     - 逐笔交易明细
│   │                                    #   - 测试 (极值交叉):
│   │                                    #     - Canvas 交互K线图 (缩放/拖动/十字光标)
│   │                                    #     - 7种周期切换 (5min~月K)
│   │                                    #     - 极值交叉叠加 (线A蓝色/线B橙色/交叉点红点)
│   │                                    #     - 右侧: 信号+回测统计+K线数据表(含盈亏)
│   │                                    #     - 盈亏: 买入信号当天收盘买入，持有3天后收盘卖出
│   │
│   └── style.css                        # CSS 样式 (暗色主题)
│                                        #   - CSS 变量: --bg, --card, --border, --text, --red, --green...
│                                        #   - Header / Tabs / Alert / Grid / ETF Card (3区域)
│                                        #   - 推荐单卡片 (脉冲发光边框动画)
│                                        #   - 策略表 (买卖行/锁定态/确认按钮)
│                                        #   - K线弹窗 / 模态框 / 搜索下拉
│                                        #   - 测试标签页专用样式 (信号卡片/回测统计/数据表)
│                                        #   - 响应式适配 (768px / 900px 断点)
│
└── tests/                               # 测试
    ├── __init__.py                      # 空 (注释: # tests)
    │
    ├── conftest.py                      # pytest 共用 fixtures
    │                                    #   - trending_up_df: 60天稳步上涨
    │                                    #   - trending_down_df: 60天稳步下跌
    │                                    #   - golden_cross_df: MA5 上穿 MA20 金叉场景
    │                                    #   - death_cross_df: MA5 下穿 MA20 死叉场景
    │                                    #   - oversold_rsi_df: RSI 超卖数据
    │                                    #   - oversold_rsi_recovering_df: RSI 超卖后回升
    │                                    #   - bollinger_touch_lower_df: 价格触及布林带下轨
    │                                    #   - flat_df: 正弦波横盘震荡
    │
    ├── test_strategies.py               # 13种策略 + 综合评分 测试
    │                                    #   - TestStrategyRegistry: 注册表完整性
    │                                    #   - TestEmptyData / TestInsufficientData: 边界情况
    │                                    #   - TestDualMA: 金叉/死叉/趋势/横盘
    │                                    #   - TestRSI: 超卖/回升/中性
    │                                    #   - TestBollinger: 触下轨/上轨/详情字段
    │                                    #   - TestMomentum: 横盘无信号/急跌
    │                                    #   - TestVolumeAnomaly: 放量涨/放量跌
    │                                    #   - TestMACD: 趋势信号
    │                                    #   - TestKDJ: 超卖/趋势
    │                                    #   - TestCCI / TestWilliams / TestADX / TestSAR / TestOBV / TestTRIX
    │                                    #   - TestSignalCombination: 综合评分逻辑
    │                                    #   - TestAppState: 信号冷却/价格历史限制
    │
    └── test_hl_cross.py                 # 极值交叉策略专项测试
                                        #   - TestCrossoverCalc: 交叉点数学验证
                                        #     - 用户原始例子 (H10/L2 → H6/L4 → H3/L1 → 交叉3.5)
                                        #     - 平行线/段外交叉/对称场景
                                        #   - TestUserExample: 完整信号验证
                                        #     - 收盘>交叉点 → 买入
                                        #     - 收盘<交叉点 → 卖出
                                        #     - 收盘≈交叉点 → 持有观望
                                        #   - TestSyntheticScenarios: 合成数据压力测试
                                        #   - TestBacktest: 简易回测
                                        #     - 300根K线，买入持有3天
                                        #     - 多种子稳定性验证 (10个种子)
                                        #   - TestRegistration: 策略注册验证
```

## License

MIT
