"""
主编排 Agent - 负责市场扫描、信号聚合、最终决策

重构要点：
  - scan_market() 新增市场风格识别（MarketRegimeDetector），结果写入 state
  - aggregate_signals() 废弃 operator.add 数值累加，改为 AdaptiveSignalAggregator
    多维度投票制 + 场景优先权重（财报季/题材/极端行情一票否决）
  - make_decision() 注入市场风格信息辅助 LLM 决策
"""
import json
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.analysis_prompts import SIGNAL_AGGREGATION_PROMPT, DECISION_PROMPT
from core.state.agent_state import AgentState, TradeDecision
from core.market_regime import MarketRegimeDetector
from core.signal_aggregator import AdaptiveSignalAggregator
from tools.market_data.realtime_feed import RealtimeFeed
from tools.market_data.index_data import IndexDataTool


class OrchestratorAgent:
    """
    主编排 Agent：
      1. scan_market()       - 扫描市场，识别市场风格，筛选标的
      2. aggregate_signals() - 自适应混合聚合四维信号（投票制 + 一票否决）
      3. make_decision()     - 最终决策（综合 LLM 推理 + 市场风格上下文）
    """

    # 默认四维权重（实际运行时由市场风格 + 动态权重文件双重覆盖）
    DIMENSION_WEIGHTS: Dict[str, float] = {
        "technical":    0.30,
        "sentiment":    0.25,
        "capital_flow": 0.25,
        "fundamental":  0.20,
    }

    def __init__(self):
        self.llm          = QwenClient()
        self.realtime     = RealtimeFeed()
        self.index_tool   = IndexDataTool()
        self.regime_detector = MarketRegimeDetector()
        self.aggregator      = AdaptiveSignalAggregator()

    # ------------------------------------------------------------------
    async def scan_market(self, state: AgentState) -> AgentState:
        """扫描大盘环境，识别市场风格，更新 universe，筛选 target_symbols"""
        market_overview = await self.index_tool.get_overview()
        sentiment  = self._classify_market_sentiment(market_overview)
        risk_level = self._classify_risk_level(market_overview)

        # ── 新增：市场风格识别 ──────────────────────────────────────────
        regime_result = self.regime_detector.detect(market_overview)

        candidates     = await self.realtime.get_hot_stocks(top_n=50)
        target_symbols = [s["symbol"] for s in candidates[:20]]

        return {
            **state,
            "timestamp":        datetime.now().isoformat(),
            "market_overview":  market_overview,
            "market_sentiment": sentiment,
            "risk_level":       risk_level,
            "target_symbols":   target_symbols,
            # 市场风格写入 state（供聚合器、决策节点使用）
            "market_regime":    regime_result.regime,
            "market_regime_detail": {
                "regime":       regime_result.regime,
                "confidence":   regime_result.confidence,
                "veto_active":  regime_result.veto_active,
                "description":  regime_result.description,
                "base_weights": regime_result.base_weights,
                "signals":      regime_result.signals,
            },
            "logs": [
                f"[Orchestrator] 市场扫描完成，筛选标的 {len(target_symbols)} 只",
                f"[Orchestrator] 市场风格: {regime_result.regime} "
                f"(置信度={regime_result.confidence:.2f}) | {regime_result.description}",
            ],
        }

    # ------------------------------------------------------------------
    async def aggregate_signals(self, state: AgentState) -> AgentState:
        """
        自适应混合聚合四维信号。

        核心变化（替代原始 operator.add 数值累加）：
          - 使用 AdaptiveSignalAggregator 进行多维度投票制聚合
          - 根据市场风格自动切换权重矩阵
          - 财报季 / 题材炒作期触发场景优先权重
          - 极端行情触发一票否决，直接输出 neutral/hold
        """
        signals = state.get("signals", [])

        # 重建 MarketRegimeResult（从 state 读取，避免重复调用接口）
        regime_detail = state.get("market_regime_detail", {})
        from core.market_regime import MarketRegimeResult, REGIME_BASE_WEIGHTS, DEFAULT_WEIGHTS
        regime_name = regime_detail.get("regime", "volatile")
        regime = MarketRegimeResult(
            regime=regime_name,
            confidence=regime_detail.get("confidence", 0.5),
            base_weights=regime_detail.get(
                "base_weights",
                REGIME_BASE_WEIGHTS.get(regime_name, DEFAULT_WEIGHTS),
            ),
            veto_active=regime_detail.get("veto_active", False),
            signals=regime_detail.get("signals", {}),
            description=regime_detail.get("description", ""),
        )

        is_earnings = AdaptiveSignalAggregator.is_earnings_season()

        # ── 按标的聚合 ────────────────────────────────────────────────
        symbol_set = list(dict.fromkeys(
            s.get("symbol", "market") for s in signals
        ))

        aggregated_scores: Dict[str, float] = {}
        aggregated_details: Dict[str, Dict] = {}

        for symbol in symbol_set:
            agg = self.aggregator.aggregate(
                symbol=symbol,
                signals=signals,
                regime=regime,
                is_earnings_season=is_earnings,
            )
            aggregated_scores[symbol]  = agg.final_score
            aggregated_details[symbol] = {
                "final_score":   agg.final_score,
                "vote_result":   agg.vote_result,
                "vote_breakdown": agg.vote_breakdown,
                "vote_weights":  agg.vote_weights,
                "veto_triggered": agg.veto_triggered,
                "veto_reason":   agg.veto_reason,
                "confidence":    agg.confidence,
            }

        # ── LLM 二次审核：对评分前 5 标的做综合分析 ───────────────────
        top_symbols      = sorted(
            aggregated_scores, key=lambda s: aggregated_scores[s], reverse=True
        )[:5]
        analysis_reports = []

        for sym in top_symbols:
            sym_signals = [s for s in signals if s.get("symbol") == sym]
            prompt = SIGNAL_AGGREGATION_PROMPT.format(
                symbol=sym,
                score=round(aggregated_scores[sym], 4),
                signals=json.dumps(sym_signals, ensure_ascii=False, indent=2),
                market_overview=json.dumps(
                    state.get("market_overview", {}), ensure_ascii=False
                ),
            )
            report_text = await self.llm.chat(prompt)
            analysis_reports.append({
                "symbol":        sym,
                "score":         aggregated_scores[sym],
                "vote_detail":   aggregated_details.get(sym, {}),
                "regime":        regime.regime,
                "report":        report_text,
            })

        return {
            **state,
            "analysis_reports": analysis_reports,
            "logs": [
                f"[Orchestrator] 信号聚合完成，评分标的 {len(aggregated_scores)} 只",
                f"[Orchestrator] 聚合模式: 自适应投票制 | 风格={regime.regime} "
                f"| 财报季={is_earnings}",
            ],
        }

    # ------------------------------------------------------------------
    async def make_decision(self, state: AgentState) -> AgentState:
        """根据聚合报告 + 组合状态 + 市场风格生成最终交易决策"""
        memory        = state.get("memory", {})
        learned_rules = memory.get("learned_rules", [])
        regime_detail = state.get("market_regime_detail", {})

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

        # 极端行情一票否决：强制清空非风控指令的主动买入决策
        if regime_detail.get("veto_active"):
            decisions = [
                d for d in decisions
                if d.get("action") not in ("buy", "add")
            ]

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
        """保留兼容接口（已由 AdaptiveSignalAggregator 内部处理）"""
        try:
            from self_evolution.knowledge_updater import KnowledgeUpdater
            return KnowledgeUpdater().load_current_weights()
        except Exception:
            return self.DIMENSION_WEIGHTS
