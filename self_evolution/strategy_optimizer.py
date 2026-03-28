"""
策略优化器 - 基于历史绩效自动调整策略参数
"""
import json
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.reflection_prompts import STRATEGY_OPTIMIZATION_PROMPT
from core.memory.long_term import LongTermMemory
from self_evolution.knowledge_updater import KnowledgeUpdater


class StrategyOptimizer:
    """
    定期（每周/达到亏损阈值时）触发，
    让 LLM 根据近期交易数据提出参数调整建议。
    """

    def __init__(self):
        self.llm = QwenClient(model="qwen-max")
        self.long_term = LongTermMemory()
        self.knowledge_updater = KnowledgeUpdater()

    async def optimize(self) -> Dict:
        """执行一次策略优化"""
        # 1. 收集近期数据
        recent_trades = self.long_term.get_recent_trades(last_n=30)
        current_weights = self.knowledge_updater.load_current_weights()

        # 2. 统计绩效
        stats = self._calc_stats(recent_trades)

        # 3. LLM 分析并给出优化建议
        prompt = STRATEGY_OPTIMIZATION_PROMPT.format(
            performance_stats=json.dumps(stats, ensure_ascii=False, indent=2),
            current_params=json.dumps(current_weights, ensure_ascii=False, indent=2),
            market_regimes="{}",
            trade_summary=json.dumps(
                [{"symbol": t["symbol"], "action": t["action"],
                  "outcome": t["outcome"], "pnl_pct": t.get("pnl_pct", 0)}
                 for t in recent_trades],
                ensure_ascii=False, indent=2
            ),
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            suggestion = json.loads(response)
        except Exception:
            return {"error": "LLM 输出解析失败", "raw": response}

        # 4. 应用权重更新
        new_weights = suggestion.get("dimension_weights")
        if new_weights and self._weights_valid(new_weights):
            self.knowledge_updater.apply_weight_update(new_weights)

        # 5. 持久化策略版本
        self.long_term.save_strategy_version(
            version=self._next_version(),
            description=suggestion.get("reasoning", ""),
            params=suggestion,
            performance=stats,
        )

        print(f"[StrategyOptimizer] 优化完成: {suggestion.get('reasoning', '')}")
        return suggestion

    def _calc_stats(self, trades: List[Dict]) -> Dict:
        if not trades:
            return {}
        wins = [t for t in trades if t.get("outcome") == "win"]
        losses = [t for t in trades if t.get("outcome") == "loss"]
        pnl_list = [t.get("pnl_pct", 0) for t in trades if t.get("pnl_pct") is not None]
        return {
            "total_trades": len(trades),
            "win_rate": len(wins) / max(len(trades), 1),
            "avg_win_pct": sum(t.get("pnl_pct", 0) for t in wins) / max(len(wins), 1),
            "avg_loss_pct": sum(t.get("pnl_pct", 0) for t in losses) / max(len(losses), 1),
            "avg_pnl_pct": sum(pnl_list) / max(len(pnl_list), 1),
        }

    def _weights_valid(self, weights: Dict) -> bool:
        required = {"technical", "sentiment", "capital_flow", "fundamental"}
        if not required.issubset(weights.keys()):
            return False
        total = sum(weights.values())
        return 0.9 <= total <= 1.1

    def _next_version(self) -> str:
        from datetime import datetime
        return f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
