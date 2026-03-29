"""
MoreMoney - A股 AI 自动化交易 Agent
主入口文件
"""
import asyncio
import signal
import sys, io
# Force UTF-8 output on Windows to avoid GBK encode errors
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from datetime import datetime

from core.graph.trading_graph import compile_graph
from core.state.agent_state import AgentState, AgentMemory, PortfolioStatus
from core.memory.long_term import LongTermMemory
from monitoring.dashboard import Dashboard
from monitoring.trade_logger import TradeLogger
from self_evolution.strategy_optimizer import StrategyOptimizer
from config.settings import settings


def build_initial_state() -> AgentState:
    """构建初始状态"""
    long_term = LongTermMemory()
    learned_rules = [r["rule"] for r in long_term.get_rules(min_confidence=0.5)]

    portfolio: PortfolioStatus = {
        "total_assets": settings.INITIAL_CAPITAL,
        "cash": settings.INITIAL_CAPITAL,
        "positions": {},
        "daily_pnl": 0.0,
        "total_pnl": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "sharpe_ratio": 0.0,
    }

    memory: AgentMemory = {
        "recent_decisions": [],
        "successful_patterns": [],
        "failed_patterns": [],
        "market_regime": "unknown",
        "learned_rules": learned_rules,
        "last_reflection": "",
    }

    return AgentState(
        session_id=f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now().isoformat(),
        market_date=datetime.now().strftime("%Y-%m-%d"),
        trading_phase="morning",
        target_symbols=[],
        universe=[],
        signals=[],
        analysis_reports=[],
        news_summaries=[],
        decisions=[],
        pending_orders=[],
        executed_orders=[],
        rejected_orders=[],
        market_overview={},
        sector_rotation={},
        risk_level="medium",
        market_sentiment="neutral",
        portfolio=portfolio,
        risk_flags=[],
        circuit_breaker_triggered=False,
        daily_loss_limit_reached=False,
        memory=memory,
        reflection_needed=False,
        strategy_update_needed=False,
        messages=[],
        errors=[],
        logs=[],
        iteration_count=0,
        max_iterations=settings.MAX_ITERATIONS_PER_DAY,
        should_terminate=False,
    )


async def run_trading_session():
    """运行一个完整的交易会话"""
    logger = TradeLogger()
    dashboard = Dashboard()

    logger.log_info("=" * 50)
    logger.log_info(
        f"MoreMoney 启动 | 模式: {settings.TRADING_MODE} "
        f"| 资金: ¥{settings.INITIAL_CAPITAL:,.0f}"
    )
    logger.log_info("=" * 50)

    graph = compile_graph()
    config = {
        "configurable": {
            "thread_id": f"trade_{datetime.now().strftime('%Y%m%d')}"
        }
    }
    state = build_initial_state()

    # 优雅退出
    _stop = False
    def _handle_signal(sig, frame):
        nonlocal _stop
        print("\n[Main] 收到退出信号，等待本轮完成后停止...")
        _stop = True
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        async for event in graph.astream(state, config=config, stream_mode="values"):
            if isinstance(event, dict):
                logger.log_state(event)
                dashboard.display(event)
                if event.get("executed_orders"):
                    logger.log_orders(event["executed_orders"])
                if event.get("should_terminate") or _stop:
                    break
    except Exception as e:
        logger.log_error(f"运行异常: {e}")
        raise
    finally:
        logger.log_info("交易会话结束")


async def run_strategy_optimization():
    """手动触发策略优化（可单独运行）"""
    optimizer = StrategyOptimizer()
    result = await optimizer.optimize()
    print(f"优化结果: {result}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "optimize":
        asyncio.run(run_strategy_optimization())
    else:
        asyncio.run(run_trading_session())
