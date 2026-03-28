# MoreMoney 项目操作文档

> 基于 LangGraph 1.1 + 通义千问（Qwen-Max）的 A 股 AI 全自动交易系统
> 最后更新：2026-03-28

---

## 目录

1. [环境准备](#1-环境准备)
2. [项目安装](#2-项目安装)
3. [配置说明](#3-配置说明)
4. [启动交易系统](#4-启动交易系统)
5. [启动可视化 UI](#5-启动可视化-ui)
6. [UI 界面使用说明](#6-ui-界面使用说明)
7. [REST API 接口文档](#7-rest-api-接口文档)
8. [交易模式切换](#8-交易模式切换)
9. [风控参数调整](#9-风控参数调整)
10. [四维权重说明](#10-四维权重说明)
11. [自我进化机制](#11-自我进化机制)
12. [数据源说明](#12-数据源说明)
13. [目录结构说明](#13-目录结构说明)
14. [常见问题排查](#14-常见问题排查)
15. [接入真实 AgentState 数据](#15-接入真实-agentstate-数据)
16. [注意事项](#16-注意事项)

---

## 1. 环境准备

### 1.1 Python 版本要求

Python >= 3.10，建议使用虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate      # Linux/macOS
```

### 1.2 系统依赖

| 组件 | 说明 |
|---|---|
| Python 3.10+ | 主运行环境 |
| pip | 包管理器 |
| 网络连接 | 通达信/通义千问/akshare |
| 迅投 QMT（可选）| 仅实盘模式需要 |

---

## 2. 项目安装

### 2.1 安装主系统依赖

```bash
cd e:\Project\py\Agent\MoreMoney
pip install -r requirements.txt
```

| 包名 | 版本 | 用途 |
|---|---|---|
| langgraph | 1.1.3 | 多 Agent 图编排 |
| langchain | 1.2.13 | LLM 工具链 |
| openai | 2.30.0 | 通义千问 API 兼容接口 |
| pytdx | 1.72 | 同花顺通达信免费数据 |
| akshare | >=1.14.0 | 新闻/资金/公告 |
| chromadb | 1.0.4 | 向量数据库 |
| pydantic | 2.12.5 | 数据校验 |
| rich | >=14.0.0 | 终端美化 |

### 2.2 安装 UI 依赖

```bash
pip install -r ui/requirements_ui.txt
```

### 2.3 验证安装

```bash
python check_syntax.py
python -c "from ui.app import app; print('UI OK')"
```

---

## 3. 配置说明

### 3.1 创建 .env

```bash
copy .env.example .env   # Windows
cp .env.example .env     # Linux
```

关键字段说明：

```
DASHSCOPE_API_KEY=sk-xxxx     # 必填，通义千问 API Key
TRADING_MODE=paper             # paper=模拟盘  live=实盘
INITIAL_CAPITAL=1000000.0     # 模拟盘初始资金
QWEN_MODEL=qwen-max            # 可改 qwen-turbo 降低成本
MAX_ITERATIONS_PER_DAY=20     # 每日最大分析轮次
ANALYSIS_INTERVAL_MINUTES=15  # 每轮间隔（分钟）
TOP_N_STOCKS=20                # 每轮分析标的数
LOG_LEVEL=INFO                 # DEBUG/INFO/WARNING/ERROR
TUSHARE_TOKEN=                 # 可选，增强财务数据
XT_ACCOUNT=                    # 实盘专用
XT_CLIENT_PATH=C:/国金证券QMT交易端/userdata_mini
```

### 3.2 配置文件一览

| 文件 | 说明 | 是否自动生成 |
|---|---|---|
| .env | 环境变量 | 手动创建 |
| config/settings.py | 全局配置类 | 已存在 |
| config/risk_params.py | 风控参数 | 已存在，可修改 |
| config/dimension_weights.json | 四维权重 | 自动生成 |
| storage/database/memory.db | SQLite 长期记忆 | 自动生成 |
| storage/vector_store/ | ChromaDB 向量存储 | 自动生成 |
| logs/trading.log | 交易日志 | 自动生成 |

---

## 4. 启动交易系统

### 4.1 模拟盘启动

```bash
python main.py
```

启动后终端输出示例：

```
==================================================
MoreMoney 启动 | 模式: paper | 资金: 1,000,000
==================================================
2026-03-28 09:30:00 | INFO | 市场开盘，扫描股票池（300只）
2026-03-28 09:31:22 | INFO | [Iter 1] risk=medium signals=12 decisions=4
```

### 4.2 手动触发策略优化

```bash
python main.py optimize
```

执行流程：读取近30条记录 → LLM分析胜率/盈亏 → 写入新四维权重到 config/dimension_weights.json。

### 4.3 优雅停止

按 Ctrl+C，系统等待本轮完成后安全退出，不中断未完成的订单。

### 4.4 实时查看日志

```bash
Get-Content logs\trading.log -Wait   # Windows
tail -f logs/trading.log               # Linux
```

---

## 5. 启动可视化 UI

UI 与交易系统独立运行，可分开或同时启动。

### 5.1 开发模式

```bash
python -m flask --app ui.app run --host 0.0.0.0 --port 5688
```

### 5.2 后台静默启动（Windows）

```powershell
Start-Process python -ArgumentList '-m','flask','--app','ui.app','run','--host','0.0.0.0','--port','5688','--no-debugger' -WindowStyle Hidden
```

### 5.3 后台启动（Linux / macOS）

```bash
nohup python -m flask --app ui.app run --host 0.0.0.0 --port 5688 > logs/ui.log 2>&1 &
```

### 5.4 访问地址

| 场景 | 地址 |
|---|---|
| 本机 | http://127.0.0.1:5688 |
| 局域网 | http://<本机IP>:5688 |

### 5.5 停止 UI

```bash
# 开发模式：Ctrl+C
# Windows 后台：Get-Process python | Stop-Process -Force
# Linux：pkill -f 'flask.*ui.app'
```

---

## 6. UI 界面使用说明

### 6.1 整体布局

```
顶栏：Logo | 交易模式 | 交易阶段 | 迭代进度 | 时钟
─────────────────────────────────────────────────────
左侧导航 | 主内容区（7个面板）       | 右侧实时流
         |                          | 信号流
风险等级 |                          | 风险预警
指示灯   |                          | 持仓盈亏
─────────────────────────────────────────────────────
状态栏：session | 模式 | SSE状态 | 时间戳
```

### 6.2 各面板说明

| 面板 | 核心内容 |
|---|---|
| 系统总览 | 四大指数、资产/盈亏 KPI、30日权益曲线、绩效指标、四维权重 |
| 市场行情 | 板块热力图（颜色深浅=涨跌幅）、板块排行表 |
| 信号矩阵 | 多空雷达图、逐条信号强度条（悬停查看推理）|
| 决策引擎 | 动作/仓位/止损止盈/紧迫度/风险评分/决策理由 |
| 持仓管理 | 资产饼图、持仓明细表、仓位占比条形图 |
| 成交记录 | 时间/代码/方向/数量/成交价/金额/状态 |
| 自我进化 | 市场机制、学到的规则、成功/失败模式 |
| 系统日志 | INFO/WARN/ERR 颜色区分，最新日志置顶 |

### 6.3 实时更新频率

| 机制 | 频率 | 内容 |
|---|---|---|
| SSE 推送 | 每3秒 | 总资产、盈亏、指数、持仓现价、风险等级 |
| 定时刷新 | 每15秒 | 持仓明细、信号、决策、成交记录、饼图 |

### 6.4 颜色含义

| 颜色 | 含义 |
|---|---|
| 绿色 | 上涨 / 多头 / 盈利 / 低风险 |
| 红色 | 下跌 / 空头 / 亏损 / 高风险 |
| 青色 | 系统主色 / 技术面 |
| 紫色 | 消息面 |
| 黄色 | 警告 |
| 金色 | 基本面 / 模拟盘标识 |

---

## 7. REST API 接口文档

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | / | 主页面 HTML |
| GET | /api/state | 完整系统状态 |
| GET | /api/portfolio | 组合状态 |
| GET | /api/signals | 信号列表 |
| GET | /api/decisions | AI 决策列表 |
| GET | /api/orders | 成交订单 |
| GET | /api/market | 大盘+板块 |
| GET | /api/risk | 风险等级+预警 |
| GET | /api/logs | 系统日志 |
| GET | /api/memory | Agent 记忆 |
| GET | /api/equity_curve | 30日权益曲线 |
| GET | /api/weights | 当前四维权重 |
| GET | /stream | SSE 实时流 |

### 7.1 调用示例

```bash
curl http://127.0.0.1:5688/api/portfolio
curl http://127.0.0.1:5688/api/signals
curl -N http://127.0.0.1:5688/stream
```

### 7.2 /api/portfolio 返回结构

```json
{
  "total_assets": 1032580.00,
  "cash": 412800.00,
  "daily_pnl": 8420.50,
  "total_pnl": 32580.00,
  "max_drawdown": 0.042,
  "win_rate": 0.673,
  "sharpe_ratio": 1.87,
  "positions": {
    "600519": {
      "name": "贵州茅台", "qty": 20, "cost": 1680.0,
      "current_price": 1724.5, "market_value": 34490,
      "pnl_pct": 0.0265, "sector": "食品饮料"
    }
  }
}
```

### 7.3 SSE 推送数据结构

```json
{
  "ts": "10:32:15",
  "total_assets": 1033120.50,
  "daily_pnl": 8960.50,
  "risk_level": "medium",
  "iteration_count": 15,
  "indices": {"sh_index": {"price": 3289.12, "change_pct": 0.87}},
  "positions": {"600519": {"current_price": 1726.0, "pnl_pct": 0.027}}
}
```

---

## 8. 交易模式切换

### 8.1 模拟盘转实盘步骤

1. 安装迅投 QMT 客户端（从券商获取）
2. 安装 xtquant（QMT Python SDK）
3. 修改 .env：

```
TRADING_MODE=live
XT_ACCOUNT=你的资金账号
XT_CLIENT_PATH=C:/国金证券QMT交易端/userdata_mini
```

4. 确保 QMT 客户端已登录并保持运行
5. 启动：python main.py

### 8.2 实盘转模拟盘

修改 .env 中 TRADING_MODE=paper 后重启即可。

### 8.3 两种模式对比

| 特性 | 模拟盘 | 实盘 |
|---|---|---|
| 资金 | 内存虚拟 | 真实券商资金 |
| 成交 | 立即模拟 | 迅投 QMT 下单 |
| 风险 | 无 | 真实资金损失风险 |
| 依赖 | 无 | xtquant + QMT 客户端 |
| 建议 | 新策略先验证 | 充分验证后再使用 |

---

## 9. 风控参数调整

编辑 `config/risk_params.py`，重启后生效。

| 参数 | 默认值 | 说明 |
|---|---|---|
| MAX_SINGLE_POSITION_PCT | 0.20 | 单股最大仓位 20% |
| MAX_SECTOR_CONCENTRATION_PCT | 0.40 | 单板块最大仓位 40% |
| MAX_TOTAL_POSITION_PCT | 0.80 | 最大总仓位 80% |
| DEFAULT_STOP_LOSS_PCT | 0.07 | 默认止损 -7% |
| DEFAULT_TAKE_PROFIT_PCT | 0.20 | 默认止盈 +20% |
| TRAILING_STOP_TRIGGER_PCT | 0.10 | 移动止损触发线（盈利10%）|
| TRAILING_STOP_PCT | 0.05 | 移动止损幅度 5% |
| MAX_DAILY_LOSS_PCT | 0.02 | 日内最大亏损 2%（触发停止）|
| MAX_DAILY_TRADES | 20 | 每日最大交易次数 |
| MAX_DRAWDOWN_LIMIT | 0.15 | 最大回撤熔断线 15% |
| MARKET_CIRCUIT_BREAKER_PCT | 5.0 | 大盘涨跌 ±5% 触发熔断 |
| MIN_ORDER_AMOUNT | 10000 | 最小单笔金额（元）|
| MAX_ORDER_AMOUNT | 200000 | 最大单笔金额（元）|
| MIN_SIGNAL_SCORE | 0.30 | 最低综合信号分才建仓 |

### 9.1 保守型配置建议

```python
MAX_SINGLE_POSITION_PCT = 0.10   # 单股不超过10%
MAX_TOTAL_POSITION_PCT = 0.60    # 总仓位不超过60%
DEFAULT_STOP_LOSS_PCT = 0.05     # 止损收紧到5%
MAX_DAILY_LOSS_PCT = 0.01        # 日亏1%即停
```

### 9.2 激进型配置建议

```python
MAX_SINGLE_POSITION_PCT = 0.30
DEFAULT_TAKE_PROFIT_PCT = 0.30
MIN_SIGNAL_SCORE = 0.20
```

---

## 10. 四维权重说明

### 10.1 默认权重

| 维度 | 权重 | 分析内容 |
|---|---|---|
| 技术面 technical | 30% | 均线/MACD/KDJ/RSI/布林带/K线形态 |
| 消息面 sentiment | 25% | 新闻/公告/社交媒体情绪 |
| 资金面 capital_flow | 25% | 北向/主力/融资融券/大宗交易 |
| 基本面 fundamental | 20% | 财报/估值/行业对比 |

### 10.2 手动调整权重

创建或编辑 `config/dimension_weights.json`：

```json
{
  "technical": 0.35,
  "sentiment": 0.20,
  "capital_flow": 0.30,
  "fundamental": 0.15
}
```

四个权重之和必须等于 1.0，否则使用默认值。

### 10.3 自动优化权重

```bash
python main.py optimize
```

系统根据近30条历史交易结果自动计算并写入最优权重，下一轮生效。
UI「系统总览」页面实时显示当前权重。

---

## 11. 自我进化机制

### 11.1 反思流程（每轮自动）

```
每轮交易结束
  └─► ReflectionAgent
        ├── LLM 复盘本轮操作
        ├── 提取新规则 → 写入 SQLite
        └── 判断是否需要策略大调整
```

### 11.2 策略优化流程

```
StrategyOptimizer
  ├── 读取近30条交易记录
  ├── LLM 分析胜率/盈亏分布
  ├── 输出新四维权重
  └── 写入 config/dimension_weights.json（下轮生效）
```

### 11.3 查看学到的规则

方式一：UI「自我进化」面板直接查看

方式二：命令行

```bash
python -c "
from core.memory.long_term import LongTermMemory
lm = LongTermMemory()
for r in lm.get_rules(min_confidence=0.5):
    print(r)
"
```

### 11.4 清空记忆重置学习

```bash
# Windows
del storage\database\memory.db
rd /s /q storage\vector_store
# Linux
rm storage/database/memory.db
rm -rf storage/vector_store
```

---

## 12. 数据源说明

| 数据类型 | 主数据源 | 备注 |
|---|---|---|
| 实时行情（全A股）| pytdx（免费）| 无需账号 |
| 日线/分钟线历史 | pytdx（免费）| 单次最多800条，自动分批 |
| 基本财务指标 | pytdx 扩展接口 | PE/PB/净资产 |
| 指数行情 | pytdx（免费）| 沪深主要指数 |
| 财经新闻/公告 | akshare | 需网络畅通 |
| 北向资金 | akshare | 沪深港通净买入 |
| 融资融券/大宗 | akshare | 收盘后更新 |
| 板块热力图 | akshare | 申万行业分类 |
| 实盘下单 | 迅投 QMT | 需券商开通 |

### 12.1 pytdx 服务器（自动选最低延迟）

```
119.147.212.81:7709   广州电信
221.194.181.176:7709  北京联通
120.76.152.87:7709    深圳阿里云
47.107.75.159:7709    深圳阿里云2
59.173.18.69:7709     武汉电信
210.51.39.201:7709    上海电信
```

全部失败时自动降级为模拟数据，系统不崩溃。

---

## 13. 目录结构说明

```
MoreMoney/
├── main.py                      # 程序主入口
├── check_syntax.py              # 语法检查
├── requirements.txt             # 主系统依赖
├── .env.example / .env          # 环境变量模板/实例
├── OPERATIONS.md                # 本操作文档
│
├── agents/                      # 8个 Agent
│   ├── orchestrator.py          # 编排 Agent
│   ├── technical_agent.py       # 技术面
│   ├── sentiment_agent.py       # 消息面
│   ├── capital_flow_agent.py    # 资金面
│   ├── fundamental_agent.py     # 基本面
│   ├── risk_agent.py            # 风险评估
│   ├── execution_agent.py       # 交易执行
│   └── reflection_agent.py      # 反思迭代
│
├── core/
│   ├── graph/trading_graph.py   # LangGraph 图定义
│   ├── state/agent_state.py     # 全局状态 Schema
│   └── memory/
│       ├── short_term.py        # 短期记忆（当日 deque）
│       ├── long_term.py         # 长期记忆（SQLite）
│       └── episodic.py          # 事件记忆（ChromaDB）
│
├── tools/
│   ├── market_data/             # 行情数据（pytdx）
│   ├── news/                    # 新闻/公告/情绪
│   ├── capital_flow/            # 北向/大宗/融资
│   ├── fundamental/             # 财务/估值/行业
│   ├── technical/               # 指标/形态/回测
│   └── broker/                  # 券商接口
│
├── llm/
│   ├── qwen_client.py           # 通义千问客户端
│   └── prompts/                 # Prompt 模板
│
├── config/
│   ├── settings.py              # 全局配置
│   ├── risk_params.py           # 风控参数
│   └── dimension_weights.json   # 四维权重（自动生成）
│
├── monitoring/
│   ├── dashboard.py             # 终端看板
│   ├── trade_logger.py          # 日志记录
│   └── alert_system.py          # 告警系统
│
├── self_evolution/
│   ├── performance_evaluator.py # 绩效评估
│   ├── strategy_optimizer.py    # 策略优化
│   └── knowledge_updater.py     # 知识更新
│
├── storage/
│   ├── database/memory.db       # SQLite（自动生成）
│   └── vector_store/            # ChromaDB（自动生成）
│
├── logs/trading.log             # 交易日志（自动生成）
│
└── ui/
    ├── app.py                   # Flask 后端
    ├── requirements_ui.txt      # UI 依赖
    ├── templates/index.html     # 主页面
    └── static/js/
        ├── dashboard.js         # 图表+渲染函数
        └── dashboard2.js        # SSE+定时刷新
```

---

## 14. 常见问题排查

### 14.1 pytdx 连接失败

现象：启动时报 `ConnectionError: 所有通达信服务器连接失败`

排查：
```bash
Test-NetConnection -ComputerName 119.147.212.81 -Port 7709
```

解决：
- 检查防火墙是否拦截 7709 端口
- 更换网络或使用 VPN
- 系统自动降级为模拟数据，不影响功能测试

### 14.2 通义千问 API 报错

现象：`AuthenticationError` 或 `InvalidAPIKey`

解决：
1. 检查 .env 中 DASHSCOPE_API_KEY 是否正确（以 sk- 开头）
2. 登录 https://dashscope.aliyun.com 确认 Key 有效且有余额

### 14.3 ChromaDB 初始化失败

```bash
rd /s /q storage\vector_store   # Windows
rm -rf storage/vector_store      # Linux
python main.py
```

### 14.4 UI 无法访问

```powershell
netstat -ano | findstr 5688
Get-Process python
python -m flask --app ui.app run --port 5688
```

### 14.5 pydantic-settings 报错

现象：`ImportError: cannot import name BaseSettings from pydantic`

```bash
pip install pydantic-settings>=2.7.0
```

### 14.6 langgraph 版本不兼容

```bash
pip install langgraph==1.1.3 langchain==1.2.13 --force-reinstall
```

### 14.7 SSE 连接持续断开

属于正常网络抖动，前端会自动重连。刷新页面可立即重建连接。
如持续断开，检查 Flask 进程是否正常运行。

---

## 15. 接入真实 AgentState 数据

当前 UI 使用模拟数据，接入真实系统有三种方案：

### 15.1 方案一：文件共享（最简单）

交易系统将状态写入 JSON，UI 定时读取：

```python
# monitoring/dashboard.py 中添加
import json
def export_state(state, path="storage/ui_state.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, default=str)
```

```python
# ui/app.py 修改加载逻辑
def _load_state():
    try:
        with open("storage/ui_state.json", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return _state
```

### 15.2 方案二：共享内存（同进程）

```python
# ui/app.py 顶部添加
_real_state: dict = {}
def update_ui_state(state):
    global _real_state
    with _lock:
        _real_state = dict(state)
```

### 15.3 方案三：Redis（推荐生产环境）

```python
# 交易系统推送
import redis, json
r = redis.from_url("redis://localhost:6379/0")
r.set("moremoney:state", json.dumps(state, default=str))

# ui/app.py 读取
def _load_state():
    raw = r.get("moremoney:state")
    return json.loads(raw) if raw else _state
```

---

## 16. 注意事项

### 16.1 投资风险声明

本项目仅供学习研究，不构成投资建议。
实盘前请在模拟盘充分验证，自行承担交易风险。

### 16.2 API Key 安全

- .env 已加入 .gitignore，禁止提交到代码仓库
- 定期轮换 DashScope API Key
- 不在日志中打印 Key

### 16.3 实盘前检查清单

- [ ] 模拟盘运行 >= 2 周，胜率稳定 > 55%
- [ ] 风控参数已根据自身风险承受能力调整
- [ ] QMT 客户端已登录且资金充足
- [ ] 已设置 MAX_DAILY_LOSS_PCT 日内止损
- [ ] 了解熔断触发条件和恢复方式

### 16.4 资源消耗提示

- 每轮分析约消耗 4-8 次 LLM 调用
- 建议在 DashScope 控制台设置用量告警
- ANALYSIS_INTERVAL_MINUTES 设为 30 可降低约 50% API 消耗

### 16.5 A股交易时间

周一至周五 09:30-11:30、13:00-15:00

非交易时间系统仍运行分析，但执行模块不会下单。

### 16.6 数据备份

```bash
# 备份学习记忆
copy storage\database\memory.db storage\database\memory_backup.db
```

---

*文档维护：修改系统配置或添加新功能后，请同步更新对应章节。*
