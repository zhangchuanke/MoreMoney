"""
Agent全局状态定义 - LangGraph State Schema
所有Agent节点共享的状态结构
"""
from typing import TypedDict, Annotated, List, Dict, Optional, Any
from datetime import datetime
import operator


class MarketSignal(TypedDict):
    """单个分析维度的信号"""
    symbol: str             # 股票代码
    dimension: str          # technical / sentiment / capital / fundamental
    direction: str          # bullish / bearish / neutral
    strength: float         # 0.0 ~ 1.0
    confidence: float       # 0.0 ~ 1.0
    reasoning: str          # LLM推理过程
    indicators: Dict        # 具体指标数值
    timestamp: str


class TradeDecision(TypedDict):
    """交易决策"""
    action: str             # buy / sell / hold / add / reduce
    symbol: str             # 股票代码
    target_position: float  # 目标仓位占比 0~1
    current_position: float # 当前仓位占比
    price_limit: Optional[float]  # 限价，None则市价
    quantity: Optional[int]       # 数量，None则自动计算
    stop_loss: float        # 止损价
    take_profit: float      # 止盈价
    urgency: str            # immediate / normal / passive
    reasoning: str          # 决策理由
    risk_score: float       # 风险评分 0~1


class PortfolioStatus(TypedDict):
    """组合状态"""
    total_assets: float
    cash: float
    positions: Dict[str, Dict]   # symbol -> {qty, cost, current_price, pnl}
    daily_pnl: float
    total_pnl: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float


class AgentMemory(TypedDict):
    """Agent记忆结构"""
    recent_decisions: List[Dict]       # 近期决策记录
    successful_patterns: List[str]     # 成功模式
    failed_patterns: List[str]         # 失败模式
    market_regime: str                 # trending / ranging / volatile / crisis
    learned_rules: List[str]           # 自我学习总结的规则
    last_reflection: str               # 上次反思时间


class AgentState(TypedDict):
    """
    LangGraph主状态 - 所有节点读写的统一状态
    使用 Annotated[list, operator.add] 支持并行节点追加
    """
    # === 基础信息 ===
    session_id: str
    timestamp: str
    market_date: str
    trading_phase: str          # pre_market / morning / midday / afternoon / post_market

    # === 分析目标 ===
    target_symbols: List[str]   # 当前分析的股票列表
    universe: List[str]         # 全量股票池

    # === 并行分析结果（使用add合并各Agent输出）===
    signals: Annotated[List[MarketSignal], operator.add]
    analysis_reports: Annotated[List[Dict], operator.add]
    news_summaries: Annotated[List[Dict], operator.add]

    # === 综合决策 ===
    decisions: List[TradeDecision]
    pending_orders: List[Dict]
    executed_orders: Annotated[List[Dict], operator.add]
    rejected_orders: Annotated[List[Dict], operator.add]

    # === 市场环境 ===
    market_overview: Dict       # 大盘状态
    sector_rotation: Dict       # 板块轮动
    risk_level: str             # low / medium / high / extreme
    market_sentiment: str       # fear / neutral / greed

    # === 组合状态 ===
    portfolio: PortfolioStatus

    # === 风控状态 ===
    risk_flags: Annotated[List[str], operator.add]   # 风险预警
    circuit_breaker_triggered: bool
    daily_loss_limit_reached: bool

    # === 记忆与学习 ===
    memory: AgentMemory
    reflection_needed: bool
    strategy_update_needed: bool

    # === 系统消息 ===
    messages: Annotated[List[Dict], operator.add]    # Agent间通信
    errors: Annotated[List[str], operator.add]
    logs: Annotated[List[str], operator.add]

    # === 迭代控制 ===
    iteration_count: int
    max_iterations: int
    should_terminate: bool
