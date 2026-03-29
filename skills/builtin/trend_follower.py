"""
Skill: 趋势跟随 (TrendFollower)

功能：
  - 检测大盘趋势（上涨/下跌/震荡）
  - 趋势明确时，对技术面信号进行权重加成
  - 逆趋势信号自动降权（不否决，仅削弱）
  - 极端趋势（涨跌幅 > 3%）触发仓位上限缩减建议
"""
from __future__ import annotations

from typing import Dict

from skills.base import SkillBase, SkillResult


class TrendFollowerSkill(SkillBase):
    skill_id    = "trend_follower"
    name        = "趋势跟随"
    description = "识别大盘趋势方向，顺势加权技术信号，逆势降权，极端行情收缩仓位上限"
    category    = "market_analysis"
    priority    = 10

    # 阈值配置
    STRONG_TREND_PCT   = 1.5   # 大盘涨跌幅超过此值视为强趋势
    EXTREME_TREND_PCT  = 3.0   # 超过此值触发极端行情处理
    TECH_BOOST         = 0.08  # 顺势时技术面权重加成
    TECH_PENALTY       = 0.06  # 逆势时技术面权重削减

    def run(self, state: Dict) -> SkillResult:
        overview    = state.get("market_overview", {})
        sh          = overview.get("sh_index", {})
        change_pct  = sh.get("change_pct", 0)

        # ── 判断趋势方向 ──────────────────────────────────────────────
        if change_pct > self.STRONG_TREND_PCT:
            trend = "bullish"
        elif change_pct < -self.STRONG_TREND_PCT:
            trend = "bearish"
        else:
            trend = "neutral"

        extreme = abs(change_pct) > self.EXTREME_TREND_PCT

        if trend == "neutral" and not extreme:
            return SkillResult(
                skill_id=self.skill_id,
                skill_name=self.name,
                triggered=False,
                advice="大盘震荡，趋势跟随技能未触发",
                confidence=0.6,
            )

        # ── 构建权重调整 ──────────────────────────────────────────────
        weight_adj: Dict[str, float] = {}
        signal_adj: Dict[str, Dict]  = {}
        veto        = False
        veto_reason = ""
        advice_parts = []

        if trend == "bullish":
            weight_adj["technical"] = +self.TECH_BOOST
            advice_parts.append(
                f"大盘强势上涨 {change_pct:+.2f}%，顺势加权技术面 +{self.TECH_BOOST:.0%}"
            )
            # 看空信号降权
            signals = state.get("signals", [])
            for sig in signals:
                if sig.get("direction") == "bearish" and sig.get("dimension") == "technical":
                    sym = sig.get("symbol", "")
                    signal_adj[sym] = signal_adj.get(sym, {})
                    signal_adj[sym]["score_delta"] = signal_adj[sym].get("score_delta", 0) - 0.05

        elif trend == "bearish":
            weight_adj["technical"] = -self.TECH_PENALTY
            weight_adj["fundamental"] = +self.TECH_PENALTY  # 熊市基本面防御
            advice_parts.append(
                f"大盘弱势下跌 {change_pct:+.2f}%，降权技术面，提升基本面防御"
            )

        if extreme:
            advice_parts.append(
                f"极端行情（{change_pct:+.2f}%），建议单票仓位上限收缩至 5%"
            )

        return SkillResult(
            skill_id=self.skill_id,
            skill_name=self.name,
            triggered=True,
            advice=" | ".join(advice_parts),
            weight_adjustments=weight_adj,
            signal_adjustments=signal_adj,
            veto=veto,
            veto_reason=veto_reason,
            metadata={
                "trend": trend,
                "change_pct": change_pct,
                "extreme": extreme,
            },
            confidence=0.85,
        )
