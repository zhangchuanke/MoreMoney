"""
订单管理工具 - 对接券商 API
支持：迅投 QMT / 模拟盘（Paper Trading）
"""
import asyncio
from datetime import datetime
from typing import Dict

from config.settings import settings


class OrderManager:
    """
    订单管理器。
    实盘模式：对接 xtquant (迅投QMT)
    模拟模式：内存模拟成交
    """

    def __init__(self):
        self.mode = settings.TRADING_MODE   # "paper" | "live"
        self._paper_orders: Dict[str, Dict] = {}
        self._order_counter = 0
        if self.mode == "live":
            self._init_xt()

    def _init_xt(self):
        """初始化迅投 QMT 接口"""
        try:
            from xtquant import xttrader
            self.xt = xttrader
            self.xt.connect()
        except ImportError:
            print("[OrderManager] xtquant 未安装，切换到模拟模式")
            self.mode = "paper"

    async def place(self, order: Dict) -> Dict:
        """下单，返回成交结果"""
        if self.mode == "paper":
            return await self._paper_trade(order)
        return await self._live_trade(order)

    async def _paper_trade(self, order: Dict) -> Dict:
        """模拟成交（假设立即全成）"""
        await asyncio.sleep(0.05)  # 模拟网络延迟
        self._order_counter += 1
        order_id = f"PAPER_{self._order_counter:06d}"
        price = order.get("price") or self._get_mock_price(order["symbol"])
        filled_order = {
            **order,
            "order_id": order_id,
            "status": "filled",
            "filled_price": price,
            "filled_qty": order.get("quantity", 0),
            "commission": round(price * order.get("quantity", 0) * 0.0003, 2),
            "filled_at": datetime.now().isoformat(),
        }
        self._paper_orders[order_id] = filled_order
        print(f"[PaperTrade] {order['action'].upper()} {order['symbol']} "
              f"x{order.get('quantity', 0)} @ {price:.2f}")
        return filled_order

    async def _live_trade(self, order: Dict) -> Dict:
        """实盘下单（迅投QMT）"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_live_trade, order
        )

    def _sync_live_trade(self, order: Dict) -> Dict:
        try:
            from xtquant import xtconstant
            direction = xtconstant.STOCK_BUY if order["action"] == "buy" else xtconstant.STOCK_SELL
            order_type = xtconstant.FIX_PRICE if order.get("price") else xtconstant.LATEST_PRICE
            order_id = self.xt.order_stock(
                account=settings.XT_ACCOUNT,
                stock_code=order["symbol"],
                order_type=order_type,
                order_volume=order.get("quantity", 0),
                price_type=order_type,
                price=order.get("price") or 0,
                strategy_name="MoreMoney",
                order_remark=order.get("reasoning", "")[:50],
            )
            return {
                **order,
                "order_id": str(order_id),
                "status": "submitted",
                "filled_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {**order, "status": "error", "error": str(e)}

    def _get_mock_price(self, symbol: str) -> float:
        import random
        return round(random.uniform(5, 100), 2)

    async def cancel(self, order_id: str) -> bool:
        """撤单"""
        if self.mode == "paper":
            if order_id in self._paper_orders:
                self._paper_orders[order_id]["status"] = "cancelled"
                return True
            return False
        # 实盘撤单
        try:
            self.xt.cancel_order_stock(settings.XT_ACCOUNT, int(order_id))
            return True
        except Exception:
            return False
