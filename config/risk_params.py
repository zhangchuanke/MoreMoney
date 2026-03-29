"""
风控参数配置（全维度升级版）

新增参数分组：
  - 流动性风控：LIQUIDITY_*
  - 个股熔断：CIRCUIT_BREAKER_*
  - 手续费/滑点成本：COST_*
  - 动态仓位基准：DYNAMIC_POSITION_*
  - 对手盘监控：COUNTERPARTY_*
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RiskParams:
    # ================================================================
    # 仓位控制（静态基准，运行时由 DynamicPositionManager 动态调整）
    # ================================================================
    MAX_SINGLE_POSITION_PCT: float = 0.20
    MAX_SECTOR_CONCENTRATION_PCT: float = 0.40
    MAX_TOTAL_POSITION_PCT: float = 0.80

    POSITION_LIMIT_BY_RISK: Dict[str, float] = field(default_factory=lambda: {
        "low":     0.80,
        "medium":  0.60,
        "high":    0.40,
        "extreme": 0.20,
    })

    # ================================================================
    # 止损止盈（静态基准，运行时由 DynamicPositionManager 动态调整）
    # ================================================================
    DEFAULT_STOP_LOSS_PCT: float = 0.07
    DEFAULT_TAKE_PROFIT_PCT: float = 0.20
    TRAILING_STOP_TRIGGER_PCT: float = 0.10
    TRAILING_STOP_PCT: float = 0.05

    # ================================================================
    # 日内风控
    # ================================================================
    MAX_DAILY_LOSS_PCT: float = 0.02
    MAX_DAILY_TRADES: int = 20

    # ================================================================
    # 最大回撤
    # ================================================================
    MAX_DRAWDOWN_LIMIT: float = 0.15

    # ================================================================
    # 市场熔断
    # ================================================================
    MARKET_CIRCUIT_BREAKER_PCT: float = 5.0

    # ================================================================
    # 单笔交易
    # ================================================================
    MIN_ORDER_AMOUNT: float = 10_000
    MAX_ORDER_AMOUNT: float = 200_000
    MIN_SIGNAL_SCORE: float = 0.30

    # ================================================================
    # 前置流动性风控（新增）
    # ================================================================
    # 日均成交额下限（元）—— 低于此值的标的在选股阶段直接剔除
    LIQUIDITY_MIN_DAILY_AMOUNT: float = 50_000_000.0    # 5000 万
    # 流通市值下限（元）
    LIQUIDITY_MIN_FLOAT_CAP: float = 5e8                # 5 亿
    # 换手率下限（%），0 = 不启用
    LIQUIDITY_MIN_TURNOVER_RATE: float = 0.0

    # ================================================================
    # 个股极端波动熔断（新增）
    # ================================================================
    # 单日振幅超过此值暂停新开仓（振幅 = (最高-最低)/昨收）
    CIRCUIT_BREAKER_AMPLITUDE: float = 0.15             # 15%
    # 连续涨停板超过此数禁止追涨
    CIRCUIT_BREAKER_MAX_LIMIT_UP: int = 3
    # 盘中 N 分钟快速拉升/砸盘阈值
    CIRCUIT_BREAKER_INTRADAY_PCT: float = 0.05          # 5%
    CIRCUIT_BREAKER_INTRADAY_MINUTES: int = 5
    # 触发后冷静期（秒）
    CIRCUIT_BREAKER_COOLDOWN_SEC: int = 1800            # 30 分钟

    # ================================================================
    # 交易成本（新增）—— 用于止损止盈实际成本计算
    # ================================================================
    # A 股交易手续费（双边）：买入 0.03%，卖出 0.13%（含印花税 0.1%）
    COST_BUY_COMMISSION_PCT: float = 0.0003             # 0.03%
    COST_SELL_COMMISSION_PCT: float = 0.0013            # 0.13%（含印花税）
    # 最低手续费（元/笔）
    COST_MIN_COMMISSION: float = 5.0
    # 默认滑点（单边）
    COST_DEFAULT_SLIPPAGE_PCT: float = 0.002            # 0.2%
    # 综合单边交易成本上限（超出时拒绝小额交易）
    COST_MAX_ROUND_TRIP_PCT: float = 0.02               # 2%（双边往返不超过 2%）

    # ================================================================
    # 动态仓位调整基准参数（新增）
    # ================================================================
    # 波动率参考基准（等效 VIX）
    DYNAMIC_VIX_LOW: float = 15.0
    DYNAMIC_VIX_MEDIUM: float = 25.0
    DYNAMIC_VIX_HIGH: float = 35.0
    DYNAMIC_VIX_EXTREME: float = 50.0
    # 是否启用动态仓位调整
    DYNAMIC_POSITION_ENABLED: bool = True

    # ================================================================
    # 对手盘风险监控（新增）
    # ================================================================
    # 北向资金单日净流出阈值（亿元）
    COUNTERPARTY_NB_MARKET_THRESHOLD: float = -30.0
    # 个股北向净卖出阈值（万元）
    COUNTERPARTY_NB_STOCK_THRESHOLD: float = -5000.0
    # 主力大单净流出阈值（万元）
    COUNTERPARTY_BLOCK_THRESHOLD: float = -3000.0
    # 连续北向净流出天数触发防御模式
    COUNTERPARTY_CONSECUTIVE_DAYS: int = 3
    # 防御模式下是否完全禁止买入
    COUNTERPARTY_DEFENSE_BLOCK_BUY: bool = False
