"""
LangGraph 数据质量校验节点

插入位置：scanner → data_quality → (technical / sentiment / capital_flow / fundamental)

职责：
  1. 对 target_symbols 批量执行双源数据质量校验
  2. 将不可交易的标的从 target_symbols 中移除
  3. 降级标的写入 degraded_symbols，供下游节点调整仓位
  4. 质量报告写入 state["data_quality_reports"]
  5. 全部标的均暂停时触发 circuit_breaker
"""

from __future__ import annotations

import logging
from typing import Dict, List

from core.state.agent_state import AgentState
from data_quality.data_validator import (
    DataQualityLevel,
    DataQualityResult,
    DataQualityValidator,
)

logger = logging.getLogger(__name__)

_validator = DataQualityValidator()  # 模块级单例，缓存最优 TDX 服务器


async def data_quality_node(state: AgentState) -> AgentState:
    """
    LangGraph 异步节点：数据质量校验。

    读取  state["target_symbols"]
    写入  state["target_symbols"]        — 移除暂停标的
          state["degraded_symbols"]      — 降级标的列表（新字段）
          state["data_quality_reports"]  — 完整质量报告（新字段）
          state["circuit_breaker_triggered"] — 全部暂停时置 True
          state["risk_flags"]            — 追加质量异常告警
          state["logs"]                  — 追加运行日志
    """
    symbols: List[str] = state.get("target_symbols", [])
    if not symbols:
        return {
            **state,
            "logs": ["[DataQuality] target_symbols 为空，跳过校验"],
        }

    market_date: str = state.get("market_date", "")
    date_arg = market_date if market_date else None

    logger.info("[DataQuality] 开始校验 %d 个标的", len(symbols))
    results: Dict[str, DataQualityResult] = _validator.validate_batch(
        symbols, date=date_arg
    )

    tradable, suspended = _validator.filter_tradable(results)
    degraded = [
        s for s, r in results.items()
        if r.quality_level == DataQualityLevel.DEGRADED
    ]

    # 序列化质量报告（不存 DataFrame，只存摘要）
    quality_reports = [
        {
            "symbol":          sym,
            "quality_level":   r.quality_level.value,
            "active_source":   r.active_source.value,
            "price_deviation": round(r.price_deviation, 6),
            "volume_deviation": round(r.volume_deviation, 6),
            "anomalies":       r.anomalies,
            "recommendation":  r.recommendation,
            "position_ratio":  r.position_ratio,
        }
        for sym, r in results.items()
    ]

    # 构建风险预警消息
    risk_flags: List[str] = []
    for sym in suspended:
        risk_flags.append(f"[DataQuality] {sym} 双源数据均异常，暂停交易")
    for sym in degraded:
        r = results[sym]
        risk_flags.append(
            f"[DataQuality] {sym} 数据降级({r.active_source.value})，"
            f"建议仓位×{r.position_ratio}"
        )

    # 全部标的暂停时触发熔断
    all_suspended = len(tradable) == 0 and len(symbols) > 0
    if all_suspended:
        logger.error(
            "[DataQuality] 全部 %d 个标的数据质量不合格，触发熔断",
            len(symbols),
        )
        risk_flags.append("[DataQuality] 全部标的数据质量异常，触发熔断保护")

    log_msg = (
        f"[DataQuality] 校验完成：{len(tradable)} 可交易 "
        f"/ {len(degraded)} 降级 "
        f"/ {len(suspended)} 暂停 "
        f"（共 {len(symbols)} 个标的）"
    )
    logger.info(log_msg)

    return {
        **state,
        "target_symbols":          tradable,
        "degraded_symbols":        degraded,
        "data_quality_reports":    quality_reports,
        "circuit_breaker_triggered": state.get("circuit_breaker_triggered", False)
                                      or all_suspended,
        "risk_flags":              risk_flags,
        "logs":                    [log_msg],
    }
