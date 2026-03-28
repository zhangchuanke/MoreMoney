"""
主编排 Agent - 负责市场扫描、信号聚合、最终决策
"""
import json
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.analysis_prompts import SIGNAL_AGGREGATION_PROMPT, DECISION_PROMPT
from core.state.agent_state import AgentState, TradeDecision
from tools.market_data.realtime_feed import RealtimeFeed
from tools.market_data.index_data import IndexDataTool


class OrchestratorAgent:
    """
    主编排 Agent：
    1. scan_market()       - 扫描市场，筛选标的
    2. aggregate_signals() - 汇总四维信号，加权评分
    3. make_decision()     - 最终决策（综合 LLM 推理）
    """

    # 默认四维权重（运行时由 _load_weights() 动态覆盖）
    DIMENSION_WEIGHTS: Dict[str, float] = {
        "technical":    0.30,
        "sentiment":    0.25,
        "capital_flow": 0.25,
        "fundamental":  0.20,
    }

    def __init__(self):
        self.llm        = QwenClient()
        self.realtime   = RealtimeFeed()
        self.index_tool = IndexDataTool()

    # ------------------------------------------------------------------
    async def scan_market(self, state: AgentState) -> AgentState:
        """扫描大盘环境，更新 universe，筛选 target_symbols"""
        market_overview = await self.index_tool.get_overview()
        sentiment  = self._classify_market_sentiment(market_overview)
        risk_level = self._classify_risk_level(market_overview)

        candidates     = await self.realtime.get_hot_stocks(top_n=50)
        target_symbols = [s["symbol"] for s in candidates[:20]]

        return {
            **state,
            "timestamp":       datetime.now().isoformat(),
            "market_overview": market_overview,
            "market_sentiment": sentiment,
            "risk_level":      risk_level,
            "target_symbols":  target_symbols,
            "logs": [f"[Orchestrator] 市场扫描完成，筛选标的 {len(target_symbols)} 只"],
        }

    # ------------------------------------------------------------------
    async def aggregate_signals(self, state: AgentState) -> AgentState:
        """加权聚合四维信号，生成每个标的的综合评分"""
        signals = state.get("signals", [])
        weights = self._load_weights()   # 动态权重

        scores:  Dict[str, float] = {}
        details: Dict[str, List]  = {}

        direction_map = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}

        for signal in signals:
            symbol = signal.get("symbol", "market")
            dim    = signal.get("dimension", "")
            weight = weights.get(dim, 0.25)
            d_score = direction_map.get(signal.get("direction", "neutral"), 0.0)
            weighted = (
                d_score
                * signal.get("strength", 0.5)
                * signal.get("confidence", 0.5)
                * weight
            )
            scores[symbol] = scores.get(symbol, 0.0) + weighted
            details.setdefault(symbol, []).append(signal)

        # LLM 二次审核：对评分前 5 标的做综合分析
        top_symbols      = sorted(scores, key=lambda s: scores[s], reverse=True)[:5]
        analysis_reports = []
        for sym in top_symbols:
            prompt = SIGNAL_AGGREGATION_PROMPT.format(
                symbol=sym,
                score=round(scores[sym], 4),
                signals=json.dumps(details.get(sym, []), ensure_ascii=False, indent=2),
                market_overview=json.dumps(
                    state.get("market_overview", {}), ensure_ascii=False
                ),
            )
            report_text = await self.llm.chat(prompt)
            analysis_reports.append(
                {"symbol": sym, "score": scores[sym], "report": report_text}
            )

        return {
            **state,
            "analysis_reports": analysis_reports,
            "logs": [f"[Orchestrator] 信号聚合完成，评分标的 {len(scores)} 只"],
        }

    # ------------------------------------------------------------------
    async def make_decision(self, state: AgentState) -> AgentState:
        """根据聚合报告 + 组合状态生成最终交易决策"""
        memory        = state.get("memory", {})
        learned_rules = memory.get("learned_rules", [])

        prompt = DECISION_PROMPT.format(
            reports=json.dumps(
                state.get("analysis_reports", []), ensure_ascii=False, indent=2
            ),
            portfolio=json.dumps(
                state.get("portfolio", {}), ensure_ascii=False, indent=2
            ),
            risk_level=state.get("risk_level", "medium"),
            market_sentiment=state.get("market_sentiment", "neutral"),
            learned_rules="\n".join(learned_rules) if learned_rules else "暂无",
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            decisions: List[TradeDecision] = json.loads(response)
            if not isinstance(decisions, list):
                decisions = []
        except Exception:
            decisions = []

        return {
            **state,
            "decisions":       decisions,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "logs": [f"[Orchestrator] 决策生成完成，共 {len(decisions)} 条"],
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _classify_market_sentiment(self, overview: Dict) -> str:
        change_pct = overview.get("sh_index_change_pct", 0)
        if change_pct > 1.5:
            return "greed"
        if change_pct < -1.5:
            return "fear"
        return "neutral"

    def _classify_risk_level(self, overview: Dict) -> str:
        vix       = overview.get("vix", 20)
        sh_change = abs(overview.get("sh_index_change_pct", 0))
        if vix > 35 or sh_change > 4:
            return "extreme"
        if vix > 25 or sh_change > 2:
            return "high"
        if vix > 15:
            return "medium"
        return "low"

    def _load_weights(self) -> Dict[str, float]:
        """运行时动态加载权重（支持 self_evolution 热更新）"""
        try:
            from self_evolution.knowledge_updater import KnowledgeUpdater
            return KnowledgeUpdater().load_current_weights()
        except Exception:
            return self.DIMENSION_WEIGHTS
