"""
Agent 全局状态定义 - LangGraph State Schema
所有 Agent 节点共享的状态结构
"""
from typing import TypedDict, Annotated, List, Dict, Optional, Any
from datetime import datetime
import operator


class MarketSignal(TypedDict):
    """单个分析维度的信号"""
    symbol: str
    dimension: str          # technical / sentiment / capital_flow / fundamental
    direction: str          # bullish / bearish / neutral
    strength: float         # 0.0 ~ 1.0
    confidence: float       # 0.0 ~ 1.0
    reasoning: str
    indicators: Dict
    timestamp: str


class TradeDecision(TypedDict):
    """交易决策"""
    action: str             # buy / sell / hold / add / reduce
    symbol: str
    target_position: float
    current_position: float
    price_limit: Optional[float]
    quantity: Optional[int]
    stop_loss: float
    take_profit: float
    urgency: str            # immediate / normal / passive
    reasoning: str
    risk_score: float


class PortfolioStatus(TypedDict):
    """组合状态"""
    total_assets: float
    cash: float
    positions: Dict[str, Dict]
    daily_pnl: float
    total_pnl: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float


class AgentMemory(TypedDict):
    """Agent 记忆结构"""
    recent_decisions: List[Dict]
    successful_patterns: List[str]
    failed_patterns: List[str]
    market_regime: str
    learned_rules: List[str]
    last_reflection: str


class MarketRegimeDetail(TypedDict):
    """
    市场风格识别详情（由 MarketRegimeDetector 产出，写入 state）。
    供 AdaptiveSignalAggregator、OrchestratorAgent.make_decision 直接读取。
    """
    regime: str          # bull / bear / volatile / theme / value
    confidence: float    # 识别置信度 0~1
    veto_active: bool    # 是否触发极端行情一票否决
    description: str     # 人可读的风格描述
    base_weights: Dict   # 对应的四维基准权重
    signals: Dict        # 识别依据的原始指标快照


class WeightBounds(TypedDict):
    """权重边界配置（供审计 / UI 展示）"""
    lower: float
    upper: float
    dimensions: List[str]


class AgentState(TypedDict):
    """
    LangGraph 主状态 —— 所有节点读写的统一状态。
    使用 Annotated[list, operator.add] 支持并行节点追加。
    """
    # === 基础信息 ===
    session_id: str
    timestamp: str
    market_date: str
    trading_phase: str          # pre_market / morning / midday / afternoon / post_market

    # === 分析目标 ===
    target_symbols: List[str]
    universe: List[str]

    # === 并行分析结果（operator.add 合并各 Agent 输出）===
    signals: Annotated[List[MarketSignal], operator.add]
    analysis_reports: Annotated[List[Dict], operator.add]
    news_summaries: Annotated[List[Dict], operator.add]

    # === 综合决策 ===
    decisions: List[TradeDecision]
    pending_orders: List[Dict]
    executed_orders: Annotated[List[Dict], operator.add]
    rejected_orders: Annotated[List[Dict], operator.add]

    # === 市场环境 ===
    market_overview: Dict
    sector_rotation: Dict
    risk_level: str             # low / medium / high / extreme
    market_sentiment: str       # fear / neutral / greed

    # === 市场风格 ===
    market_regime: str                        # bull / bear / volatile / theme / value
    market_regime_detail: MarketRegimeDetail  # 完整风格识别结果
    weight_bounds: WeightBounds               # 当前权重边界（供审计使用）

    # === 组合状态 ===
    portfolio: PortfolioStatus

    # === 风控状态 ===
    risk_flags: Annotated[List[str], operator.add]
    circuit_breaker_triggered: bool
    daily_loss_limit_reached: bool

    # === 记忆与学习 ===
    memory: AgentMemory
    reflection_needed: bool
    strategy_update_needed: bool

    # === 系统消息 ===
    messages: Annotated[List[Dict], operator.add]
    errors: Annotated[List[str], operator.add]
    logs: Annotated[List[str], operator.add]

    # === 数据质量校验（data_quality 节点写入）===
    data_quality_reports: List[Dict]
    degraded_symbols: List[str]

    # === 新闻过滤（news_filter 节点写入）===
    filtered_news: Dict

    # === 技能引擎（skills 节点写入）===
    skill_results: List[Dict]    # 各 Skill 执行结果摘要
    merged_weight_adj: Dict      # 合并后的四维权重调整量
    merged_signal_adj: Dict      # 合并后的标的信号调整量
    skill_veto_active: bool      # 技能引擎是否触发一票否决
    skill_veto_reason: str       # 一票否决原因

    # === 滑点适配（slippage 节点写入）===
    slippage_report: List[Dict]

    # === 迭代控制 ===
    iteration_count: int
    max_iterations: int
    should_terminate: bool
