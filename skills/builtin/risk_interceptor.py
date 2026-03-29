"""
Skill: 风险拦截 (RiskInterceptor)

功能：
  - 监测系统风险等级和风险预警
  - 风险等级 high/extreme 时对买入信号施加一票否决
  - 触及止损线的持仓主动生成卖出建议
  - 最大回撤超阈值时建议防御
"""
from __future__ import annotations

from typing import Dict

from skills.base import SkillBase, SkillResult


class RiskInterceptorSkill(SkillBase):
    skill_id    = "risk_interceptor"
    name        = "风险拦截"
    description = "在高风险/极端风险环境下拦截新买入，触及止损线时强制卖出建议"
    category    = "risk_control"
    priority    = 5

    MAX_DRAWDOWN_WARN = 0.08
    MAX_DRAWDOWN_VETO = 0.15

    def is_applicable(self, state: Dict) -> bool:
        risk = state.get("risk_level", "low")
        return risk in ("high", "extreme") or bool(state.get("risk_flags"))

    def run(self, state: Dict) -> SkillResult:
        risk_level = state.get("risk_level", "low")
        risk_flags = state.get("risk_flags", [])
        portfolio  = state.get("portfolio", {})
        drawdown   = portfolio.get("max_drawdown", 0)
        positions  = portfolio.get("positions", {})

        veto        = False
        veto_reason = ""
        advice_parts = []
        signal_adj: Dict = {}

        # 极端风险：一票否决所有新买入
        if risk_level == "extreme" or drawdown >= self.MAX_DRAWDOWN_VETO:
            veto        = True
            veto_reason = (
                f"风险等级={risk_level.upper()}，最大回撤={drawdown:.1%}，"
                "一票否决所有新买入指令"
            )
            advice_parts.append(veto_reason)
        elif risk_level == "high" or drawdown >= self.MAX_DRAWDOWN_WARN:
            advice_parts.append(
                f"风险偏高（{risk_level}/回撤{drawdown:.1%}），压缩新仓买入强度"
            )
            # 降低所有 buy 方向信号评分
            for sym in positions:
                signal_adj[sym] = {"score_delta": -0.10}

        # 止损预警：距止损价 ≤2% 的持仓标记降权
        for sym, pos in positions.items():
            stop  = pos.get("stop_loss", 0)
            price = pos.get("current_price", 0)
            if stop and price and price > 0:
                gap = (price - stop) / price
                if 0 <= gap <= 0.02:
                    advice_parts.append(
                        f"{sym} 距止损价仅 {gap:.1%}，建议减仓或止损"
                    )
                    signal_adj[sym] = signal_adj.get(sym, {})
                    signal_adj[sym]["direction_override"] = "bearish"

        if risk_flags:
            advice_parts.append(f"活跃风险预警 {len(risk_flags)} 条")

        triggered = bool(advice_parts)
        return SkillResult(
            skill_id=self.skill_id,
            skill_name=self.name,
            triggered=triggered,
            advice=" | ".join(advice_parts) if advice_parts else "风险正常，无需干预",
            signal_adjustments=signal_adj,
            veto=veto,
            veto_reason=veto_reason,
            metadata={
                "risk_level": risk_level,
                "drawdown": drawdown,
                "flags_count": len(risk_flags),
            },
            confidence=0.95,
        )
