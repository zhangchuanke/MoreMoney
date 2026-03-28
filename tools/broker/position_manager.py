"""
持仓管理工具
"""
import asyncio
from datetime import datetime
from typing import Dict

from config.settings import settings


class PositionManager:

    def __init__(self):
        self.mode = settings.TRADING_MODE
        # 模拟持仓（paper trading）
        self._paper_portfolio: Dict = {
            "total_assets": settings.INITIAL_CAPITAL,
            "cash": settings.INITIAL_CAPITAL,
            "positions": {},
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "sharpe_ratio": 0.0,
        }

    async def refresh(self, current_portfolio: Dict) -> Dict:
        """刷新持仓数据（实盘从券商拉取，模拟盘更新模拟值）"""
        if self.mode == "paper":
            return self._update_paper(current_portfolio)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_live_refresh
        )

    def _update_paper(self, portfolio: Dict) -> Dict:
        """更新模拟持仓的市值和盈亏"""
        positions = portfolio.get("positions", {})
        total_position_value = 0.0

        for symbol, pos in positions.items():
            qty = pos.get("quantity", 0)
            current_price = pos.get("current_price", pos.get("cost", 0))
            market_value = qty * current_price
            cost_value = qty * pos.get("cost", current_price)
            pnl = market_value - cost_value
            pnl_pct = pnl / max(cost_value, 1)
            positions[symbol] = {
                **pos,
                "market_value": round(market_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
            }
            total_position_value += market_value

        cash = portfolio.get("cash", 0)
        total_assets = cash + total_position_value
        initial = settings.INITIAL_CAPITAL
        total_pnl = total_assets - initial
        total_pnl_pct = total_pnl / initial

        return {
            **portfolio,
            "positions": positions,
            "total_assets": round(total_assets, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 4),
            "refreshed_at": datetime.now().isoformat(),
        }

    def _sync_live_refresh(self) -> Dict:
        """从迅投QMT拉取实时持仓"""
        try:
            from xtquant import xttrader
            account = settings.XT_ACCOUNT
            asset = xttrader.query_stock_asset(account)
            positions_raw = xttrader.query_stock_positions(account)

            positions = {}
            for p in positions_raw:
                symbol = p.stock_code
                positions[symbol] = {
                    "quantity": p.volume,
                    "cost": p.open_price,
                    "current_price": p.market_price,
                    "market_value": p.market_value,
                    "pnl": p.profit_loss,
                    "pnl_pct": p.profit_loss_ratio,
                    "sector": "",
                }

            return {
                "total_assets": asset.total_asset,
                "cash": asset.cash,
                "positions": positions,
                "daily_pnl": asset.profit_loss,
                "total_pnl": 0,
                "max_drawdown": 0,
                "win_rate": 0,
                "sharpe_ratio": 0,
                "refreshed_at": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"[PositionManager] 实盘持仓获取失败: {e}")
            return {}
