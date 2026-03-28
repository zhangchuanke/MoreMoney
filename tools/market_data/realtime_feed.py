"""
实时行情数据工具 - 基于同花顺通达信协议（pytdx）

akshare 作为降级备用（新闻/公告等 pytdx 不支持的数据）
"""
import asyncio
from datetime import datetime
from typing import Dict, List

from tools.market_data.tdx_client import get_tdx_client


class RealtimeFeed:
    """
    实时行情工具 - 主数据源：pytdx（同花顺通达信协议）
    特点：免费、无需账号、延迟约1-3秒、覆盖全A股
    """

    def __init__(self):
        self._client = get_tdx_client()

    async def get_quote(self, symbol: str) -> Dict:
        """获取单股实时行情"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_quote, symbol
        )

    async def get_batch_quotes(self, symbols: List[str]) -> List[Dict]:
        """批量获取实时行情（每次最多80只，自动分批）"""
        results = []
        # pytdx 单次限制80只
        for i in range(0, len(symbols), 80):
            batch = symbols[i:i + 80]
            batch_result = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_batch_quotes, batch
            )
            results.extend(batch_result)
        return results

    async def get_hot_stocks(
        self,
        top_n: int = 50,
        min_amount: float = 5e7,   # 最小成交额5000万
    ) -> List[Dict]:
        """
        获取热门股票（按成交额排序）。
        策略：获取沪深两市全量股票行情，按成交额筛选 top_n。
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_hot_stocks, top_n, min_amount
        )

    def _sync_get_hot_stocks(
        self, top_n: int, min_amount: float
    ) -> List[Dict]:
        from pytdx.params import TDXParams
        client = self._client

        # 获取沪深两市股票列表
        sh_list = client.get_stock_list(TDXParams.MARKET_SH)
        sz_list = client.get_stock_list(TDXParams.MARKET_SZ)

        # 过滤：只保留主板/中小板/创业板（6/0/3开头），排除基金/债券
        def is_stock(code: str) -> bool:
            return (
                code.startswith(("6", "0", "3"))
                and not code.startswith(("580", "511", "159", "519"))
            )

        sh_symbols = [
            "sh" + s["code"] for s in sh_list
            if is_stock(s.get("code", ""))
        ]
        sz_symbols = [
            "sz" + s["code"] for s in sz_list
            if is_stock(s.get("code", ""))
        ]
        all_symbols = sh_symbols + sz_symbols

        # 批量获取行情
        quotes = []
        for i in range(0, len(all_symbols), 80):
            batch = all_symbols[i:i + 80]
            batch_quotes = client.get_batch_quotes(batch)
            quotes.extend(batch_quotes)

        # 过滤停牌/涨跌停异常 + 按成交额排序
        valid = [
            q for q in quotes
            if q.get("amount", 0) >= min_amount
            and q.get("price", 0) > 1.0   # 过滤超低价股
        ]
        valid.sort(key=lambda x: x.get("amount", 0), reverse=True)
        return valid[:top_n]

    async def get_stock_list_all(self) -> List[Dict]:
        """获取沪深两市全量股票列表"""
        from pytdx.params import TDXParams
        sh = await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_stock_list, TDXParams.MARKET_SH
        )
        sz = await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_stock_list, TDXParams.MARKET_SZ
        )
        return [
            {**s, "market": "SH"} for s in (sh or [])
        ] + [
            {**s, "market": "SZ"} for s in (sz or [])
        ]
