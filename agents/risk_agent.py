"""
风控 Agent
职责：仓位管理、止损、最大回撤控制、集中度检查、熔断机制
"""
from datetime import datetime
from typing import Dict, List

from core.state.agent_state import AgentState
from config.risk_params import RiskParams


class RiskAgent:
    """
    风险控制 Agent。
    规则驱动为主（不走 LLM，保证实时性和确定性）。

    检查项:
      1. 单股持仓集中度上限
      2. 单日最大亏损限额（日内止损线）
      3. 最大回撤熔断
      4. 市场极端波动熔断
      5. 板块过度集中检查
      6. 动态止损位更新
    """

    def __init__(self):
        self.params = RiskParams()

    async def assess(self, state: AgentState) -> AgentState:
        portfolio = state.get("portfolio", {})
        market_overview = state.get("market_overview", {})
        risk_flags: List[str] = []
        circuit_breaker = False
        daily_loss_limit = False

        # 1. 日内止损检查
        daily_pnl_pct = self._calc_daily_pnl_pct(portfolio)
        if daily_pnl_pct <= -self.params.MAX_DAILY_LOSS_PCT:
            daily_loss_limit = True
            risk_flags.append(
                f"日内亏损 {daily_pnl_pct:.2%} 已触及止损线 -{self.params.MAX_DAILY_LOSS_PCT:.2%}"
            )

        # 2. 最大回撤熔断
        max_drawdown = portfolio.get("max_drawdown", 0)
        if max_drawdown >= self.params.MAX_DRAWDOWN_LIMIT:
            circuit_breaker = True
            risk_flags.append(
                f"最大回撤 {max_drawdown:.2%} 触及熔断阈值 {self.params.MAX_DRAWDOWN_LIMIT:.2%}"
            )

        # 3. 大盘极端波动熔断
        sh_change = abs(market_overview.get("sh_index_change_pct", 0))
        if sh_change >= self.params.MARKET_CIRCUIT_BREAKER_PCT:
            circuit_breaker = True
            risk_flags.append(f"大盘波动 {sh_change:.2%} 触发市场熔断")

        # 4. 单股集中度检查
        positions = portfolio.get("positions", {})
        total_assets = portfolio.get("total_assets", 1)
        for symbol, pos in positions.items():
            pos_pct = pos.get("market_value", 0) / max(total_assets, 1)
            if pos_pct > self.params.MAX_SINGLE_POSITION_PCT:
                risk_flags.append(
                    f"{symbol} 持仓占比 {pos_pct:.2%} 超过上限 {self.params.MAX_SINGLE_POSITION_PCT:.2%}"
                )

        # 5. 板块集中度检查
        sector_concentration = self._calc_sector_concentration(positions)
        for sector, pct in sector_concentration.items():
            if pct > self.params.MAX_SECTOR_CONCENTRATION_PCT:
                risk_flags.append(
                    f"板块 [{sector}] 集中度 {pct:.2%} 超过上限"
                )

        # 6. 更新动态止损
        updated_positions = self._update_stop_loss(positions)

        # 7. 综合风险等级
        risk_level = self._calc_risk_level(
            daily_pnl_pct, max_drawdown, sh_change, len(risk_flags)
        )

        return {
            **state,
            "risk_flags": risk_flags,
            "circuit_breaker_triggered": circuit_breaker,
            "daily_loss_limit_reached": daily_loss_limit,
            "risk_level": risk_level,
            "portfolio": {**portfolio, "positions": updated_positions},
            "logs": [
                f"[RiskAgent] 风控检查完成，风险等级={risk_level}，"
                f"预警 {len(risk_flags)} 项，熔断={circuit_breaker}"
            ],
        }

    # ------------------------------------------------------------------
    def _calc_daily_pnl_pct(self, portfolio: Dict) -> float:
        total = portfolio.get("total_assets", 1)
        daily_pnl = portfolio.get("daily_pnl", 0)
        return daily_pnl / max(total, 1)

    def _calc_sector_concentration(self, positions: Dict) -> Dict[str, float]:
        sector_value: Dict[str, float] = {}
        total_value = sum(p.get("market_value", 0) for p in positions.values())
        for pos in positions.values():
            sector = pos.get("sector", "未知")
            sector_value[sector] = sector_value.get(sector, 0) + pos.get("market_value", 0)
        return {
            s: v / max(total_value, 1) for s, v in sector_value.items()
        }

    def _update_stop_loss(
        self, positions: Dict
    ) -> Dict:
        """移动止损：持仓盈利超过阈值时，将止损上移至成本价"""
        updated = {}
        for symbol, pos in positions.items():
            cost = pos.get("cost", 0)
            current = pos.get("current_price", cost)
            pnl_pct = (current - cost) / max(cost, 1)
            stop = pos.get("stop_loss", cost * (1 - self.params.DEFAULT_STOP_LOSS_PCT))

            # 盈利超过 10% 时移动止损至成本价
            if pnl_pct >= 0.10 and stop < cost:
                stop = cost
            # 盈利超过 20% 时移动止损至 +5%
            elif pnl_pct >= 0.20:
                stop = max(stop, cost * 1.05)

            updated[symbol] = {**pos, "stop_loss": round(stop, 3)}
        return updated

    def _calc_risk_level(
        self,
        daily_pnl_pct: float,
        max_drawdown: float,
        sh_change: float,
        flag_count: int,
    ) -> str:
        score = 0
        if daily_pnl_pct <= -0.02: score += 2
        if daily_pnl_pct <= -0.01: score += 1
        if max_drawdown >= 0.15: score += 2
        if max_drawdown >= 0.10: score += 1
        if sh_change >= 2.5: score += 2
        if flag_count >= 3: score += 1

        if score >= 5: return "extreme"
        if score >= 3: return "high"
        if score >= 1: return "medium"
        return "low"
