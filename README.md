# MoreMoney - A股 AI 自动化交易 Agent

基于 **LangGraph 1.1 + 通义千问（Qwen-Max）** 构建的 A 股全自动交易系统。
从技术面、消息面、资金面、基本面四个维度并行分析，自主决策买卖，持续自我迭代进化。

---

## 核心特性

- **多 Agent 并行**：四维分析节点并行执行，LangGraph 自动合并结果
- **自适应信号聚合**：基于市场风格动态切换四维权重矩阵，投票制聚合，支持一票否决
- **技能插件系统**：5 个内置 Skill，可动态启用/禁用，支持权重/信号/一票否决
- **三层记忆系统**：短期（当日 deque）+ 长期（SQLite）+ 事件（ChromaDB 向量检索）
- **严格风控**：熔断 / 日内止损 / 动态止损 / 仓位集中度 / 合规边界 / Kill Switch
- **自我迭代**：LLM 驱动四维权重优化，回测前置关卡验证
- **模拟/实盘双模式**：paper 模式开箱即用，live 模式对接迅投 QMT
- **免费数据源**：pytdx 通达信协议，无需账号
- **Vue 3 监控面板**：13 个功能面板，SSE 实时推送

---

## 技术栈

| 模块 | 版本 | 用途 |
|------|------|------|
| langgraph | 1.1.3 | 多 Agent 图编排 |
| langchain | 1.2.13 | LLM 工具链 |
| openai | 2.30.0 | 通义千问 API |
| pytdx | 1.72 | 同花顺通达信免费数据 |
| akshare | >=1.14 | 新闻/公告/北向资金 |
| chromadb | 1.0.4 | 向量数据库 |
| pydantic | 2.12.5 | 数据校验 |
| flask | >=3.0 | UI API 后端 |
| vue | 3.4 | 前端框架 |
| vite | 5.0 | 前端构建（需 Node 18+）|

---

## 快速开始

```bash
pip install -r requirements.txt
pip install -r ui/requirements_ui.txt
cp .env.example .env   # 填入 DASHSCOPE_API_KEY
python main.py         # 启动交易系统（模拟盘）
python ui/app.py       # 启动 Flask API（另开终端）
cd frontend && npm install && npm run dev  # Vue 前端（:5173）
python main.py optimize  # 手动触发策略优化
```

---

## 系统工作流程

### 主交易图（每轮循环）

```
START
  |
  v
[scanner] 市场扫描
  · 获取大盘指数行情，热股扫描 top20
  · 识别市场风格 → market_regime_detail
  · 五类风格: bull / bear / volatile / theme / value
  · 极端行情(大盘+-3.5% 或 VIX>=40) 触发 veto_active=True
  |
  v
[market_regime] 风格识别（透传或兜底补充）
  |
  v
[liquidity_filter] 流动性过滤
  · 剔除日均成交额 < 5000万 / 流通市值 < 5亿 的标的
  |
  v
[data_quality] 双源数据校验
  · pytdx <-> akshare 交叉比对
  · GOOD=正常  DEGRADED=仓位x0.5  SUSPENDED=移出
  · 全部暂停时触发 circuit_breaker=True
  |
  v
[news_filter] 新闻降噪
  · 证监会白名单过滤（可信度>=0.5）
  · ChromaDB 向量去重（相似度>0.85 = 旧闻）
  |
  +----------+----------+----------+----------+
  v          v          v          v
[technical][sentiment][capital_flow][fundamental]  并行
  +----------+----------+----------+----------+
             |
             v
[skills] 技能引擎
  · TrendFollower   趋势跟随（强趋势标的加权）
  · RiskInterceptor 风险拦截（异常波动降权）
  · SignalBooster   信号增强（多维共振放大）
  · SentimentFilter 情绪过滤（噪音情绪降权）
  · EarningsAdapter 财报季适配（基本面权重上调）
  · 输出: 权重调整 / 信号调整 / 一票否决
  |
  v
[aggregator] 自适应信号聚合
  · 极端行情一票否决 → 全部 hold
  · 市场风格 + Skill 调整量 → 权重矩阵
  · 各维度投票（strength x confidence）
  · top5 标的 → LLM 二次审核
  |
  v
[risk] 风控（规则驱动，不走 LLM）
  · KillSwitch / 日内止损 / 回撤熔断 / 大盘熔断
  · 单股/板块集中度 / 移动止损 / 流动性复检
  · 个股振幅熔断 / 动态仓位 / 对手盘监控
  |
  +-- 熔断或日损 --> [reflection]
  +-- extreme    --> END
  +-- 正常       --> [decision]
                        |
                        v
                   [decision] LLM 生成决策
                        |
              +-- 全部hold --> [reflection]
              |   有操作
              v
         [slippage] 滑点估算
              |
              v
         [execution] 下单（模拟/实盘）
              |
              v
         [reflection] 反思
  · 绩效评估 / 交易写入长期记忆 / 风险事件记录
  · LLM 反思 → 提取规则 → 合规过滤 → learned_rules
  · 判断是否需要策略大调整
  |
  +-- should_terminate=True --> END
  +-- 继续                  --> [scanner] 下一轮
```

### 自我进化流程（python main.py optimize）

```
1. 收集 >=200 条历史交易（覆盖多种市场风格周期）
2. 统计绩效（总胜率、盈亏比、按市场风格分层统计）
3. LLM 提出新四维权重建议
4. RuleBoundaryChecker 合规检查（过滤市场操纵意图）
5. 权重边界裁剪归一化（每维强制在 10%~50% 之间）
6. BacktestGate 回测验证（新权重 vs 基准权重）
   +-- 通过   --> KnowledgeUpdater 写入配置，立即生效
   +-- 不通过 --> 拒绝写入，记录失败原因
7. LongTermMemory 持久化策略版本（含参数 + 绩效快照）
```

---

## 目录结构

```
MoreMoney/
├── main.py
├── requirements.txt
├── agents/                      # 8 个 Agent
│   ├── orchestrator.py          # 编排（扫描/聚合/决策）
│   ├── technical_agent.py
│   ├── sentiment_agent.py
│   ├── capital_flow_agent.py
│   ├── fundamental_agent.py
│   ├── risk_agent.py
│   ├── execution_agent.py
│   └── reflection_agent.py
├── core/
│   ├── graph/trading_graph.py   # LangGraph 图（16 个节点）
│   ├── state/agent_state.py     # 全局状态 Schema
│   ├── market_regime.py         # 市场风格识别（5类）
│   ├── signal_aggregator.py     # 自适应信号聚合器
│   └── memory/                  # 短期/长期/事件记忆
├── skills/                      # 技能插件系统
│   ├── base.py / registry.py / engine.py
│   └── builtin/                 # 5 个内置 Skill
├── tools/                       # 行情/新闻/资金/财务/技术/券商
├── llm/                         # 通义千问客户端 + Prompt
├── signal_filter/               # 新闻降噪与信号过滤
├── data_quality/                # 双源数据校验
├── compliance/                  # 合规硬约束
├── config/                      # 全局配置与风控参数
├── monitoring/                  # 看板/告警/日志/KillSwitch/管控台
├── self_evolution/              # 绩效评估/策略优化/知识更新/回测关卡
├── risk/                        # 动态仓位/流动性/个股熔断/对手盘
├── execution/                   # 滑点预估
├── storage/                     # 运行时数据（自动生成）
├── ui/                          # Flask API 后端（端口 5688）
│   └── app.py
└── frontend/                    # Vue 3 独立前端（端口 5173）
    └── src/components/Panel*.vue
```

---

## 前端面板

| 面板 | 内容 |
|------|------|
| 总览 | KPI 卡片、四维权重、风险预警 |
| 行情 | 四大指数、板块涨跌排行 |
| 市场机制 | 风格判断、置信度、权重矩阵 |
| 信号矩阵 | 多空信号列表、强度条 |
| 决策引擎 | 操作/仓位/止损止盈/风险分 |
| 资金流向 | 北向资金、主力资金、板块资金流 |
| 持仓管理 | 持仓卡片（含止损/止盈/盈亏）|
| 成交记录 | 完整订单表含滑点 |
| 每日优选 | 评分卡片 + 手动添加 Modal |
| Agent 状态 | 8 个 Agent 运行状态 |
| 风控参数 | 动态仓位仪表 + 参数列表 |
| 控制面板 | Kill Switch 4 按钮 + 操作历史 |
| 系统日志 | 实时日志 + 级别过滤 |

右侧边栏：信号流 / 持仓盈亏 / Agent 状态 / 风险预警，每 3 秒 SSE 自动更新。

---

## 监控体系

| 组件 | 端口 | 功能 |
|------|------|------|
| Dashboard | 控制台 | 每轮打印组合状态（资产/盈亏/持仓/预警）|
| TradeLogger | 文件/控制台 | 结构化日志，INFO/WARN/ERROR 分级 |
| KillSwitch | 进程内 | 线程安全全局开关（NORMAL/PAUSED/EMERGENCY/HALTED）|
| AlertSystem | 控制台 | 分级告警（可扩展企业微信/钉钉）|
| control_panel | 8765 | Flask 应急管控面板，一键暂停/清仓/停止 |
| ui/app.py | 5688 | 完整监控 Flask API + SSE 实时推送 |
| frontend/ | 5173 | Vue 3 SPA，对接 5688 API |

---

## 风控规则

| 规则 | 默认值 |
|------|--------|
| 单股最大仓位 | 20% |
| 单板块最大仓位 | 40% |
| 日内最大亏损 | 2% |
| 最大回撤熔断 | 15% |
| 大盘涨跌熔断 | ±5% |
| 默认止损 | -7% |
| 默认止盈 | +20% |
| 流动性下限 | 日均成交额 5000 万 |
| 个股振幅熔断 | 单日振幅 > 15% |
| 北向防御触发 | 连续 3 日净流出 |

所有参数均在 `config/risk_params.py` 中调整，重启后生效。

---

## 数据源

| 数据类型 | 来源 |
|---------|------|
| 实时/历史行情 | pytdx（免费，无需账号）|
| 财经新闻/公告 | akshare |
| 北向/融资融券 | akshare |
| 实盘下单 | 迅投 QMT |

pytdx 自动选最低延迟服务器，全部失败时降级为模拟数据，系统不崩溃。

---

## 运行模式

| 模式 | 配置 | 说明 |
|------|------|------|
| 模拟盘（默认）| TRADING_MODE=paper | 内存模拟，即开即用 |
| 实盘 | TRADING_MODE=live | 对接迅投 QMT |

---

> **投资有风险，本项目仅供学习研究，不构成投资建议。**
> 实盘前请在模拟盘充分验证，自行承担交易风险。
