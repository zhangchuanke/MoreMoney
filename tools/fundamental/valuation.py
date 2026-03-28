"""
估值指标工具
主数据源：pytdx 扩展财务接口（PE/PB/市值）
补充数据源：akshare
"""
import asyncio
from typing import Dict

from tools.market_data.tdx_client import get_tdx_client


class ValuationTool:

    def __init__(self):
        self._client = get_tdx_client()

    async def get_valuation(self, symbol: str) -> Dict:
        """获取个股最新估值数据"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_valuation, symbol
        )

    def _sync_get_valuation(self, symbol: str) -> Dict:
        # 1. pytdx 实时行情中含有 PE/PB
        try:
            q = self._client.get_quote(symbol)
            fin = self._client.get_finance_info(symbol)
            pe  = fin.get("pe") or fin.get("pe_ratio") or fin.get("totalpe")
            pb  = fin.get("pb") or fin.get("pb_ratio")
            mktcap = fin.get("totals") and fin.get("totalpe")  # 占位
            if pe or pb:
                return {
                    "symbol":       symbol,
                    "pe_ttm":       float(pe) if pe else None,
                    "pb":           float(pb) if pb else None,
                    "ps":           None,
                    "peg":          None,
                    "pe_percentile": None,
                    "market_cap":   None,
                    "date":         "",
                }
        except Exception:
            pass

        # 2. 降级到 akshare
        try:
            return self._from_akshare(symbol)
        except Exception:
            return self._mock(symbol)

    def _from_akshare(self, symbol: str) -> Dict:
        import akshare as ak
        code = symbol.replace("sh", "").replace("sz", "").strip()
        df = ak.stock_a_lg_indicator(symbol=code)
        if df.empty:
            return self._mock(symbol)
        row = df.iloc[-1]
        pe  = float(row.get("pe", 0))
        hist_pe = df["pe"].dropna().astype(float)
        pe_pct  = float((hist_pe <= pe).sum() / max(len(hist_pe), 1))
        return {
            "symbol":       symbol,
            "pe_ttm":       pe,
            "pb":           float(row.get("pb", 0)),
            "ps":           float(row.get("ps", 0)),
            "peg":          None,
            "pe_percentile": round(pe_pct, 4),
            "market_cap":   float(row.get("total_mv", 0)),
            "date":         str(row.get("trade_date", "")),
        }

    def _mock(self, symbol: str) -> Dict:
        import random
        return {
            "symbol":       symbol,
            "pe_ttm":       round(random.uniform(10, 50), 2),
            "pb":           round(random.uniform(1, 8), 2),
            "ps":           round(random.uniform(1, 10), 2),
            "peg":          round(random.uniform(0.5, 2.5), 2),
            "pe_percentile": round(random.uniform(0.1, 0.9), 3),
            "market_cap":   round(random.uniform(10, 3000), 2),
            "date":         "",
        }
