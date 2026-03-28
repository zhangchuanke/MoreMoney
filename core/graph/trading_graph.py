"""
LangGraph 1.1.x 主交易图

变更点（相比旧版）:
  - langgraph.graph.START / END 仍在 langgraph.graph
  - MemorySaver 在 langgraph.checkpoint.memory
  - builder.compile() 支持 interrupt_before / interrupt_after
  - astream() stream_mode="values" | "updates" | "debug"
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

# ============================================================
# Agent 单例
# ============================================================
_orchestrator      = OrchestratorAgent()
_technical_agent   = TechnicalAgent()
_sentiment_agent   = SentimentAgent()
_capital_agent     = CapitalFlowAgent()
_fundamental_agent = FundamentalAgent()
_risk_agent        = RiskAgent()
_execution_agent   = ExecutionAgent()
_reflection_agent  = ReflectionAgent()


# ============================================================
# 节点函数（保持 async，LangGraph 1.1 完整支持异步节点）
# ============================================================
async def market_scanner_node(state: AgentState) -> AgentState:
    return await _orchestrator.scan_market(state)

async def technical_analysis_node(state: AgentState) -> AgentState:
    return await _technical_agent.analyze(state)

async def sentiment_analysis_node(state: AgentState) -> AgentState:
    return await _sentiment_agent.analyze(state)

async def capital_flow_analysis_node(state: AgentState) -> AgentState:
    return await _capital_agent.analyze(state)

async def fundamental_analysis_node(state: AgentState) -> AgentState:
    return await _fundamental_agent.analyze(state)

async def signal_aggregator_node(state: AgentState) -> AgentState:
    return await _orchestrator.aggregate_signals(state)

async def risk_assessment_node(state: AgentState) -> AgentState:
    return await _risk_agent.assess(state)

async def decision_node(state: AgentState) -> AgentState:
    return await _orchestrator.make_decision(state)

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
) -> Literal["execution", "reflection"]:
    decisions = state.get("decisions", [])
    if not decisions or all(d.get("action") == "hold" for d in decisions):
        return "reflection"
    return "execution"


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

    # 注册节点
    builder.add_node("scanner",      market_scanner_node)
    builder.add_node("technical",    technical_analysis_node)
    builder.add_node("sentiment",    sentiment_analysis_node)
    builder.add_node("capital_flow", capital_flow_analysis_node)
    builder.add_node("fundamental",  fundamental_analysis_node)
    builder.add_node("aggregator",   signal_aggregator_node)
    builder.add_node("risk",         risk_assessment_node)
    builder.add_node("decision",     decision_node)
    builder.add_node("execution",    execution_node)
    builder.add_node("reflection",   reflection_node)

    # 入口边
    builder.add_edge(START, "scanner")

    # 扫描 -> 四维并行
    for node in ("technical", "sentiment", "capital_flow", "fundamental"):
        builder.add_edge("scanner", node)

    # 四维 -> 聚合
    for node in ("technical", "sentiment", "capital_flow", "fundamental"):
        builder.add_edge(node, "aggregator")

    # 聚合 -> 风控
    builder.add_edge("aggregator", "risk")

    # 风控 -> 条件路由（LangGraph 1.1: END 字面量用 "__end__"）
    builder.add_conditional_edges(
        "risk",
        route_after_risk,
        {"decision": "decision", "reflection": "reflection", "__end__": END},
    )

    # 决策 -> 条件路由
    builder.add_conditional_edges(
        "decision",
        route_after_decision,
        {"execution": "execution", "reflection": "reflection"},
    )

    # 执行 -> 反思
    builder.add_edge("execution", "reflection")

    # 反思 -> 条件路由（循环或终止）
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
