"""
绩效评估工具 - 评估每轮交易结果
"""
from typing import Dict, List


class PerformanceEvaluator:

    # 策略调整阈值
    STRATEGY_UPDATE_THRESHOLD = {
        "win_rate_min": 0.40,        # 胜率低于40%触发调整
        "max_drawdown_trigger": 0.10,# 回撤超10%触发调整
        "consecutive_losses": 5,     # 连续亏损5次触发调整
    }

    def evaluate(self, portfolio: Dict, executed_orders: List[Dict]) -> Dict:
        """评估本轮绩效"""
        total_assets = portfolio.get("total_assets", 1)
        daily_pnl = portfolio.get("daily_pnl", 0)
        max_drawdown = portfolio.get("max_drawdown", 0)

        # 本轮订单统计
        filled = [o for o in executed_orders if o.get("status") == "filled"]
        buy_count  = sum(1 for o in filled if o.get("action") == "buy")
        sell_count = sum(1 for o in filled if o.get("action") == "sell")

        return {
            "total_assets": total_assets,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl / max(total_assets, 1),
            "max_drawdown": max_drawdown,
            "orders_filled": len(filled),
            "buy_orders": buy_count,
            "sell_orders": sell_count,
            "win_rate": portfolio.get("win_rate", 0),
            "sharpe_ratio": portfolio.get("sharpe_ratio", 0),
        }

    def needs_strategy_update(self, perf: Dict) -> bool:
        """判断是否需要策略大调整"""
        thresholds = self.STRATEGY_UPDATE_THRESHOLD
        if perf.get("win_rate", 1) < thresholds["win_rate_min"]:
            return True
        if perf.get("max_drawdown", 0) > thresholds["max_drawdown_trigger"]:
            return True
        return False
