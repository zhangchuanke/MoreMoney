"""
动态仓位调整模块

根据账户净值、市场波动率动态调整仓位上限和止损止盈阈值，
替代 RiskParams 中的固定静态值，实现自适应风控。

调整逻辑：
  波动率越高 -> 仓位上限收缩、止损收窄
  净值回撤越大 -> 仓位上限进一步压缩
  净值新高 -> 逐步恢复满仓能力
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from config.risk_params import RiskParams

logger = logging.getLogger("risk.dynamic_position")


@dataclass
class DynamicPositionResult:
    """动态计算后的仓位/止损止盈参数快照。"""
    max_single_position_pct: float
    max_sector_pct: float
    max_total_position_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    vol_multiplier: float
    drawdown_multiplier: float
    effective_risk_level: str

    def as_dict(self) -> Dict:
        return {
            "max_single_position_pct":  self.max_single_position_pct,
            "max_sector_pct":           self.max_sector_pct,
            "max_total_position_pct":   self.max_total_position_pct,
            "stop_loss_pct":            self.stop_loss_pct,
            "take_profit_pct":          self.take_profit_pct,
            "trailing_stop_pct":        self.trailing_stop_pct,
            "vol_multiplier":           self.vol_multiplier,
            "drawdown_multiplier":      self.drawdown_multiplier,
            "effective_risk_level":     self.effective_risk_level,
        }


class DynamicPositionManager:
    """
    动态仓位管理器。

    用法::

        mgr = DynamicPositionManager()
        result = mgr.compute(
            current_nav=1_050_000,
            peak_nav=1_100_000,
            vix=28.0,
            sh_amplitude=0.03,
            risk_level="high",
        )
        # 使用 result.max_single_position_pct 替代固定参数
    """

    _VIX_LOW     = 15.0
    _VIX_MEDIUM  = 25.0
    _VIX_HIGH    = 35.0
    _VIX_EXTREME = 50.0

    def __init__(self, params: Optional[RiskParams] = None):
        self.params = params or RiskParams()

    def compute(
        self,
        current_nav: float,
        peak_nav: float,
        vix: float = 20.0,
        sh_amplitude: float = 0.0,
        risk_level: str = "medium",
    ) -> DynamicPositionResult:
        """
        计算动态仓位与止损止盈参数。

        Parameters
        ----------
        current_nav   : 当前账户净值（元）
        peak_nav      : 历史峰值净值（元）
        vix           : 市场恐慌指数（A 股用大盘振幅/成交量偏离度近似）
        sh_amplitude  : 当日上证振幅（小数，如 0.03 = 3%）
        risk_level    : 当前 RiskAgent 评级
        """
        p = self.params

        # ── 1. 波动率调整系数 ──────────────────────────────────────────
        # 综合 VIX 与上证振幅取较大威胁
        eff_vix = max(vix, sh_amplitude * 100 * 5)  # 振幅转换为等效VIX
        vol_multiplier = self._vol_multiplier(eff_vix)

        # ── 2. 回撤调整系数 ───────────────────────────────────────────
        drawdown = 0.0
        if peak_nav > 0 and current_nav < peak_nav:
            drawdown = (peak_nav - current_nav) / peak_nav
        drawdown_multiplier = self._drawdown_multiplier(drawdown)

        # ── 3. 风险等级硬约束系数 ─────────────────────────────────────
        risk_cap = p.POSITION_LIMIT_BY_RISK.get(risk_level, 0.60)

        # ── 4. 综合仓位上限 ───────────────────────────────────────────
        combined = vol_multiplier * drawdown_multiplier

        max_total = min(
            p.MAX_TOTAL_POSITION_PCT * combined,
            risk_cap,
        )
        max_single = p.MAX_SINGLE_POSITION_PCT * combined
        max_sector = p.MAX_SECTOR_CONCENTRATION_PCT * combined

        # 下限保护：至少允许 5% 仓位（否则仓位为零无意义）
        max_total  = max(max_total, 0.05)
        max_single = max(max_single, 0.05)
        max_sector = max(max_sector, 0.10)

        # ── 5. 动态止损止盈 ───────────────────────────────────────────
        # 波动率高时止损收窄（亏损更快），止盈同步收窄（落袋为安）
        stop_loss_pct    = p.DEFAULT_STOP_LOSS_PCT * (2.0 - vol_multiplier)
        take_profit_pct  = p.DEFAULT_TAKE_PROFIT_PCT * vol_multiplier
        trailing_stop_pct = p.TRAILING_STOP_PCT * (2.0 - vol_multiplier)

        # 止损不能小于 2%，不能大于 12%
        stop_loss_pct = max(0.02, min(0.12, stop_loss_pct))
        # 止盈不能小于 8%
        take_profit_pct = max(0.08, take_profit_pct)
        trailing_stop_pct = max(0.02, min(0.08, trailing_stop_pct))

        # ── 6. 综合风险等级 ───────────────────────────────────────────
        effective_risk = self._effective_risk(
            vol_multiplier, drawdown_multiplier, risk_level
        )

        result = DynamicPositionResult(
            max_single_position_pct=round(max_single, 4),
            max_sector_pct=round(max_sector, 4),
            max_total_position_pct=round(max_total, 4),
            stop_loss_pct=round(stop_loss_pct, 4),
            take_profit_pct=round(take_profit_pct, 4),
            trailing_stop_pct=round(trailing_stop_pct, 4),
            vol_multiplier=round(vol_multiplier, 4),
            drawdown_multiplier=round(drawdown_multiplier, 4),
            effective_risk_level=effective_risk,
        )

        logger.info(
            "[DynamicPosition] VIX=%.1f 振幅=%.2%% 回撤=%.2%% -> "
            "单股上限=%.2%% 总仓=%.2%% 止损=%.2%%",
            eff_vix, sh_amplitude, drawdown,
            result.max_single_position_pct,
            result.max_total_position_pct,
            result.stop_loss_pct,
        )
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _vol_multiplier(self, vix: float) -> float:
        """将 VIX 映射到 [0.30, 1.0] 的仓位系数。"""
        if vix <= self._VIX_LOW:
            return 1.0
        if vix <= self._VIX_MEDIUM:
            # 线性插值 [15, 25] -> [1.0, 0.75]
            t = (vix - self._VIX_LOW) / (self._VIX_MEDIUM - self._VIX_LOW)
            return 1.0 - 0.25 * t
        if vix <= self._VIX_HIGH:
            # [25, 35] -> [0.75, 0.50]
            t = (vix - self._VIX_MEDIUM) / (self._VIX_HIGH - self._VIX_MEDIUM)
            return 0.75 - 0.25 * t
        if vix <= self._VIX_EXTREME:
            # [35, 50] -> [0.50, 0.30]
            t = (vix - self._VIX_HIGH) / (self._VIX_EXTREME - self._VIX_HIGH)
            return 0.50 - 0.20 * t
        return 0.30

    def _drawdown_multiplier(self, drawdown: float) -> float:
        """将当前回撤映射到 [0.30, 1.0] 的仓位系数。"""
        if drawdown <= 0.05:
            return 1.0
        if drawdown <= 0.10:
            t = (drawdown - 0.05) / 0.05
            return 1.0 - 0.25 * t
        if drawdown <= 0.15:
            t = (drawdown - 0.10) / 0.05
            return 0.75 - 0.25 * t
        if drawdown <= 0.20:
            t = (drawdown - 0.15) / 0.05
            return 0.50 - 0.20 * t
        return 0.30

    def _effective_risk(
        self,
        vol_mult: float,
        dd_mult: float,
        base_level: str,
    ) -> str:
        """综合波动率系数与回撤系数确定有效风险等级。"""
        combined = vol_mult * dd_mult
        if combined < 0.35:
            return "extreme"
        if combined < 0.55:
            return "high"
        if combined < 0.80:
            return "medium"
        # 以 base_level 为下限
        order = ["low", "medium", "high", "extreme"]
        base_idx = order.index(base_level) if base_level in order else 1
        low_idx = order.index("low")
        return order[max(base_idx, low_idx)]
