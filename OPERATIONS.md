# MoreMoney 项目操作文档

> 基于 LangGraph 1.1 + 通义千问（Qwen-Max）的 A 股 AI 全自动交易系统  
> 最后更新：2026-03-29

---

## 目录

1. [环境准备](#1-环境准备)
2. [安装](#2-安装)
3. [配置](#3-配置)
4. [启动交易系统](#4-启动交易系统)
5. [启动可视化 UI](#5-启动可视化-ui)
6. [前端面板说明](#6-前端面板说明)
7. [REST API 接口](#7-rest-api-接口)
8. [交易模式切换](#8-交易模式切换)
9. [风控参数调整](#9-风控参数调整)
10. [四维权重](#10-四维权重)
11. [自我进化机制](#11-自我进化机制)
12. [合规边界检查](#12-合规边界检查)
13. [数据源](#13-数据源)
14. [常见问题](#14-常见问题)
15. [接入真实 AgentState](#15-接入真实-agentstate)
16. [注意事项](#16-注意事项)

---

## 1. 环境准备

| 组件 | 要求 |
|---|---|
| Python | ≥ 3.10 |
| Node.js | ≥ 18（前端开发）|
| 网络 | 通达信/通义千问/akshare |
| 迅投 QMT | 可选，仅实盘需要 |

```bash
python -m venv venv
venv\Scripts\Activate.ps1   # Windows
```

---

## 2. 安装

```bash
pip install -r requirements.txt
pip install -r ui/requirements_ui.txt

# 前端（需 Node 18+）
cd frontend
npm install
```

---

## 3. 配置

```bash
cp .env.example .env
```

关键字段：

```
DASHSCOPE_API_KEY=sk-xxxx
TRADING_MODE=paper
INITIAL_CAPITAL=1000000.0
QWEN_MODEL=qwen-max
MAX_ITERATIONS_PER_DAY=20
ANALYSIS_INTERVAL_MINUTES=15
LOG_LEVEL=INFO
```

自动生成文件：`config/dimension_weights.json`、`storage/database/memory.db`、`storage/vector_store/`、`logs/trading.log`

---

## 4. 启动交易系统

```bash
python main.py           # 模拟盘
python main.py optimize  # 手动触发策略优化
# Ctrl+C 优雅退出
```

---

## 5. 启动可视化 UI

### Flask API 后端（:5688）

```bash
python ui/app.py
# Windows 后台：Start-Process python -ArgumentList ui/app.py -WindowStyle Hidden
```

### Vue 3 前端（:5173）

```bash
cd frontend
npm run dev
# 访问 http://127.0.0.1:5173
```

切换 Node 版本（Windows nvm）：`nvm use 18.16.1`

> Vite 自动将 `/api/*` 和 `/stream` 代理到 Flask:5688。

---

## 6. 前端面板说明

布局：顶栏 | 左侧导航 | 主面板区（13个） | 右侧实时栏

| 面板 | 内容 |
|---|---|
| 总览 | KPI卡片、四维权重、风险预警 |
| 行情 | 四大指数、板块涨跌 |
| 市场机制 | 牛熊判断、置信度、权重、信号 |
| 信号矩阵 | 多空信号、强度条 |
| 决策引擎 | 操作/仓位/止损/止盈/风险分 |
| 资金流向 | 北向、主力、板块资金流 |
| 持仓管理 | 持仓卡片（含盈亏/止损/止盈）|
| 成交记录 | 订单表含滑点 |
| 每日优选 | 评分卡片 + 手动添加 |
| Agent状态 | 8个Agent状态+耗时 |
| 风控参数 | 动态仓位仪表+参数列表 |
| 控制面板 | Kill Switch + 操作历史 |
| 系统日志 | 实时日志 + 级别过滤 |

SSE 每3秒推送，定时每15秒全量刷新。

---

## 7. REST API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/state` | 完整状态 |
| GET | `/api/portfolio` | 组合持仓 |
| GET | `/api/signals` | 信号列表 |
| GET | `/api/decisions` | AI决策 |
| GET | `/api/orders` | 成交记录 |
| GET | `/api/market` | 大盘+板块 |
| GET | `/api/capital_flow` | 资金流向 |
| GET | `/api/regime` | 市场机制 |
| GET | `/api/agents` | Agent状态 |
| GET | `/api/risk` | 风险参数 |
| GET | `/api/logs` | 系统日志 |
| GET | `/api/memory` | 记忆规则 |
| GET | `/api/equity_curve` | 权益曲线 |
| GET | `/api/weights` | 四维权重 |
| GET | `/api/watchlist` | 每日优选 |
| POST | `/api/watchlist` | 新增优选 |
| DELETE | `/api/watchlist/<code>` | 删除优选 |
| POST | `/api/kill_switch/<action>` | pause/resume/halt/emergency |
| GET | `/stream` | SSE实时流 |

---

## 8. 交易模式切换

| 特性 | 模拟盘 | 实盘 |
|---|---|---|
| 资金 | 内存虚拟 | 真实券商 |
| 成交 | 立即模拟 | QMT下单 |
| 依赖 | 无 | xtquant+QMT |

切换实盘：在 `.env` 设置 `TRADING_MODE=live`、`XT_ACCOUNT`、`XT_CLIENT_PATH`。

---

## 9. 风控参数调整

编辑 `config/risk_params.py`，重启后生效。

| 参数 | 默认值 |
|---|---|
| MAX_SINGLE_POSITION_PCT | 0.20 |
| MAX_SECTOR_CONCENTRATION_PCT | 0.40 |
| MAX_TOTAL_POSITION_PCT | 0.80 |
| DEFAULT_STOP_LOSS_PCT | 0.07 |
| DEFAULT_TAKE_PROFIT_PCT | 0.20 |
| MAX_DAILY_LOSS_PCT | 0.02 |
| MAX_DAILY_TRADES | 20 |
| MAX_DRAWDOWN_LIMIT | 0.15 |
| MARKET_CIRCUIT_BREAKER_PCT | 5.0 |

---

## 10. 四维权重

默认：技术面30% / 消息面25% / 资金面25% / 基本面20%

手动调整：编辑 `config/dimension_weights.json`（四项之和须为1.0）

自动优化：`python main.py optimize`

---

## 11. 自我进化机制

```
每轮结束 → ReflectionAgent
  ├── LLM 复盘 → 提取规则 → 写入 SQLite（经合规过滤）
  └── 判断是否触发策略大调整

触发阈值 → StrategyOptimizer
  ├── 读取近30条记录 → LLM 分析胜率/盈亏
  └── 写入新四维权重到 config/dimension_weights.json
```

查看已学规则：
```bash
python -c "from core.memory.long_term import LongTermMemory; [print(r) for r in LongTermMemory().get_rules(min_confidence=0.5)]"
```

重置记忆：
```bash
del storage\database\memory.db
rd /s /q storage\vector_store
```

---

## 12. 合规边界检查

`compliance/rule_boundary.py` 在写入规则和更新权重前自动过滤违规内容。

拦截类型：市场操纵（拉抬/打压/坐庄）、虚假申报（幌骗/快速挂撤）、内幕交易、价格操纵。

```bash
# 查看被拒绝的规则
Get-Content logs\trading.log | Select-String "合规红线"
```

---

## 13. 数据源

| 数据 | 来源 | 备注 |
|---|---|---|
| 实时/历史行情 | pytdx（免费）| 自动选最低延迟服务器 |
| 财经新闻/公告 | akshare | 需网络畅通 |
| 北向/融资融券 | akshare | 收盘后更新 |
| 实盘下单 | 迅投 QMT | 需券商开通 |

pytdx 全部失败时自动降级为模拟数据，不影响功能测试。

---

## 14. 常见问题

**pytdx 连接失败**
```bash
Test-NetConnection -ComputerName 119.147.212.81 -Port 7709
# 检查防火墙是否拦截 7709 端口
```

**通义千问 API 报错（AuthenticationError）**
- 检查 `.env` 中 `DASHSCOPE_API_KEY` 是否以 `sk-` 开头
- 登录 https://dashscope.aliyun.com 确认 Key 有效且有余额

**ChromaDB 初始化失败**
```bash
rd /s /q storage\vector_store
python main.py
```

**UI 无法访问（5688端口）**
```bash
netstat -ano | findstr 5688
python ui/app.py  # 前台验证启动
```

**Vite 启动失败（语法错误）**
- 确认 Node 版本 ≥ 18：`node --version`
- Windows nvm 切换：`nvm use 18.16.1`

**pydantic-settings 报错**
```bash
pip install pydantic-settings>=2.7.0
```

**circular import（signal 模块）**
- 项目已将 `signal/` 重命名为 `signal_filter/`，如遇此问题请检查导入路径

---

## 15. 接入真实 AgentState

当前 UI 使用模拟数据，三种接入方案：

**方案一：文件共享（最简单）**
```python
# monitoring/dashboard.py 中添加
import json
def export_state(state, path="storage/ui_state.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, default=str)
```

**方案二：共享内存（同进程）**
```python
# ui/app.py 顶部
_real_state: dict = {}
def update_ui_state(state):
    global _real_state
    with _lock:
        _real_state = dict(state)
```

**方案三：Redis（推荐生产）**
```python
import redis, json
r = redis.from_url("redis://localhost:6379/0")
# 交易系统推送
r.set("moremoney:state", json.dumps(state, default=str))
# ui/app.py 读取
def _load_state():
    raw = r.get("moremoney:state")
    return json.loads(raw) if raw else _state
```

---

## 16. 注意事项

### 投资风险声明

本项目仅供学习研究，不构成投资建议。实盘前请在模拟盘充分验证，自行承担交易风险。

### API Key 安全

- `.env` 已加入 `.gitignore`，禁止提交代码仓库
- 定期轮换 DashScope API Key
- 不在日志中打印 Key

### 实盘前检查清单

- [ ] 模拟盘运行 ≥ 2 周，胜率稳定 > 55%
- [ ] 风控参数已按自身风险承受能力调整
- [ ] QMT 客户端已登录且资金充足
- [ ] 已设置 `MAX_DAILY_LOSS_PCT` 日内止损
- [ ] 了解熔断触发条件和恢复方式

### 资源消耗

- 每轮约消耗 4-8 次 LLM 调用
- 建议在 DashScope 控制台设置用量告警
- `ANALYSIS_INTERVAL_MINUTES=30` 可降低约50% API消耗

### A股交易时间

周一至周五 09:30-11:30、13:00-15:00。非交易时间系统仍运行分析，但不下单。

### 数据备份

```bash
copy storage\database\memory.db storage\database\memory_backup.db
```

---

*文档维护：修改系统配置或添加新功能后，请同步更新对应章节。*
