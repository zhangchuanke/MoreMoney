# MoreMoney - A股 AI 自动化交易 Agent

基于 **LangGraph 1.1 + 通义千问（Qwen-Max）** 构建的 A 股全自动交易系统。
从技术面、消息面、资金面、基本面四个维度并行分析，自主决策买卖，并持续自我迭代进化。

---

## 架构概览

```
市场扫描
  └─► [并行四维分析]
        ├── 技术面 Agent  (均线/MACD/KDJ/RSI/布林带/K线形态)
        ├── 消息面 Agent  (新闻/公告/社交媒体情绪)
        ├── 资金面 Agent  (北向/主力资金/融资融券/大宗交易)
        └── 基本面 Agent  (财报/估值/行业对比)
              └─► 信号聚合 → 风险评估 → 决策生成 → 执行
                                                    └─► 反思迭代 → 自我进化
```

---

## 核心特性

- **多 Agent 并行**：四维分析节点并行执行，LangGraph 自动合并结果（`operator.add`）
- **三层记忆系统**：短期（当日 deque）+ 长期（SQLite）+ 事件（ChromaDB 语义检索）
- **严格风控**：熔断 / 日内止损 / 动态移动止损 / 仓位集中度控制
- **自我迭代**：每轮结束自动反思，提取规则，LLM 驱动四维权重优化
- **模拟/实盘双模式**：paper 模式开箱即用，live 模式对接迅投 QMT
- **免费数据源**：同花顺通达信协议（pytdx），无需账号，覆盖全A股实时/历史/财务数据

---

## 技术栈

| 模块 | 版本 | 用途 |
|------|------|------|
| `langgraph` | 1.1.3 | 多 Agent 图编排 |
| `langchain` | 1.2.13 | LLM 工具链 |
| `langchain-core` | 1.2.23 | 核心抽象层 |
| `openai` | 2.30.0 | 通义千问 API（兼容接口）|
| `pytdx` | 1.72 | 同花顺通达信免费数据 |
| `akshare` | ≥1.14 | 新闻/公告/北向资金补充 |
| `chromadb` | 1.0.4 | 向量数据库（语义记忆）|
| `pydantic` | 2.12.5 | 数据校验与配置管理 |

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

# 3. 启动（模拟盘）
python main.py

# 4. 手动触发策略优化
python main.py optimize
```

---

## 目录结构

```
MoreMoney/
├── core/
│   ├── graph/          # LangGraph 图定义（trading_graph.py）
│   ├── state/          # 全局状态 Schema（AgentState）
│   └── memory/         # 短期/长期/事件记忆
├── agents/             # 8个 Agent（编排/技术/消息/资金/基本面/风控/执行/反思）
├── tools/
│   ├── market_data/    # 行情数据（pytdx 主源 + akshare 补充）
│   ├── news/           # 新闻/公告/社交情绪（akshare）
│   ├── capital_flow/   # 北向/大宗/融资融券（akshare）
│   ├── fundamental/    # 财务/估值/行业（pytdx + akshare）
│   ├── technical/      # 技术指标/形态识别/回测引擎
│   └── broker/         # 券商接口（模拟盘 / 迅投QMT）
├── llm/                # 通义千问客户端 + Prompt 模板
├── risk/               # 风控参数
├── self_evolution/     # 绩效评估/策略优化/知识更新
├── monitoring/         # 看板/告警/日志
├── config/             # 全局配置（settings.py / risk_params.py）
└── main.py             # 程序入口
```

---

## 数据源说明

| 数据类型 | 主数据源 | 备用/补充 |
|---------|---------|----------|
| 实时行情（全A股）| pytdx（免费）| - |
| 日线/分钟线历史 | pytdx（免费）| - |
| 基本财务指标 | pytdx 扩展接口 | akshare |
| 指数行情 | pytdx（免费）| - |
| 财经新闻/公告 | akshare | - |
| 北向资金 | akshare | - |
| 融资融券/大宗 | akshare | - |
| 板块热力图 | akshare | - |
| 实盘下单 | 迅投 QMT（`xtquant`）| - |

> pytdx 内置6组通达信公开服务器，自动选择延迟最低节点，连接失败自动降级为模拟数据。

---

## 风控规则

| 规则 | 默认值 | 配置文件 |
|-----|-------|----------|
| 单股最大仓位 | 20% | `config/risk_params.py` |
| 单板块最大仓位 | 40% | `config/risk_params.py` |
| 日内最大亏损（停止交易）| 2% | `config/risk_params.py` |
| 最大回撤熔断 | 15% | `config/risk_params.py` |
| 大盘涨跌熔断 | ±5% | `config/risk_params.py` |
| 默认止损 | -7% | `config/risk_params.py` |
| 默认止盈 | +20% | `config/risk_params.py` |
| 动态移动止损 | 盈利10%移至成本；20%移至+5% | `agents/risk_agent.py` |

---

## 自我进化机制

```
每轮交易结束
  └─► ReflectionAgent
        ├── LLM 复盘本轮操作
        ├── 提取新交易规则 → 写入 SQLite
        └── 判断是否触发策略大调整

定期 / 触发阈值
  └─► StrategyOptimizer
        ├── 读取近30条交易记录
        ├── LLM 分析胜率/盈亏分布
        ├── 输出新四维权重
        └── 写入 config/dimension_weights.json（下轮生效）
```

默认四维权重：技术面 30% / 消息面 25% / 资金面 25% / 基本面 20%（可被自动调整）

---

## 运行模式

| 模式 | 配置 | 说明 |
|------|------|------|
| **模拟盘**（默认）| `TRADING_MODE=paper` | 内存模拟成交，即开即用 |
| **实盘** | `TRADING_MODE=live` | 对接迅投 QMT，需安装 `xtquant` |

---

## 注意事项

> **投资有风险，本项目仅供学习研究，不构成投资建议。**  
> 实盘前请在模拟盘充分验证，自行承担交易风险。
