"""
Slippage estimation, commission cost, and break-even adaptation module.

Handles the inherent delay of free market data feeds:
  - pytdx  : ~1-3 s delay
  - akshare: ~3-10 s delay (REST)
  - Level-2: <100 ms (paid subscription)

New in this version:
  - estimate_round_trip_cost(): ????????????? + ??? + ????
  - compute_effective_stop_loss(): ?????????????
  - compute_effective_take_profit(): ?????????????
  - cost_guard(): ???????????

Inserted as a LangGraph node between decision and execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

from core.state.agent_state import AgentState

logger = logging.getLogger(__name__)


@dataclass
class SlippageConfig:
    base_slippage_buy:        float = 0.002   # 0.2% base buy slippage
    base_slippage_sell:       float = 0.002   # 0.2% base sell slippage
    degraded_extra_slippage:  float = 0.003   # +0.3% when data source degraded
    immediate_extra_slippage: float = 0.001   # +0.1% for urgent orders
    level2_slippage_discount: float = 0.50    # 50% discount when Level-2 available
    low_volume_multiplier:    float = 2.0     # x2 slippage for illiquid stocks
    low_volume_threshold:     int   = 5_000   # lots threshold for illiquidity


_DEFAULT_CFG = SlippageConfig()


def _has_level2() -> bool:
    """Detect whether a Level-2 feed SDK is installed."""
    for mod in ("ths_l2", "WindPy", "tqsdk"):
        try:
            __import__(mod)
            return True
        except ImportError:
            continue
    return False


def estimate_slippage(
    action:      str,
    symbol:      str,
    base_price:  float,
    is_degraded: bool          = False,
    urgency:     str           = "normal",
    volume_hand: int           = 0,
    cfg:         SlippageConfig = _DEFAULT_CFG,
) -> Dict:
    """
    Estimate slippage for a single order and return adjusted price.

    Returns:
        adjusted_price, slippage_pct, slippage_cost, has_level2, notes
    """
    if base_price <= 0:
        return {"adjusted_price": base_price, "slippage_pct": 0.0,
                "slippage_cost": 0.0, "has_level2": False, "notes": []}

    notes: List[str] = []
    is_buy   = action.lower() == "buy"
    slippage = cfg.base_slippage_buy if is_buy else cfg.base_slippage_sell

    if is_degraded:
        slippage += cfg.degraded_extra_slippage
        notes.append(f"degraded source +{cfg.degraded_extra_slippage:.2%}")

    if urgency == "immediate":
        slippage += cfg.immediate_extra_slippage
        notes.append(f"urgent +{cfg.immediate_extra_slippage:.2%}")
    elif urgency == "passive":
        slippage = max(0.0, slippage - 0.001)
        notes.append("passive order -0.10%")

    l2 = _has_level2()
    if l2:
        slippage *= (1.0 - cfg.level2_slippage_discount)
        notes.append("Level-2 available, slippage halved")
    else:
        notes.append("free feed (pytdx/akshare); consider Level-2 for tighter fills")

    if 0 < volume_hand < cfg.low_volume_threshold:
        slippage *= cfg.low_volume_multiplier
        notes.append(f"illiquid ({volume_hand} lots) x{cfg.low_volume_multiplier}")

    adjusted = base_price * (1 + slippage) if is_buy else base_price * (1 - slippage)
    adjusted = round(adjusted, 2)  # A-share tick = 0.01 CNY

    logger.debug(
        "[Slippage] %s %s ref=%.2f adj=%.2f slip=%.3f%%",
        action, symbol, base_price, adjusted, slippage * 100,
    )
    return {
        "adjusted_price": adjusted,
        "slippage_pct":   round(slippage, 6),
        "slippage_cost":  round(abs(adjusted - base_price), 4),
        "has_level2":     l2,
        "notes":          notes,
    }


def estimate_commission(
    action: str,
    price: float,
    quantity: int,
    cfg: SlippageConfig = _DEFAULT_CFG,
) -> Dict:
    """
    ?????????????

    Returns:
        commission_pct, commission_amount
    """
    amount = price * quantity
    if amount <= 0:
        return {"commission_pct": 0.0, "commission_amount": 0.0}

    rate = cfg.commission_buy if action.lower() == "buy" else cfg.commission_sell
    commission = max(amount * rate, cfg.min_commission)
    return {
        "commission_pct":    round(commission / amount, 6),
        "commission_amount": round(commission, 2),
    }


def estimate_round_trip_cost(
    buy_price:   float,
    sell_price:  float,
    quantity:    int,
    cfg:         SlippageConfig = _DEFAULT_CFG,
    buy_degraded:  bool = False,
    sell_degraded: bool = False,
) -> Dict:
    """
    ????????????????? + ??? + ?????

    Returns:
        total_cost_pct  : ?????????????
        total_cost_amount: ????????
        breakdown       : ??????
    """
    # ????
    buy_slip = estimate_slippage(
        action="buy", symbol="", base_price=buy_price,
        is_degraded=buy_degraded, cfg=cfg,
    )
    # ????
    sell_slip = estimate_slippage(
        action="sell", symbol="", base_price=sell_price,
        is_degraded=sell_degraded, cfg=cfg,
    )
    # ???
    buy_comm  = estimate_commission("buy",  buy_price,  quantity, cfg)
    sell_comm = estimate_commission("sell", sell_price, quantity, cfg)

    total_cost = (
        buy_slip["slippage_cost"]  * quantity
        + sell_slip["slippage_cost"] * quantity
        + buy_comm["commission_amount"]
        + sell_comm["commission_amount"]
    )
    base_amount = buy_price * quantity if buy_price > 0 else 1
    return {
        "total_cost_pct":    round(total_cost / base_amount, 6),
        "total_cost_amount": round(total_cost, 2),
        "breakdown": {
            "buy_slippage_pct":   buy_slip["slippage_pct"],
            "sell_slippage_pct":  sell_slip["slippage_pct"],
            "buy_commission_pct": buy_comm["commission_pct"],
            "sell_commission_pct":sell_comm["commission_pct"],
        },
    }


def compute_effective_stop_loss(
    entry_price:     float,
    raw_stop_pct:    float,
    quantity:        int    = 100,
    cfg:             SlippageConfig = _DEFAULT_CFG,
) -> Dict:
    """
    ??????????????

    ????? = ??? * (1 - ????) + ?????/????
    ???????? = raw_stop_pct?????????

    Returns:
        effective_stop_price : ?????????
        effective_stop_pct   : ???????????? raw ???
        cost_adjustment      : ???????/??
    """
    if entry_price <= 0:
        return {
            "effective_stop_price": 0.0,
            "effective_stop_pct":   raw_stop_pct,
            "cost_adjustment":      0.0,
        }
    # ??????? + ??????????
    buy_comm = estimate_commission("buy", entry_price, quantity, cfg)
    buy_slip = estimate_slippage("buy", "", entry_price, cfg=cfg)
    cost_per_share = (
        buy_comm["commission_amount"] / max(quantity, 1)
        + buy_slip["slippage_cost"]
    )
    # ???????????????
    raw_stop_price = entry_price * (1 - raw_stop_pct)
    effective_stop_price = raw_stop_price + cost_per_share
    effective_stop_price = min(effective_stop_price, entry_price * 0.99)  # ??? -1%
    effective_stop_pct   = (entry_price - effective_stop_price) / entry_price

    logger.debug(
        "[Cost] ?????: entry=%.2f raw_stop=%.2%% eff_stop=%.2f (%.2%%)",
        entry_price, raw_stop_pct, effective_stop_price, effective_stop_pct,
    )
    return {
        "effective_stop_price": round(effective_stop_price, 2),
        "effective_stop_pct":   round(effective_stop_pct, 6),
        "cost_adjustment":      round(cost_per_share, 4),
    }


def compute_effective_take_profit(
    entry_price:      float,
    raw_tp_pct:       float,
    quantity:         int    = 100,
    cfg:              SlippageConfig = _DEFAULT_CFG,
) -> Dict:
    """
    ??????????????

    ????? = ??? * (1 + ????) + ?????/??
    ???????? = raw_tp_pct?

    Returns:
        effective_tp_price : ?????????
        effective_tp_pct   : ???????????? raw ???
        cost_adjustment    : ???????/??
    """
    if entry_price <= 0:
        return {
            "effective_tp_price": 0.0,
            "effective_tp_pct":   raw_tp_pct,
            "cost_adjustment":    0.0,
        }
    buy_comm  = estimate_commission("buy",  entry_price, quantity, cfg)
    sell_comm = estimate_commission("sell", entry_price, quantity, cfg)
    buy_slip  = estimate_slippage("buy",  "", entry_price, cfg=cfg)
    sell_slip = estimate_slippage("sell", "", entry_price, cfg=cfg)

    cost_per_share = (
        (buy_comm["commission_amount"] + sell_comm["commission_amount"]) / max(quantity, 1)
        + buy_slip["slippage_cost"]
        + sell_slip["slippage_cost"]
    )
    raw_tp_price       = entry_price * (1 + raw_tp_pct)
    effective_tp_price = raw_tp_price + cost_per_share
    effective_tp_pct   = (effective_tp_price - entry_price) / entry_price

    return {
        "effective_tp_price": round(effective_tp_price, 2),
        "effective_tp_pct":   round(effective_tp_pct, 6),
        "cost_adjustment":    round(cost_per_share, 4),
    }


def cost_guard(
    action:      str,
    price:       float,
    quantity:    int,
    cfg:         SlippageConfig = _DEFAULT_CFG,
) -> bool:
    """
    ???????????????????? False???????
    ??????????????????????
    """
    amount = price * quantity
    if amount <= 0:
        return False
    # ????????
    buy_comm  = cfg.commission_buy
    sell_comm = cfg.commission_sell
    slip_total = cfg.base_slippage_buy + cfg.base_slippage_sell
    round_trip_pct = buy_comm + sell_comm + slip_total
    # ??????????????? / ????
    min_comm_impact = (cfg.min_commission * 2) / max(amount, 1)
    effective_pct = max(round_trip_pct, min_comm_impact)

    if effective_pct > cfg.max_round_trip_cost_pct:
        logger.warning(
            "[CostGuard] ???? %s %s�%d: ???? %.2%% > ?? %.2%%",
            action, str(price), quantity, effective_pct, cfg.max_round_trip_cost_pct,
        )
        return False
    return True


async def slippage_adapter_node(state: AgentState) -> AgentState:
    """
    LangGraph node: inject slippage estimates between decision and execution.

    Reads:  state["decisions"], state["data_quality_reports"]
    Writes: state["decisions"] (price adjusted),
            state["slippage_report"], state["logs"]
    """
    decisions = state.get("decisions", [])
    if not decisions:
        return {**state, "logs": ["[Slippage] no decisions, skip"]}

    dq_reports = state.get("data_quality_reports", [])
    degraded_set = {
        r["symbol"]
        for r in dq_reports
        if r.get("quality_level") == "degraded"
    }

    portfolio = state.get("portfolio", {})
    positions = portfolio.get("positions", {})

    adjusted_decisions: List[Dict] = []
    slippage_report:    List[Dict] = []

    for d in decisions:
        sym    = d.get("symbol", "")
        action = d.get("action", "hold")
        if action == "hold":
            adjusted_decisions.append(d)
            continue

        base_price  = d.get("price_limit") or positions.get(sym, {}).get("current_price", 0)
        volume_hand = int(positions.get(sym, {}).get("volume", 0) / 100)

        est = estimate_slippage(
            action=action,
            symbol=sym,
            base_price=float(base_price or 0),
            is_degraded=(sym in degraded_set),
            urgency=d.get("urgency", "normal"),
            volume_hand=volume_hand,
        )

        new_d = dict(d)
        if base_price and float(base_price) > 0:
            bp  = float(base_price)
            qty = int(d.get("quantity", 100))
            new_d["price_limit"]    = est["adjusted_price"]
            new_d["slippage_pct"]   = est["slippage_pct"]
            new_d["slippage_cost"]  = est["slippage_cost"]
            new_d["slippage_notes"] = est["notes"]

            # 含成本的止损止盈价
            raw_sl = d.get("stop_loss_pct", 0.07)
            raw_tp = d.get("take_profit_pct", 0.20)
            eff_sl = compute_effective_stop_loss(bp, raw_sl, qty)
            eff_tp = compute_effective_take_profit(bp, raw_tp, qty)
            new_d["effective_stop_loss_price"]   = eff_sl["effective_stop_price"]
            new_d["effective_stop_loss_pct"]     = eff_sl["effective_stop_pct"]
            new_d["effective_take_profit_price"] = eff_tp["effective_tp_price"]
            new_d["effective_take_profit_pct"]   = eff_tp["effective_tp_pct"]
            new_d["cost_adjustment_per_share"]   = eff_sl["cost_adjustment"]

            # 成本门卫：往返成本过高则降级为 hold
            if not cost_guard(action, bp, qty):
                new_d["action"] = "hold"
                new_d["cost_guard_rejected"] = True

        adjusted_decisions.append(new_d)
        slippage_report.append({
            "symbol":         sym,
            "action":         action,
            "base_price":     base_price,
            "adjusted_price": est["adjusted_price"],
            "slippage_pct":   est["slippage_pct"],
            "has_level2":     est["has_level2"],
            "notes":          est["notes"],
        })

    log_msg = (
        f"[Slippage] done: {len(adjusted_decisions)} decisions, "
        f"{len(degraded_set)} degraded symbols with extra slippage"
    )
    logger.info(log_msg)

    return {
        **state,
        "decisions":       adjusted_decisions,
        "slippage_report": slippage_report,
        "logs":            [log_msg],
    }
