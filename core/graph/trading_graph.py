"""
LangGraph 1.1.x 主交易图

流水线：
  START
  → scanner          (市场扫描 + 标的筛选)
  → market_regime    (市场风格识别)
  → liquidity_filter (前置流动性过滤)
  → data_quality     (双源数据校验)
  → news_filter      (新闻降噪)
  → [technical, sentiment, capital_flow, fundamental]  (四维并行分析)
  → skills           (技能引擎：权重/信号调整 + 一票否决)
  → aggregator       (自适应信号聚合，投票制)
  → risk             (风险评估)
  → decision / reflection / END  (条件路由)
  → slippage → execution → reflection → scanner / END
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from core.state.agent_state import AgentState
from agents.orchestrator import OrchestratorAgent
from agents.technical_agent import TechnicalAgent
from agents.sentiment_agent import SentimentAgent
from agents.capital_flow_agent import CapitalFlowAgent
from agents.fundamental_agent import FundamentalAgent
from agents.risk_agent import RiskAgent
from agents.execution_agent import ExecutionAgent
from agents.reflection_agent import ReflectionAgent
from data_quality.data_quality_node import data_quality_node
from signal_filter.news_filter_node import news_filter_node
from execution.slippage import slippage_adapter_node
from core.market_regime import MarketRegimeDetector
from risk.liquidity_filter import liquidity_filter_node
from skills.engine import SkillEngine

# ============================================================
# Agent / Engine 单例
# ============================================================
_orchestrator      = OrchestratorAgent()
_technical_agent   = TechnicalAgent()
_sentiment_agent   = SentimentAgent()
_capital_agent     = CapitalFlowAgent()
_fundamental_agent = FundamentalAgent()
_risk_agent        = RiskAgent()
_execution_agent   = ExecutionAgent()
_reflection_agent  = ReflectionAgent()
_regime_detector   = MarketRegimeDetector()
_skill_engine      = SkillEngine.instance()


# ============================================================
# 节点函数
# ============================================================
async def market_scanner_node(state: AgentState) -> AgentState:
    return await _orchestrator.scan_market(state)


async def market_regime_node(state: AgentState) -> AgentState:
    """
    市场风格识别节点。
    scan_market() 已内置风格识别；此节点透传或兜底补充识别。
    """
    if state.get("market_regime_detail"):
        detail = state["market_regime_detail"]
        return {
            **state,
            "logs": [
                f"[MarketRegime] 风格已由 scanner 识别: {detail.get('regime')} "
                f"(置信度={detail.get('confidence', 0):.2f})"
            ],
        }
    market_overview = state.get("market_overview", {})
    regime = _regime_detector.detect(market_overview)
    return {
        **state,
        "market_regime": regime.regime,
        "market_regime_detail": {
            "regime":       regime.regime,
            "confidence":   regime.confidence,
            "veto_active":  regime.veto_active,
            "description":  regime.description,
            "base_weights": regime.base_weights,
            "signals":      regime.signals,
        },
        "logs": [
            f"[MarketRegime] 识别结果: {regime.regime} "
            f"(置信度={regime.confidence:.2f}) | {regime.description}"
        ],
    }


async def liquidity_pre_filter_node(state: AgentState) -> AgentState:
    """前置流动性过滤：剔除日均成交额不达标的标的，防止小盘股无法止损"""
    return await liquidity_filter_node(state)


async def data_quality_check_node(state: AgentState) -> AgentState:
    """数据质量双源校验：移除不可信标的，写入降级列表"""
    return await data_quality_node(state)


async def news_filter_check_node(state: AgentState) -> AgentState:
    """新闻降噪 + 可信度分级：过滤社交媒体噪音，仅留官方信披"""
    return await news_filter_node(state)


async def technical_analysis_node(state: AgentState) -> AgentState:
    return await _technical_agent.analyze(state)


async def sentiment_analysis_node(state: AgentState) -> AgentState:
    return await _sentiment_agent.analyze(state)


async def capital_flow_analysis_node(state: AgentState) -> AgentState:
    return await _capital_agent.analyze(state)


async def fundamental_analysis_node(state: AgentState) -> AgentState:
    return await _fundamental_agent.analyze(state)


async def skill_node(state: AgentState) -> AgentState:
    """
    技能引擎节点：在四维分析汇聚后、信号聚合前运行所有已启用 Skill。
    输出权重调整、信号调整、一票否决，注入 state 供 aggregator 消费。
    """
    skill_output = _skill_engine.run_all(state)
    triggered_count = sum(
        1 for r in skill_output.get("skill_results", []) if r.get("triggered")
    )
    log = f"[SkillEngine] 执行完成，触发技能数={triggered_count}"
    if skill_output.get("veto_active"):
        log += f"，一票否决: {skill_output['veto_reason']}"
    return {
        **state,
        "skill_results":     skill_output.get("skill_results", []),
        "merged_weight_adj": skill_output.get("merged_weight_adj", {}),
        "merged_signal_adj": skill_output.get("merged_signal_adj", {}),
        "skill_veto_active": skill_output.get("veto_active", False),
        "skill_veto_reason": skill_output.get("veto_reason", ""),
        "logs": [log],
    }


async def signal_aggregator_node(state: AgentState) -> AgentState:
    """自适应混合信号聚合（投票制 + 市场风格权重 + 一票否决）"""
    return await _orchestrator.aggregate_signals(state)


async def risk_assessment_node(state: AgentState) -> AgentState:
    return await _risk_agent.assess(state)


async def decision_node(state: AgentState) -> AgentState:
    return await _orchestrator.make_decision(state)


async def slippage_adapt_node(state: AgentState) -> AgentState:
    """滑点预估适配：注入固定滑点，调整目标价格 / 数量"""
    return await slippage_adapter_node(state)


async def execution_node(state: AgentState) -> AgentState:
    return await _execution_agent.execute(state)


async def reflection_node(state: AgentState) -> AgentState:
    return await _reflection_agent.reflect(state)


# ============================================================
# 条件路由
# ============================================================
def route_after_risk(
    state: AgentState,
) -> Literal["decision", "reflection", "__end__"]:
    if state.get("circuit_breaker_triggered") or state.get("daily_loss_limit_reached"):
        return "reflection"
    if state.get("risk_level") == "extreme":
        return "__end__"
    return "decision"


def route_after_decision(
    state: AgentState,
) -> Literal["slippage", "reflection"]:
    decisions = state.get("decisions", [])
    if not decisions or all(d.get("action") == "hold" for d in decisions):
        return "reflection"
    return "slippage"


def route_after_reflection(
    state: AgentState,
) -> Literal["scanner", "__end__"]:
    if state.get("should_terminate"):
        return "__end__"
    if state.get("iteration_count", 0) >= state.get("max_iterations", 10):
        return "__end__"
    return "scanner"


# ============================================================
# 构建图
# ============================================================
def build_trading_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # ── 注册节点 ──────────────────────────────────────────────────────
    builder.add_node("scanner",          market_scanner_node)
    builder.add_node("market_regime",    market_regime_node)
    builder.add_node("liquidity_filter", liquidity_pre_filter_node)
    builder.add_node("data_quality",     data_quality_check_node)
    builder.add_node("news_filter",      news_filter_check_node)
    builder.add_node("technical",        technical_analysis_node)
    builder.add_node("sentiment",        sentiment_analysis_node)
    builder.add_node("capital_flow",     capital_flow_analysis_node)
    builder.add_node("fundamental",      fundamental_analysis_node)
    builder.add_node("skills",           skill_node)
    builder.add_node("aggregator",       signal_aggregator_node)
    builder.add_node("risk",             risk_assessment_node)
    builder.add_node("decision",         decision_node)
    builder.add_node("slippage",         slippage_adapt_node)
    builder.add_node("execution",        execution_node)
    builder.add_node("reflection",       reflection_node)

    # ── 边 ────────────────────────────────────────────────────────────
    builder.add_edge(START, "scanner")

    # 扫描 → 风格识别 → 流动性过滤 → 数据质量 → 新闻过滤
    builder.add_edge("scanner",          "market_regime")
    builder.add_edge("market_regime",    "liquidity_filter")
    builder.add_edge("liquidity_filter", "data_quality")
    builder.add_edge("data_quality",     "news_filter")

    # 新闻过滤 → 四维并行分析
    for node in ("technical", "sentiment", "capital_flow", "fundamental"):
        builder.add_edge("news_filter", node)

    # 四维 → 技能引擎（汇聚后执行 Skill）
    for node in ("technical", "sentiment", "capital_flow", "fundamental"):
        builder.add_edge(node, "skills")

    # 技能引擎 → 聚合
    builder.add_edge("skills", "aggregator")

    # 聚合 → 风控
    builder.add_edge("aggregator", "risk")

    # 风控 → 条件路由
    builder.add_conditional_edges(
        "risk",
        route_after_risk,
        {"decision": "decision", "reflection": "reflection", "__end__": END},
    )

    # 决策 → 滑点适配 → 执行
    builder.add_conditional_edges(
        "decision",
        route_after_decision,
        {"slippage": "slippage", "reflection": "reflection"},
    )
    builder.add_edge("slippage", "execution")

    # 执行 → 反思
    builder.add_edge("execution", "reflection")

    # 反思 → 条件路由（循环或终止）
    builder.add_conditional_edges(
        "reflection",
        route_after_reflection,
        {"scanner": "scanner", "__end__": END},
    )

    return builder


def compile_graph(checkpointer=None):
    """
    编译并返回可执行图。
    LangGraph 1.1: compile() 支持 interrupt_before 用于人工审核。
    """
    builder = build_trading_graph()
    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(
        checkpointer=cp,
        # 如需人工审核决策，取消注释:
        # interrupt_before=["execution"],
    )
