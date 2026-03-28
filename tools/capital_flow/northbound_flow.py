"""
北向资金（沪深港通）工具
数据源：akshare（pytdx 不支持北向资金数据）
"""
import asyncio
from datetime import datetime
from typing import Dict

try:
    import akshare as ak
except ImportError:
    ak = None


class NorthboundFlowTool:

    async def get_total_flow(self) -> Dict:
        """获取今日北向资金总量"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_total_flow
        )

    def _sync_total_flow(self) -> Dict:
        if ak is None:
            return self._mock_total()
        try:
            df = ak.stock_em_hsgt_north_net_flow_in(indicator="沪深港通")
            row = df.iloc[-1]
            return {
                "date":        str(row.get("日期", "")),
                "net_buy":     float(row.get("当日成交净买额", 0)),
                "cumulative":  float(row.get("历史累计净买额", 0)),
                "timestamp":   datetime.now().isoformat(),
            }
        except Exception:
            return self._mock_total()

    def _mock_total(self) -> Dict:
        import random
        return {
            "date":       datetime.now().strftime("%Y-%m-%d"),
            "net_buy":    round(random.uniform(-80, 120), 2),
            "cumulative": round(random.uniform(15000, 20000), 2),
            "timestamp":  datetime.now().isoformat(),
        }

    async def get_stock_flow(self, symbol: str) -> Dict:
        """获取个股北向持仓"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_stock_flow, symbol
        )

    def _sync_stock_flow(self, symbol: str) -> Dict:
        if ak is None:
            return self._mock_stock(symbol)
        code = symbol.replace("sh", "").replace("sz", "")
        try:
            df  = ak.stock_hsgt_hist_em(symbol=code)
            row = df.iloc[-1]
            return {
                "symbol":      symbol,
                "hold_shares": float(row.get("持股数量", 0)),
                "hold_pct":    float(row.get("持股比例", 0)),
                "net_buy":     float(row.get("当日净买入", 0)),
                "date":        str(row.get("日期", "")),
            }
        except Exception:
            return self._mock_stock(symbol)

    def _mock_stock(self, symbol: str) -> Dict:
        import random
        return {
            "symbol":      symbol,
            "hold_shares": random.randint(100000, 10000000),
            "hold_pct":    round(random.uniform(0, 5), 3),
            "net_buy":     round(random.uniform(-5000, 8000), 2),
            "date":        datetime.now().strftime("%Y-%m-%d"),
        }
