"""
风控 Agent（全维度升级版）

原有检查项（保留）:
  1. 单股持仓集中度上限
  2. 单日最大亏损限额
  3. 最大回撤熔断
  4. 市场极端波动熔断
  5. 板块过度集中检查
  6. 动态止损位更新

新增检查项:
  7. 前置流动性过滤（target_symbols 剔除低流动性标的）
  8. 个股极端波动熔断（涨跌停、振幅超阈值、盘中急速拉升）
  9. 动态仓位调整（根据净值回撤 + 市场波动率自适应）
  10. 对手盘风险监控（北向 + 主力资金异常流出拦截）
  11. Kill Switch 检查（紧急停止/清仓指令注入决策流）
"""
from datetime import datetime
from typing import Dict, List, Optional

from core.state.agent_state import AgentState
from config.risk_params import RiskParams
from risk.liquidity_filter import LiquidityFilter, LiquidityConfig
from risk.stock_circuit_breaker import (
    StockCircuitBreaker, StockCircuitBreakerConfig, get_stock_circuit_breaker
)
from risk.dynamic_position import DynamicPositionManager, DynamicPositionResult
from risk.counterparty_monitor import (
    CounterpartyMonitor, CounterpartyConfig, get_counterparty_monitor
)
from monitoring.kill_switch import KillSwitch


class RiskAgent:
    """
    风险控制 Agent。
    规则驱动为主（不走 LLM，保证实时性和确定性）。
    """

    def __init__(self):
        self.params = RiskParams()

        # 流动性过滤器
        self.liquidity_filter = LiquidityFilter(LiquidityConfig(
            min_daily_amount=self.params.LIQUIDITY_MIN_DAILY_AMOUNT,
            min_float_cap=self.params.LIQUIDITY_MIN_FLOAT_CAP,
        ))

        # 个股熔断器（全局单例，跨轮次保持冷静期状态）
        self.circuit_breaker: StockCircuitBreaker = get_stock_circuit_breaker()
        self.circuit_breaker.config = StockCircuitBreakerConfig(
            max_daily_amplitude=self.params.CIRCUIT_BREAKER_AMPLITUDE,
            max_consecutive_limit_up=self.params.CIRCUIT_BREAKER_MAX_LIMIT_UP,
            intraday_rapid_threshold=self.params.CIRCUIT_BREAKER_INTRADAY_PCT,
            intraday_rapid_window_minutes=self.params.CIRCUIT_BREAKER_INTRADAY_MINUTES,
            cooldown_seconds=self.params.CIRCUIT_BREAKER_COOLDOWN_SEC,
        )

        # 动态仓位管理器
        self.dynamic_position = DynamicPositionManager(self.params)

        # 对手盘监控（全局单例）
        self.counterparty: CounterpartyMonitor = get_counterparty_monitor()
        self.counterparty.config = CounterpartyConfig(
            northbound_daily_outflow_threshold=self.params.COUNTERPARTY_NB_MARKET_THRESHOLD,
            northbound_stock_outflow_threshold=self.params.COUNTERPARTY_NB_STOCK_THRESHOLD,
            block_trade_outflow_threshold=self.params.COUNTERPARTY_BLOCK_THRESHOLD,
            northbound_consecutive_outflow_days=self.params.COUNTERPARTY_CONSECUTIVE_DAYS,
            defense_mode_block_buy=self.params.COUNTERPARTY_DEFENSE_BLOCK_BUY,
        )

        # Kill Switch
        self.kill_switch = KillSwitch.instance()

    async def assess(self, state: AgentState) -> AgentState:
        portfolio       = state.get("portfolio", {})
        market_overview = state.get("market_overview", {})
        risk_flags: List[str] = []
        circuit_breaker   = False
        daily_loss_limit  = False

        # ── 0. Kill Switch 检查 ──────────────────────────────────────
        ks_status = self.kill_switch.status()
        if not self.kill_switch.is_trading_allowed():
            risk_flags.append(f"[KillSwitch] 交易已停止: {ks_status['state']}")
            circuit_breaker = True

        if self.kill_switch.should_liquidate():
            risk_flags.append("[KillSwitch] 一键清仓指令激活")
            # 通知执行层强制清仓
            state = {**state, "force_liquidate": True}

        # ── 1. 日内止损检查 ──────────────────────────────────────────
        daily_pnl_pct = self._calc_daily_pnl_pct(portfolio)
        if daily_pnl_pct <= -self.params.MAX_DAILY_LOSS_PCT:
            daily_loss_limit = True
            risk_flags.append(
                f"日内亏损 {daily_pnl_pct:.2%} 已触及止损线 "
                f"-{self.params.MAX_DAILY_LOSS_PCT:.2%}"
            )

        # ── 2. 最大回撤熔断 ──────────────────────────────────────────
        max_drawdown = portfolio.get("max_drawdown", 0)
        if max_drawdown >= self.params.MAX_DRAWDOWN_LIMIT:
            circuit_breaker = True
            risk_flags.append(
                f"最大回撤 {max_drawdown:.2%} 触及熔断阈值 "
                f"{self.params.MAX_DRAWDOWN_LIMIT:.2%}"
            )

        # ── 3. 大盘极端波动熔断 ─────────────────────────────────────
        sh_change = abs(market_overview.get("sh_index_change_pct", 0))
        if sh_change >= self.params.MARKET_CIRCUIT_BREAKER_PCT:
            circuit_breaker = True
            risk_flags.append(f"大盘波动 {sh_change:.2%} 触发市场熔断")

        # ── 4. 单股集中度检查 ────────────────────────────────────────
        positions    = portfolio.get("positions", {})
        total_assets = portfolio.get("total_assets", 1)
        for symbol, pos in positions.items():
            pos_pct = pos.get("market_value", 0) / max(total_assets, 1)
            if pos_pct > self.params.MAX_SINGLE_POSITION_PCT:
                risk_flags.append(
                    f"{symbol} 持仓占比 {pos_pct:.2%} 超过上限 "
                    f"{self.params.MAX_SINGLE_POSITION_PCT:.2%}"
                )

        # ── 5. 板块集中度检查 ────────────────────────────────────────
        sector_concentration = self._calc_sector_concentration(positions)
        for sector, pct in sector_concentration.items():
            if pct > self.params.MAX_SECTOR_CONCENTRATION_PCT:
                risk_flags.append(
                    f"板块 [{sector}] 集中度 {pct:.2%} 超过上限"
                )

        # ── 6. 更新动态止损 ──────────────────────────────────────────
        updated_positions = self._update_stop_loss(positions)

        # ── 7. 前置流动性过滤（target_symbols）──────────────────────
        target_symbols: List[str] = state.get("target_symbols", [])
        market_quotes:  Dict      = state.get("market_quotes", {})
        if target_symbols:
            passed_syms, rejected_syms = self.liquidity_filter.filter_symbols(
                target_symbols, market_quotes
            )
            if rejected_syms:
                risk_flags.append(
                    f"流动性过滤: 剔除 {len(rejected_syms)} 只低流动性标的 "
                    f"({', '.join(rejected_syms[:5])}{'...' if len(rejected_syms)>5 else ''})"
                )
            target_symbols = passed_syms

        # ── 8. 个股极端波动熔断（对决策列表过滤）───────────────────
        decisions: List[Dict] = state.get("decisions", [])
        filtered_decisions: List[Dict] = []
        for d in decisions:
            sym    = d.get("symbol", "")
            action = d.get("action", "hold")
            if action in ("buy", "add", "sell"):
                quote = market_quotes.get(sym, {})
                cb_events = self.circuit_breaker.check(sym, action, quote)
                blocked = [e for e in cb_events if e.severity == "block"]
                if blocked:
                    reason = blocked[0].reason
                    risk_flags.append(f"[StockCB] {sym} 决策被熔断: {reason}")
                    # 降级为 hold
                    d = {**d, "action": "hold", "circuit_breaker_blocked": reason}
            filtered_decisions.append(d)

        # ── 9. 动态仓位调整 ──────────────────────────────────────────
        current_nav = total_assets
        peak_nav    = portfolio.get("peak_nav", total_assets)
        vix         = market_overview.get("vix", 20.0)
        sh_amplitude= market_overview.get("sh_amplitude", 0.0)
        risk_level_now = self._calc_risk_level(
            daily_pnl_pct, max_drawdown, sh_change, len(risk_flags)
        )
        dynamic_params: Optional[DynamicPositionResult] = None
        if self.params.DYNAMIC_POSITION_ENABLED:
            dynamic_params = self.dynamic_position.compute(
                current_nav=current_nav,
                peak_nav=peak_nav,
                vix=vix,
                sh_amplitude=sh_amplitude,
                risk_level=risk_level_now,
            )
            risk_flags_dp = self._check_dynamic_position_breach(
                positions, total_assets, dynamic_params
            )
            risk_flags.extend(risk_flags_dp)

        # ── 10. 对手盘风险监控 ───────────────────────────────────────
        # 从 state 注入资金流数据（由 CapitalFlowAgent 写入）
        capital_flow = state.get("capital_flow_summary", {})
        nb_market = capital_flow.get("northbound_net_billion", 0.0)
        if nb_market != 0.0:
            self.counterparty.update_northbound_market(nb_market)

        for sym_flow in capital_flow.get("stock_flows", []):
            sym = sym_flow.get("symbol", "")
            nb_wan = sym_flow.get("northbound_net_wan", 0.0)
            block_wan = sym_flow.get("block_trade_net_wan", 0.0)
            if sym:
                self.counterparty.update_northbound_stock(sym, nb_wan)
                self.counterparty.update_block_trade(sym, block_wan)

        # 对决策列表做对手盘拦截
        final_decisions: List[Dict] = []
        for d in filtered_decisions:
            sym    = d.get("symbol", "")
            action = d.get("action", "hold")
            if action in ("buy", "add"):
                cp_events = self.counterparty.check(sym, action)
                cp_blocked = [e for e in cp_events if e.severity == "block"]
                if cp_blocked:
                    reason = cp_blocked[0].reason
                    risk_flags.append(f"[CounterpartyRisk] {sym} 买入被拦截: {reason}")
                    d = {**d, "action": "hold", "counterparty_blocked": reason}
            final_decisions.append(d)

        # ── 综合风险等级 ─────────────────────────────────────────────
        risk_level = risk_level_now
        if dynamic_params:
            risk_level = dynamic_params.effective_risk_level

        return {
            **state,
            "risk_flags":               risk_flags,
            "circuit_breaker_triggered": circuit_breaker,
            "daily_loss_limit_reached":  daily_loss_limit,
            "risk_level":                risk_level,
            "target_symbols":            target_symbols,
            "decisions":                 final_decisions,
            "defense_mode":              self.counterparty.is_defense_mode(),
            "dynamic_risk_params":       dynamic_params.as_dict() if dynamic_params else {},
            "portfolio": {
                **portfolio,
                "positions":   updated_positions,
                "peak_nav":    max(peak_nav, current_nav),
            },

            "logs": [
                f"[RiskAgent] 风控检查完成，风险等级={risk_level}，"
                f"预警 {len(risk_flags)} 项，熟断={circuit_breaker}，"
                f"防御模式={self.counterparty.is_defense_mode()}"
            ],
        }

    # ------------------------------------------------------------------
    def _calc_daily_pnl_pct(self, portfolio):
        total     = portfolio.get("total_assets", 1)
        daily_pnl = portfolio.get("daily_pnl", 0)
        return daily_pnl / max(total, 1)

    def _calc_sector_concentration(self, positions):
        sector_value = {}
        total_value = sum(p.get("market_value", 0) for p in positions.values())
        for pos in positions.values():
            sector = pos.get("sector", "未知")
            sector_value[sector] = sector_value.get(sector, 0) + pos.get("market_value", 0)
        return {s: v / max(total_value, 1) for s, v in sector_value.items()}

    def _update_stop_loss(self, positions):
        """移动止损：持仓盈利超过阈值时，将止损上移。"""
        updated = {}
        for symbol, pos in positions.items():
            cost    = pos.get("cost", 0)
            current = pos.get("current_price", cost)
            pnl_pct = (current - cost) / max(cost, 1)
            stop    = pos.get("stop_loss", cost * (1 - self.params.DEFAULT_STOP_LOSS_PCT))
            if pnl_pct >= 0.10 and stop < cost:
                stop = cost
            elif pnl_pct >= 0.20:
                stop = max(stop, cost * 1.05)
            updated[symbol] = {**pos, "stop_loss": round(stop, 3)}
        return updated

    def _check_dynamic_position_breach(self, positions, total_assets, dp):
        """检查当前持仓是否超过动态仓位上限。"""
        flags = []
        for symbol, pos in positions.items():
            pos_pct = pos.get("market_value", 0) / max(total_assets, 1)
            if pos_pct > dp.max_single_position_pct:
                flags.append(
                    f"{symbol} 持仓 {pos_pct:.2%} 超过动态上限 "
                    f"{dp.max_single_position_pct:.2%}（波动率调整后）"
                )
        return flags

    def _calc_risk_level(self, daily_pnl_pct, max_drawdown, sh_change, flag_count):
        score = 0
        if daily_pnl_pct <= -0.02: score += 2
        if daily_pnl_pct <= -0.01: score += 1
        if max_drawdown  >= 0.15:  score += 2
        if max_drawdown  >= 0.10:  score += 1
        if sh_change     >= 2.5:   score += 2
        if flag_count    >= 3:     score += 1
        if score >= 5: return "extreme"
        if score >= 3: return "high"
        if score >= 1: return "medium"
        return "low"
