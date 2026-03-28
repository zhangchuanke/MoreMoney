"""
历史K线数据工具 - 基于同花顺通达信协议（pytdx）
支持：日线、分钟线（1/5/15/30/60分钟）
"""
import asyncio
from typing import Optional
import pandas as pd

from tools.market_data.tdx_client import get_tdx_client


class HistoricalDataTool:

    def __init__(self):
        self._client = get_tdx_client()

    async def get_daily(
        self,
        symbol: str,
        periods: int = 120,
    ) -> pd.DataFrame:
        """
        获取日线历史数据（前复权价格需自行处理，pytdx 返回未复权）。
        返回 DataFrame，index 为日期，列：open/high/low/close/volume/amount/change_pct
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_daily_bars, symbol, periods
        )

    async def get_minute(
        self,
        symbol: str,
        period: int = 5,    # 1/5/15/30/60
        count:  int = 100,
    ) -> pd.DataFrame:
        """获取分钟K线"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_minute_bars, symbol, period, count
        )

    async def get_multi_daily(
        self,
        symbols: list,
        periods: int = 60,
    ) -> dict:
        """
        并发获取多只股票的日线数据。
        返回 {symbol: DataFrame}
        """
        tasks = [
            self.get_daily(sym, periods)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            sym: df
            for sym, df in zip(symbols, results)
            if isinstance(df, pd.DataFrame) and not df.empty
        }
