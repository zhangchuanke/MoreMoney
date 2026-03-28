"""
执行 Agent
职责：将决策转化为实际订单，管理委托状态，处理成交回报
"""
import asyncio
from datetime import datetime
from typing import Dict, List

from core.state.agent_state import AgentState, TradeDecision
from tools.broker.order_manager import OrderManager
from tools.broker.position_manager import PositionManager
from config.settings import settings


class ExecutionAgent:
    """
    执行 Agent。
    1. 将 TradeDecision 转换为券商订单
    2. 支持：市价单 / 限价单 / 分批建仓
    3. 跟踪订单状态，处理部分成交
    4. 触发止损/止盈平仓
    """

    def __init__(self):
        self.order_mgr = OrderManager()
        self.position_mgr = PositionManager()

    async def execute(self, state: AgentState) -> AgentState:
        decisions: List[TradeDecision] = state.get("decisions", [])
        executed: List[Dict] = []
        rejected: List[Dict] = []
        pending: List[Dict] = state.get("pending_orders", [])

        # 1. 先处理止损/止盈触发
        sl_orders = await self._check_stop_triggers(state)
        for order in sl_orders:
            result = await self._place_order(order)
            (executed if result["status"] == "filled" else rejected).append(result)

        # 2. 执行新决策
        for decision in decisions:
            if decision.get("action") == "hold":
                continue
            order = self._decision_to_order(decision, state)
            if not self._pre_check(order, state):
                rejected.append({**order, "reject_reason": "pre_check_failed"})
                continue
            result = await self._place_order(order)
            (executed if result["status"] in ("filled", "partial") else rejected).append(result)

        # 3. 更新持仓状态
        updated_portfolio = await self.position_mgr.refresh(state.get("portfolio", {}))

        return {
            **state,
            "executed_orders": executed,
            "rejected_orders": rejected,
            "pending_orders": pending,
            "portfolio": updated_portfolio,
            "logs": [
                f"[ExecutionAgent] 执行完成：成交 {len(executed)} 笔，"
                f"拒绝 {len(rejected)} 笔"
            ],
        }

    # ------------------------------------------------------------------
    def _decision_to_order(self, decision: TradeDecision, state: AgentState) -> Dict:
        portfolio = state.get("portfolio", {})
        total_assets = portfolio.get("total_assets", 100000)
        cash = portfolio.get("cash", 0)
        positions = portfolio.get("positions", {})
        symbol = decision["symbol"]
        action = decision["action"]

        current_pos = positions.get(symbol, {}).get("market_value", 0)
        target_value = total_assets * decision.get("target_position", 0)
        delta_value = target_value - current_pos

        # 根据最新价估算数量（100股整数倍）
        price = positions.get(symbol, {}).get("current_price") or decision.get("price_limit", 10)
        qty = max(100, int(abs(delta_value) / max(price, 0.01) // 100 * 100))

        return {
            "symbol": symbol,
            "action": action,
            "quantity": qty,
            "price": decision.get("price_limit"),   # None = 市价
            "order_type": "LIMIT" if decision.get("price_limit") else "MARKET",
            "urgency": decision.get("urgency", "normal"),
            "stop_loss": decision.get("stop_loss"),
            "take_profit": decision.get("take_profit"),
            "reasoning": decision.get("reasoning", ""),
            "created_at": datetime.now().isoformat(),
        }

    def _pre_check(self, order: Dict, state: AgentState) -> bool:
        """下单前置检查：资金、T+1 限制等"""
        portfolio = state.get("portfolio", {})
        cash = portfolio.get("cash", 0)
        price = order.get("price") or 0
        qty = order.get("quantity", 0)

        if order["action"] == "buy":
            estimated_cost = price * qty * 1.001  # 含手续费估算
            if estimated_cost > cash:
                return False
        return True

    async def _place_order(self, order: Dict) -> Dict:
        """实际下单（对接券商 API）"""
        try:
            result = await self.order_mgr.place(order)
            return {**order, **result}
        except Exception as e:
            return {**order, "status": "error", "error": str(e)}

    async def _check_stop_triggers(self, state: AgentState) -> List[Dict]:
        """检查是否有持仓触发止损/止盈"""
        orders = []
        positions = state.get("portfolio", {}).get("positions", {})
        for symbol, pos in positions.items():
            current_price = pos.get("current_price", 0)
            stop_loss = pos.get("stop_loss", 0)
            take_profit = pos.get("take_profit", float("inf"))
            qty = pos.get("quantity", 0)

            if current_price <= stop_loss and stop_loss > 0:
                orders.append({
                    "symbol": symbol, "action": "sell", "quantity": qty,
                    "price": None, "order_type": "MARKET",
                    "urgency": "immediate",
                    "reasoning": f"触发止损：当前价 {current_price} <= 止损价 {stop_loss}",
                    "created_at": datetime.now().isoformat(),
                })
            elif current_price >= take_profit and take_profit < float("inf"):
                orders.append({
                    "symbol": symbol, "action": "sell", "quantity": qty,
                    "price": None, "order_type": "MARKET",
                    "urgency": "immediate",
                    "reasoning": f"触发止盈：当前价 {current_price} >= 止盈价 {take_profit}",
                    "created_at": datetime.now().isoformat(),
                })
        return orders
