"""
市场风格识别模块

在每轮 market_scanner 之后运行，输出五类市场风格标签及对应的基准权重矩阵。

五类风格：
  bull        - 牛市趋势（指数持续上涨、成交量放大、北上加速流入）
  bear        - 熊市趋势（指数持续下跌、成交量萎缩、恐慌情绪蔓延）
  volatile    - 震荡行情（指数区间震荡、个股分化、缺乏主线）
  theme       - 题材炒作行情（概念板块轮动快、涨跌停效应强、消息面驱动）
  value       - 价值行情（低估值蓝筹占优、基本面驱动、外资偏好）

优先级权重矩阵（dimension_weights）：
  不同风格下四维信号权重不同，避免策略在全市场用同一套固定权重。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("core.market_regime")

# ---------------------------------------------------------------------------
# 各风格对应的基准权重
# ---------------------------------------------------------------------------
REGIME_BASE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "bull": {
        "technical":    0.35,
        "sentiment":    0.30,
        "capital_flow": 0.25,
        "fundamental":  0.10,
    },
    "bear": {
        "technical":    0.30,
        "sentiment":    0.15,
        "capital_flow": 0.20,
        "fundamental":  0.35,
    },
    "volatile": {
        "technical":    0.35,
        "sentiment":    0.20,
        "capital_flow": 0.25,
        "fundamental":  0.20,
    },
    "theme": {
        "technical":    0.20,
        "sentiment":    0.40,
        "capital_flow": 0.30,
        "fundamental":  0.10,
    },
    "value": {
        "technical":    0.20,
        "sentiment":    0.15,
        "capital_flow": 0.25,
        "fundamental":  0.40,
    },
}

# 默认（未知风格）
DEFAULT_WEIGHTS: Dict[str, float] = {
    "technical":    0.30,
    "sentiment":    0.25,
    "capital_flow": 0.25,
    "fundamental":  0.20,
}

# ---------------------------------------------------------------------------
# 一票否决场景：极端行情下风控强制优先
# ---------------------------------------------------------------------------
VETO_OVERRIDE_WEIGHTS: Dict[str, float] = {
    "technical":    0.15,
    "sentiment":    0.10,
    "capital_flow": 0.10,
    "fundamental":  0.15,
    # 剩余 0.50 实际由风控节点直接拦截，不走聚合器评分
}


@dataclass
class MarketRegimeResult:
    regime: str                                # 当前风格标签
    confidence: float                          # 识别置信度 0~1
    base_weights: Dict[str, float]             # 对应基准权重
    veto_active: bool = False                  # 是否触发极端行情一票否决
    signals: Dict[str, float] = field(default_factory=dict)  # 识别依据指标
    description: str = ""

    def effective_weights(self) -> Dict[str, float]:
        """返回实际生效权重（极端行情时切换为风控优先权重）"""
        if self.veto_active:
            return VETO_OVERRIDE_WEIGHTS
        return self.base_weights


class MarketRegimeDetector:
    """
    基于大盘指标的市场风格识别器。

    输入：market_overview（由 OrchestratorAgent.scan_market 产出）
    输出：MarketRegimeResult

    识别逻辑（规则引擎，不走 LLM，保证稳定性与速度）：
      1. 极端行情检测（优先级最高，一票否决）
      2. 趋势判断（牛/熊）
      3. 题材炒作强度判断
      4. 价值蓝筹强度判断
      5. 默认震荡
    """

    # 极端行情阈值
    EXTREME_CHANGE_PCT   = 3.5   # 大盘单日涨跌幅超过 ±3.5%
    EXTREME_VIX          = 40    # VIX 超过 40

    # 牛市判断阈值
    BULL_CHANGE_PCT      = 0.8   # 大盘涨幅超过 0.8%
    BULL_NORTHBOUND_FLOW = 50    # 北向净流入超过 50 亿
    BULL_LIMIT_UP_COUNT  = 60    # 涨停家数 > 60

    # 熊市判断阈值
    BEAR_CHANGE_PCT      = -0.8  # 大盘跌幅超过 -0.8%
    BEAR_LIMIT_DOWN_COUNT = 40   # 跌停家数 > 40

    # 题材炒作判断阈值
    THEME_LIMIT_UP_COUNT = 80    # 涨停家数 > 80（板块效应强）
    THEME_TURNOVER_RATIO = 1.2   # 换手率相对均值倍数 > 1.2

    # 价值行情判断阈值
    VALUE_PE_RATIO       = 12    # 沪深300 PE < 12（低估值主导）
    VALUE_NORTHBOUND_FLOW = 30   # 北向净流入 > 30 亿且题材热度低

    def detect(self, market_overview: Dict) -> MarketRegimeResult:
        """
        识别当前市场风格。

        Args:
            market_overview: OrchestratorAgent.scan_market 产出的大盘状态字典
                预期字段：
                  sh_index_change_pct  - 上证指数日涨跌幅
                  vix                  - 市场恐慌指数（或 A 股波动率替代）
                  northbound_flow_bn   - 北向资金净流入（亿元，正为流入）
                  limit_up_count       - 涨停家数
                  limit_down_count     - 跌停家数
                  market_turnover_ratio_vs_avg - 换手率 vs 近20日均值的倍数
                  csi300_pe            - 沪深300 PE
        Returns:
            MarketRegimeResult
        """
        ch   = market_overview.get("sh_index_change_pct", 0.0)
        vix  = market_overview.get("vix", 20)
        nb   = market_overview.get("northbound_flow_bn", 0.0)
        lu   = market_overview.get("limit_up_count", 0)
        ld   = market_overview.get("limit_down_count", 0)
        tr   = market_overview.get("market_turnover_ratio_vs_avg", 1.0)
        pe   = market_overview.get("csi300_pe", 15)

        raw_signals = {
            "sh_change_pct":        ch,
            "vix":                  vix,
            "northbound_flow_bn":   nb,
            "limit_up_count":       lu,
            "limit_down_count":     ld,
            "turnover_ratio_vs_avg": tr,
            "csi300_pe":            pe,
        }

        # ── 1. 极端行情一票否决 ──────────────────────────────────────────
        if abs(ch) >= self.EXTREME_CHANGE_PCT or vix >= self.EXTREME_VIX:
            logger.warning(
                "[MarketRegime] 极端行情触发一票否决: ch=%.2f%%, vix=%.1f", ch, vix
            )
            return MarketRegimeResult(
                regime="volatile",
                confidence=0.95,
                base_weights=REGIME_BASE_WEIGHTS["volatile"],
                veto_active=True,
                signals=raw_signals,
                description=f"极端行情（大盘{ch:+.2f}%，VIX={vix}），风控一票否决，暂停主动开仓",
            )

        # ── 2. 题材炒作判断（优先级高于牛熊，因为题材市中牛市信号也多）──
        if lu >= self.THEME_LIMIT_UP_COUNT and tr >= self.THEME_TURNOVER_RATIO:
            conf = min(1.0, (lu / 120 + tr / 2.0) / 2)
            logger.info("[MarketRegime] 识别为题材炒作行情: lu=%d, tr=%.2f", lu, tr)
            return MarketRegimeResult(
                regime="theme",
                confidence=round(conf, 3),
                base_weights=REGIME_BASE_WEIGHTS["theme"],
                signals=raw_signals,
                description=f"题材炒作（涨停{lu}家，换手率{tr:.1f}x均值），消息面/资金流优先",
            )

        # ── 3. 价值行情判断 ──────────────────────────────────────────────
        if pe <= self.VALUE_PE_RATIO and nb >= self.VALUE_NORTHBOUND_FLOW and lu < 50:
            conf = min(1.0, (self.VALUE_PE_RATIO - pe) / 5 * 0.5 + nb / 100 * 0.5)
            logger.info("[MarketRegime] 识别为价值行情: pe=%.1f, nb=%.1f亿", pe, nb)
            return MarketRegimeResult(
                regime="value",
                confidence=round(conf, 3),
                base_weights=REGIME_BASE_WEIGHTS["value"],
                signals=raw_signals,
                description=f"价值行情（沪深300 PE={pe:.1f}，北向净流入{nb:.1f}亿），基本面优先",
            )

        # ── 4. 牛市趋势 ──────────────────────────────────────────────────
        if ch >= self.BULL_CHANGE_PCT and (nb >= self.BULL_NORTHBOUND_FLOW or lu >= self.BULL_LIMIT_UP_COUNT):
            conf = min(1.0, ch / 3 * 0.5 + min(lu, 100) / 100 * 0.5)
            logger.info("[MarketRegime] 识别为牛市趋势: ch=%.2f%%, lu=%d", ch, lu)
            return MarketRegimeResult(
                regime="bull",
                confidence=round(conf, 3),
                base_weights=REGIME_BASE_WEIGHTS["bull"],
                signals=raw_signals,
                description=f"牛市趋势（大盘{ch:+.2f}%，涨停{lu}家），技术/情绪面优先",
            )

        # ── 5. 熊市趋势 ──────────────────────────────────────────────────
        if ch <= self.BEAR_CHANGE_PCT and ld >= self.BEAR_LIMIT_DOWN_COUNT:
            conf = min(1.0, abs(ch) / 3 * 0.5 + min(ld, 80) / 80 * 0.5)
            logger.info("[MarketRegime] 识别为熊市趋势: ch=%.2f%%, ld=%d", ch, ld)
            return MarketRegimeResult(
                regime="bear",
                confidence=round(conf, 3),
                base_weights=REGIME_BASE_WEIGHTS["bear"],
                signals=raw_signals,
                description=f"熊市趋势（大盘{ch:+.2f}%，跌停{ld}家），基本面/防御优先",
            )

        # ── 6. 默认：震荡 ─────────────────────────────────────────────────
        logger.info("[MarketRegime] 识别为震荡行情，使用均衡权重")
        return MarketRegimeResult(
            regime="volatile",
            confidence=0.60,
            base_weights=REGIME_BASE_WEIGHTS["volatile"],
            signals=raw_signals,
            description="震荡行情，均衡权重",
        )
