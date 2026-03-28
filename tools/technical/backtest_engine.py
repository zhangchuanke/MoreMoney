"""
回测引擎（用于自我迭代验证策略效果）
"""
import pandas as pd
from typing import Dict, List, Callable, Optional
from datetime import datetime


class BacktestEngine:
    """
    简单事件驱动回测引擎。
    用途：在 self_evolution 流程中，用历史数据验证调整后的策略参数是否改善了收益。
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage

    def run(
        self,
        price_data: Dict[str, pd.DataFrame],  # symbol -> OHLCV DataFrame
        signal_fn: Callable,                   # (symbol, df_slice) -> "buy"|"sell"|"hold"
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict:
        """
        运行回测，返回绩效指标。

        Args:
            price_data: 各标的的历史价格数据
            signal_fn:  信号生成函数，接受 (symbol, df) 返回操作方向
            start_date: 回测开始日期 YYYY-MM-DD
            end_date:   回测结束日期 YYYY-MM-DD

        Returns:
            Dict 包含: total_return, sharpe, max_drawdown, win_rate, trade_count
        """
        cash = self.initial_capital
        positions: Dict[str, Dict] = {}  # symbol -> {qty, cost}
        equity_curve: List[float] = []
        trades: List[Dict] = []

        # 取所有标的交集日期
        all_dates = sorted(set.intersection(
            *[set(df.index.astype(str)) for df in price_data.values()]
        ))
        if start_date:
            all_dates = [d for d in all_dates if d >= start_date]
        if end_date:
            all_dates = [d for d in all_dates if d <= end_date]

        for date in all_dates:
            day_value = cash

            for symbol, df in price_data.items():
                try:
                    df_slice = df.loc[:date]
                    if len(df_slice) < 2:
                        continue
                    price = float(df_slice.iloc[-1]["close"])
                except (KeyError, IndexError):
                    continue

                # 更新持仓市值
                if symbol in positions:
                    day_value += positions[symbol]["qty"] * price

                # 生成信号
                signal = signal_fn(symbol, df_slice)

                if signal == "buy" and symbol not in positions and cash > price * 100:
                    # 买入：用 10% 资金
                    invest = min(cash * 0.10, cash)
                    qty = int(invest / (price * (1 + self.slippage)) // 100 * 100)
                    if qty > 0:
                        cost = qty * price * (1 + self.slippage)
                        commission = cost * self.commission_rate
                        cash -= (cost + commission)
                        positions[symbol] = {"qty": qty, "cost": price, "entry_date": date}

                elif signal == "sell" and symbol in positions:
                    pos = positions.pop(symbol)
                    revenue = pos["qty"] * price * (1 - self.slippage)
                    commission = revenue * self.commission_rate
                    pnl = revenue - pos["qty"] * pos["cost"] - commission
                    cash += revenue - commission
                    trades.append({
                        "symbol": symbol,
                        "entry_date": pos["entry_date"],
                        "exit_date": date,
                        "pnl": pnl,
                        "pnl_pct": pnl / (pos["qty"] * pos["cost"]),
                        "outcome": "win" if pnl > 0 else "loss",
                    })

            equity_curve.append(day_value)

        return self._calc_metrics(equity_curve, trades)

    def _calc_metrics(self, equity_curve: List[float], trades: List[Dict]) -> Dict:
        if not equity_curve:
            return {}
        import numpy as np
        eq = pd.Series(equity_curve)
        returns = eq.pct_change().dropna()
        total_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital
        sharpe = (returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0
        rolling_max = eq.cummax()
        drawdown = (eq - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min())
        win_trades = [t for t in trades if t["outcome"] == "win"]
        win_rate = len(win_trades) / max(len(trades), 1)
        return {
            "total_return": round(total_return, 4),
            "sharpe": round(float(sharpe), 4),
            "max_drawdown": round(max_drawdown, 4),
            "win_rate": round(win_rate, 4),
            "trade_count": len(trades),
            "final_equity": round(equity_curve[-1], 2),
        }
