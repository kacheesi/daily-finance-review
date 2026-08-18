# 自动化金融市场每日复盘系统

每天 17:00 自动采集 **A 股 / 商品期货 / 数字货币** 收盘数据 → 技术分析 → AI 复盘 → 生成可视化 HTML Dashboard（`daily_report.html`）。

## 功能特性

| 模块 | 内容 |
|---|---|
| A股大盘 | 9 大指数（上证/深成/创业板/科创50/沪深300/中证500/1000/A50/A500）、成交额、涨跌家数、涨停跌停、市场情绪、0-100 市场评分、状态判定（强势上涨/震荡/弱势/恐慌等） |
| 行业板块 | 14 个关注行业：涨跌幅、强弱评级、热度排名、领涨股（含行业热力图） |
| 自选股票 | 20 只默认池（可 Excel/CSV/JSON 导入）：收盘/换手/市值/PE/PB + MA5/10/20/60、MACD、RSI、KDJ、布林带 → 趋势、技术状态、风险等级、基本面评级、综合评级 A/B/C/D |
| 商品期货 | 沪金/沪银/原油/沪铜/螺纹钢/铁矿石/豆粕/玉米/豆油：涨跌、趋势、风险提示 |
| 数字货币 | BTC/ETH（CoinGecko）：价格、24h 涨跌、情绪、风险（仅辅助） |
| AI 总结 | 市场总结 5 问 + 基金经理视角（Agent 生成；无 AI 时规则兜底） |
| 可视化 | ECharts 10 图（评分仪表盘/指数涨跌/情绪雷达/行业热力/资金/自选股 K 线/期货/币价），CDN→本地→纯表格三级降级 |

## 目录结构

```
每日复盘/
├── run_daily.py                # 主入口（任务计划/Cron/开机补跑）
├── requirements.txt
├── config/
│   ├── settings.json           # 评分阈值/重试/指标参数
│   ├── watchlist.json          # 自选股池（默认20只）
│   └── market_codes.json       # 指数/期货/币代码映射
├── src/
│   ├── scheduler.py            # 主流程编排 + catch-up 补执行
│   ├── collector/              # 腾讯行情/新浪情绪板块期货/CoinGecko 币/AkShare 备用
│   ├── analyzer/               # 技术指标/市场评分/个股评级/期货币/行业
│   ├── ai/                     # 规则兜底总结 + Agent 提示词
│   ├── storage/                # SQLite 9表
│   ├── report/                 # Jinja2 模板 + ECharts 生成器
│   └── utils/                  # 日志/重试/交易日
├── data/
│   ├── market.db               # SQLite 历史库
│   ├── raw/<date>/collection.json   # 当日采集数据（两通道共用）
│   ├── reports/daily_report.html    # 最新报告（+ 按日归档）
│   └── vendor/echarts.min.js   # 离线图表库
└── scripts/                    # init_db / import_watchlist / seed_vendor / agent_tools
```

## 部署教程

### 1. 环境准备（一次性）

```bash
# 创建虚拟环境并安装依赖
py -3.13 -m venv C:\Users\Administrator\.workbuddy\binaries\python\envs\default
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\pip install -r requirements.txt

# 初始化数据库
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python scripts\init_db.py

# 下载 ECharts 离线包（网络不可用时报告自动降级为纯表格）
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python scripts\seed_vendor.py
```

### 2. 配置自选股票池

默认 20 只已预置（贵州茅台/宁德时代/比亚迪/中芯国际…）。**两种方式**：

**方式 A（推荐）：网页管理**
```bash
python scripts\watchlist_server.py        # 启动管理服务
```
打开 http://127.0.0.1:8787 → 输入 6 位代码即可添加（名称自动获取），一键删除。
每日报告的右上角也有「＋ 管理自选股」按钮直达。

**方式 B：命令行导入**
```bash
# CSV/Excel 需含 code（6位代码）与 name 列；JSON 可为 {"watchlist":[...]} 或数组
python scripts\import_watchlist.py --file my_stocks.csv        # 合并
python scripts\import_watchlist.py --file my_stocks.json --replace   # 替换
```

### 3. 手动运行验证

```bash
python run_daily.py                    # 今日全流程
python run_daily.py --force            # 强制重新采集
python run_daily.py --date 2026-08-18  # 指定日期
python run_daily.py --catchup          # 补执行缺失交易日
```

打开 `data\reports\daily_report.html` 查看报告。

### 4. 配置定时任务（每日 17:00）

**方式 A：WorkBuddy 自动化（推荐，含 AI 分析）**
在 WorkBuddy 中创建自动化：每日 17:00 触发，激活「东方财富妙想 MCP」与「通达信 MCP」，执行每日复盘任务（详见自动化 prompt）。

**方式 B：Windows 任务计划程序（独立运行，AI 用规则兜底）**
```cmd
:: 每日 17:05 运行
schtasks /Create /TN "DailyFinanceReview" /SC DAILY /ST 17:05 /TR "\"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe\" \"C:\Users\Administrator\WorkBuddy\每日复盘\run_daily.py\"" /F

:: 开机补跑（若 17:00 后电脑未开机，开机后自动补当天）
schtasks /Create /TN "DailyFinanceReviewCatchup" /SC ONSTART /TR "\"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe\" \"C:\Users\Administrator\WorkBuddy\每日复盘\run_daily.py\" --catchup" /F
```

**Linux/Mac Cron：**
```cron
5 17 * * 1-5 /usr/bin/python3 /path/to/每日复盘/run_daily.py
```

### 5. catch-up 补执行机制

- 系统以 SQLite `run_log` 表记录最近成功运行日；
- 开机触发 `--catchup` 时：从缺失日逐日补到今日（仅交易日，且今日 17:00 前不提前跑）；
- 单日失败写 `run_log=failed`，次日自动重试，不影响后续日期。

## 数据源说明

| 数据 | 通道A（WorkBuddy自动化） | 通道B（独立脚本，按优先级） |
|---|---|---|
| 指数行情（含中证A50/主力资金） | 通达信 MCP（tdx_quotes） | **东方财富 push2delay**（延时行情，收盘后=准确收盘价）→ 腾讯兜底 |
| 市场情绪/涨跌家数/涨停跌停 | 东方财富妙想 MCP | **东方财富 clist 全A统计**（含主力资金）→ 新浪兜底 |
| 行业板块（含资金流） | 东方财富妙想 MCP | **东方财富行业板块**（细分行业映射14关注行业）→ 新浪兜底 |
| 指数/个股K线 | 通达信 MCP（tdx_kline） | 腾讯（web.ifzq.gtimg.cn；A50 无腾讯数据时标注缺失） |
| 自选股行情（含主力资金/PE/PB） | 东方财富妙想 MCP | **东方财富 ulist** → 腾讯兜底 |
| 基本面（ROE/营收增速/毛利率） | 东方财富妙想 MCP | **东方财富数据中心**（RPT_F10_FINANCE_MAINFINADATA）→ 新浪兜底 |
| 商品期货 | 通达信 MCP（tdx_futures_quotes） | 新浪期货日线 |
| 数字货币 | CoinGecko / 网络检索 | CoinGecko API |
| 备用 | — | AkShare（东财 push2 可达环境） |

> 注意：
> 1. 北向资金实时数据自 2024-08 起停止披露，系统以**主力资金流向（东财 f62 字段）**替代，9 大指数与全市场/行业/个股均有该数据。
> 2. 本机网络对 push2.eastmoney.com 被阻断，但 **push2delay / datacenter-web / np-listapi 可达**，故脚本通道走延时行情链路（收盘后数据即最终收盘价）。

> 注意：北向资金实时数据自 2024-08 起停止披露，系统以主力资金流向替代（脚本通道该字段缺失时评分自动归一化，不影响总分口径）。

## 常见问题

- **报告图表空白**：检查网络（ECharts CDN）或 `data/vendor/echarts.min.js` 是否存在；两者均不可用则自动显示表格版。
- **部分数据缺失**：报告顶部会显示 ⚠️ 数据提示，`run_log` 标记为 `partial`；缺失数据源在下次运行自动恢复。
- **期货/币数据源限流**：新浪与 CoinGecko 偶发限流（429/456），系统已内置退避重试与降级标记。
- **自选股代码格式**：6 位数字即可（如 600519），自动识别沪/深/北交所。

## 后续扩展

港股/美股/ETF、历史趋势对比页、邮件/企微推送、财报日历提醒、FastAPI 本地服务化、回测模块。
