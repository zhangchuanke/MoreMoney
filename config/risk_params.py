"""
风控参数配置
"""
from dataclasses import dataclass


@dataclass
class RiskParams:
    # === 仓位控制 ===
    MAX_SINGLE_POSITION_PCT: float = 0.20    # 单股最大仓位 20%
    MAX_SECTOR_CONCENTRATION_PCT: float = 0.40  # 单板块最大仓位 40%
    MAX_TOTAL_POSITION_PCT: float = 0.80     # 最大总仓位 80%

    # 按风险等级的总仓位上限
    POSITION_LIMIT_BY_RISK = {
        "low":     0.80,
        "medium":  0.60,
        "high":    0.40,
        "extreme": 0.20,
    }

    # === 止损止盈 ===
    DEFAULT_STOP_LOSS_PCT: float = 0.07      # 默认止损 7%
    DEFAULT_TAKE_PROFIT_PCT: float = 0.20    # 默认止盈 20%
    TRAILING_STOP_TRIGGER_PCT: float = 0.10  # 移动止损触发线 10%
    TRAILING_STOP_PCT: float = 0.05          # 移动止损幅度 5%

    # === 日内风控 ===
    MAX_DAILY_LOSS_PCT: float = 0.02         # 日内最大亏损 2%（触发停止交易）
    MAX_DAILY_TRADES: int = 20               # 每日最大交易次数

    # === 最大回撤 ===
    MAX_DRAWDOWN_LIMIT: float = 0.15         # 最大回撤熔断线 15%

    # === 市场熔断 ===
    MARKET_CIRCUIT_BREAKER_PCT: float = 5.0  # 大盘涨跌 5% 触发熔断

    # === 单笔交易 ===
    MIN_ORDER_AMOUNT: float = 10_000         # 最小单笔金额
    MAX_ORDER_AMOUNT: float = 200_000        # 最大单笔金额
    MIN_SIGNAL_SCORE: float = 0.30           # 最低信号综合评分才建仓
