"""
反思 / 自我迭代 Agent
职责：复盘本轮交易、评估决策质量、更新策略规则、触发自我进化
"""
import json
import logging
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.reflection_prompts import REFLECTION_PROMPT, RULE_EXTRACTION_PROMPT
from core.state.agent_state import AgentState, AgentMemory
from core.memory.long_term import LongTermMemory
from core.memory.episodic import EpisodicMemory
# ShortTermMemory 未在此 Agent 使用，不导入
from self_evolution.performance_evaluator import PerformanceEvaluator
from self_evolution.knowledge_updater import KnowledgeUpdater
from compliance.rule_boundary import RuleBoundaryChecker

logger = logging.getLogger("agents.reflection")


class ReflectionAgent:
    """
    反思 Agent。
    每轮结束后:
      1. 评估本轮决策质量（胜负、盈亏）
      2. 提取成功/失败模式
      3. 更新 learned_rules（自我归纳的交易规则，经合规边界过滤）
      4. 判断是否需要策略大调整
      5. 更新迭代状态 → 决定下一轮继续还是终止
    """

    def __init__(self):
        self.llm = QwenClient()
        self.long_term = LongTermMemory()
        self.episodic = EpisodicMemory()
        self.evaluator = PerformanceEvaluator()
        self.knowledge_updater = KnowledgeUpdater()
        self.rule_boundary = RuleBoundaryChecker()

    async def reflect(self, state: AgentState) -> AgentState:
        executed_orders = state.get("executed_orders", [])
        portfolio = state.get("portfolio", {})
        signals = state.get("signals", [])
        risk_flags = state.get("risk_flags", [])
        memory: AgentMemory = state.get("memory", {})

        # 1. 绩效评估
        perf = self.evaluator.evaluate(portfolio, executed_orders)

        # 2. 将已完成交易记入长期记忆
        for order in executed_orders:
            if order.get("status") == "filled":
                self.long_term.save_trade({
                    "symbol": order.get("symbol"),
                    "action": order.get("action"),
                    "entry_price": order.get("price"),
                    "reasoning": order.get("reasoning"),
                    "outcome": "pending",   # 待平仓后更新
                    "market_date": datetime.now().strftime("%Y-%m-%d"),
                })

        # 3. 极端风险事件记入事件记忆
        if risk_flags:
            self.episodic.record_episode(
                event_type="risk_flag",
                description="; ".join(risk_flags),
                context={"market_overview": state.get("market_overview", {})},
                agent_response={"orders_executed": len(executed_orders)},
                outcome=perf,
                lesson="",
                severity=min(len(risk_flags) * 0.2, 1.0),
            )

        # 4. LLM 反思：提取规则、评估决策
        existing_rules = memory.get("learned_rules", [])
        reflection_text = await self._llm_reflect(state, perf, existing_rules)

        # 5. 提取新规则并通过合规边界过滤，拒绝任何含市场操纵/异常交易意图的规则
        raw_rules = await self._extract_rules(reflection_text, existing_rules)
        new_rules, rejected_rules = self.rule_boundary.filter_rules(raw_rules)
        if rejected_rules:
            logger.warning(
                "[ReflectionAgent] %d 条规则因触及合规红线被拒绝写入: %s",
                len(rejected_rules),
                "; ".join(str(r) for r in rejected_rules),
            )
        for rule in new_rules:
            self.long_term.save_rule(rule, source="reflection", confidence=0.6)

        # 6. 判断是否需要策略大调整
        strategy_update_needed = self.evaluator.needs_strategy_update(perf)

        # 7. 更新 market_regime
        market_regime = self._detect_regime(state)

        # 8. 更新 memory
        recent_decisions = memory.get("recent_decisions", [])[-20:]
        recent_decisions.append({
            "timestamp": datetime.now().isoformat(),
            "orders": len(executed_orders),
            "perf": perf,
        })

        updated_memory: AgentMemory = {
            **memory,
            "recent_decisions": recent_decisions,
            "learned_rules": (existing_rules + new_rules)[-50:],   # 保留最近50条（均已通过合规过滤）
            "market_regime": market_regime,
            "last_reflection": datetime.now().isoformat(),
        }

        # 9. 是否终止
        iteration = state.get("iteration_count", 0)
        max_iter = state.get("max_iterations", 10)
        should_terminate = (
            iteration >= max_iter
            or state.get("circuit_breaker_triggered", False)
            or not self._is_trading_time()
        )

        return {
            **state,
            "memory": updated_memory,
            "reflection_needed": False,
            "strategy_update_needed": strategy_update_needed,
            "should_terminate": should_terminate,
            "logs": [
                f"[ReflectionAgent] 反思完成，新规则 {len(new_rules)} 条"
                f"（合规过滤拒绝 {len(rejected_rules)} 条），"
                f"策略调整需要={strategy_update_needed}，终止={should_terminate}"
            ],
        }

    # ------------------------------------------------------------------
    async def _llm_reflect(
        self, state: AgentState, perf: Dict, existing_rules: List[str]
    ) -> str:
        prompt = REFLECTION_PROMPT.format(
            executed_orders=json.dumps(
                state.get("executed_orders", []), ensure_ascii=False, indent=2
            ),
            portfolio=json.dumps(
                state.get("portfolio", {}), ensure_ascii=False, indent=2
            ),
            signals=json.dumps(
                state.get("signals", [])[:10], ensure_ascii=False, indent=2
            ),
            risk_flags=json.dumps(state.get("risk_flags", []), ensure_ascii=False),
            perf=json.dumps(perf, ensure_ascii=False, indent=2),
            existing_rules="\n".join(existing_rules) if existing_rules else "暂无",
            market_regime=state.get("memory", {}).get("market_regime", "unknown"),
        )
        return await self.llm.chat(prompt)

    async def _extract_rules(
        self, reflection_text: str, existing_rules: List[str]
    ) -> List[str]:
        prompt = RULE_EXTRACTION_PROMPT.format(
            reflection=reflection_text,
            existing_rules="\n".join(existing_rules) if existing_rules else "暂无",
        )
        response = await self.llm.chat(prompt, response_format="json")
        try:
            data = json.loads(response)
            return data.get("new_rules", [])
        except Exception:
            return []

    def _detect_regime(self, state: AgentState) -> str:
        overview = state.get("market_overview", {})
        change = overview.get("sh_index_change_pct", 0)
        if abs(change) > 2.5:
            return "volatile"
        if change > 0.5:
            return "trending_up"
        if change < -0.5:
            return "trending_down"
        return "ranging"

    def _is_trading_time(self) -> bool:
        now = datetime.now()
        hour, minute = now.hour, now.minute
        # A股交易时段：9:30-11:30, 13:00-15:00
        morning = (9, 30) <= (hour, minute) <= (11, 30)
        afternoon = (13, 0) <= (hour, minute) <= (15, 0)
        return morning or afternoon
