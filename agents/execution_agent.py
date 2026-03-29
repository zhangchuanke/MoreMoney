"""
执行 Agent
职责：将决策转化为实际订单，管理委托状态，处理成交回报
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List

from core.state.agent_state import AgentState, TradeDecision
from tools.broker.order_manager import OrderManager
from tools.broker.position_manager import PositionManager
from config.settings import settings
from compliance.order_compliance import OrderComplianceChecker, ViolationType

logger = logging.getLogger("agents.execution")


class ExecutionAgent:
    """
    执行 Agent。
    1. 将 TradeDecision 转换为券商订单
    2. 支持：市价单 / 限价单 / 分批建仓
    3. 跟踪订单状态，处理部分成交
    4. 触发止损/止盈平仓
    5. 所有订单在下单前经过报撤单合规硬约束检查
    """

    def __init__(self):
        self.order_mgr = OrderManager()
        self.position_mgr = PositionManager()
        self.compliance = OrderComplianceChecker()

    async def execute(self, state: AgentState) -> AgentState:
        decisions: List[TradeDecision] = state.get("decisions", [])
        executed: List[Dict] = []
        rejected: List[Dict] = []
        pending: List[Dict] = state.get("pending_orders", [])

        # 1. 先处理止损/止盈触发
        #    止损单豁免高频/撤单率检查，但仍须通过单笔占比检查
        sl_orders = await self._check_stop_triggers(state)
        for order in sl_orders:
            sl_violations = self.compliance.check_order(order)
            sl_blocks = [
                v for v in sl_violations
                if v.severity == "block"
                and v.violation_type == ViolationType.SINGLE_ORDER_RATIO
            ]
            if sl_blocks:
                reason = "; ".join(str(v) for v in sl_blocks)
                logger.warning("[ExecutionAgent] 止损单被合规拦截(单笔占比): %s", reason)
                rejected.append({
                    **order,
                    "reject_reason": "compliance_block_stop",
                    "compliance_violations": [str(v) for v in sl_blocks],
                })
                continue
            result = await self._place_order(order)
            if result["status"] == "filled":
                self.compliance.record_order(order)
            (executed if result["status"] == "filled" else rejected).append(result)

        # 2. 执行新决策
        for decision in decisions:
            if decision.get("action") == "hold":
                continue
            order = self._decision_to_order(decision, state)

            # 2a. 报撤单合规硬约束检查（强制拦截）
            compliance_violations = self.compliance.check_order(order)
            block_violations = [v for v in compliance_violations if v.severity == "block"]
            if block_violations:
                reason = "; ".join(str(v) for v in block_violations)
                logger.warning("[ExecutionAgent] 订单被合规模块拦截: %s", reason)
                rejected.append({
                    **order,
                    "reject_reason": "compliance_block",
                    "compliance_violations": [str(v) for v in block_violations],
                })
                continue
            # 警告级违规仅记录日志，不拦截
            for v in compliance_violations:
                if v.severity == "warn":
                    logger.warning("[ExecutionAgent] 合规警告: %s", v)

            # 2b. 资金/T+1 前置检查
            if not self._pre_check(order, state):
                rejected.append({**order, "reject_reason": "pre_check_failed"})
                continue

            result = await self._place_order(order)
            if result["status"] in ("filled", "partial"):
                # 成功报单后向合规器登记
                self.compliance.record_order(order)
                executed.append(result)
            else:
                rejected.append(result)

        # 3. 更新持仓状态
        updated_portfolio = await self.position_mgr.refresh(state.get("portfolio", {}))

        compliance_blocks = [
            r for r in rejected
            if r.get("reject_reason", "").startswith("compliance")
        ]
        return {
            **state,
            "executed_orders": executed,
            "rejected_orders": rejected,
            "pending_orders": pending,
            "portfolio": updated_portfolio,
            "compliance_daily_summary": self.compliance.daily_summary(),
            "logs": [
                f"[ExecutionAgent] 执行完成：成交 {len(executed)} 笔，"
                f"拒绝 {len(rejected)} 笔（合规拦截 {len(compliance_blocks)} 笔）"
            ],
        }

    # ------------------------------------------------------------------
    def _decision_to_order(self, decision: TradeDecision, state: AgentState) -> Dict:
        portfolio = state.get("portfolio", {})
        total_assets = portfolio.get("total_assets", 100000)
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
