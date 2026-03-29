# ETF T+0 信号提醒系统

基于5种技术策略的 ETF T+0 盘中信号提醒工具。

**不做自动交易，只告诉你什么时候买、什么时候卖。**

## 数据源

双源轮询，自动切换：
- **腾讯财经** (主力, ~120ms)
- **东方财富** (备用, ~1200ms)

## 内置策略

| 策略 | 原理 | 买入 | 卖出 |
|------|------|------|------|
| 双均线 | MA5 × MA20 交叉 | 金叉 | 死叉 |
| RSI | 相对强弱 | <30 超卖 | >70 超买 |
| 布林带 | 价格通道 | 触及下轨 | 触及上轨 |
| 涨速监控 | 短时涨跌 | 15min 急跌>2% | 15min 急涨>2% |
| 量价异动 | 成交量突变 | 放量上涨 | 放量下跌 |

## 快速开始

```bash
pip install -r requirements.txt

# 终端模式
python3 main.py

# 可视化仪表盘 (推荐)
python3 dashboard.py
# 浏览器打开 http://localhost:8888
```

## 配置

编辑 `config.py`：

**1. 我的持仓** — 填入你的实际持仓，系统会结合成本价给操作建议：

```python
MY_POSITIONS = {
    "513100": {"cost": 1.650, "shares": 10000, "note": "纳指底仓"},
    "518880": {"cost": 5.200, "shares": 5000,  "note": "黄金观察仓"},
}
```

**2. 监控品种** — 默认覆盖15只 T+0 ETF，可增删。

**3. 策略参数** — 可开关策略、调整阈值。

## 项目结构

```
momo/
├── main.py          # 终端模式入口
├── dashboard.py     # Web 可视化仪表盘 (FastAPI + WebSocket)
├── config.py        # 品种/持仓/策略配置
├── datafeed.py      # 双源实时行情 + K线
├── strategies.py    # 5种策略
├── position.py      # 持仓盈亏 + 操作建议
├── display.py       # 终端美化输出 (Rich)
├── requirements.txt
└── README.md
```
