"""
融资融券数据工具
"""
import asyncio
from datetime import datetime
from typing import Dict

try:
    import akshare as ak
except ImportError:
    ak = None


class MarginDataTool:

    async def get_latest(self, symbol: str) -> Dict:
        """获取个股最新融资融券数据"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_latest, symbol
        )

    def _sync_get_latest(self, symbol: str) -> Dict:
        if ak is None:
            return self._mock(symbol)
        code = symbol.replace("sh", "").replace("sz", "")
        try:
            df = ak.stock_margin_detail_szse(symbol=code)
            if df.empty:
                df = ak.stock_margin_detail_sse(symbol=code)
            if df.empty:
                return self._mock(symbol)
            row = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else row
            balance = float(row.get("融资余额", 0))
            prev_balance = float(prev.get("融资余额", 1))
            return {
                "symbol": symbol,
                "margin_balance": balance,
                "margin_buy": float(row.get("融资买入额", 0)),
                "short_balance": float(row.get("融券余量", 0)),
                "change_pct": round((balance - prev_balance) / max(prev_balance, 1), 4),
                "date": str(row.get("日期", "")),
            }
        except Exception:
            return self._mock(symbol)

    def _mock(self, symbol: str) -> Dict:
        import random
        balance = random.randint(10000000, 500000000)
        return {
            "symbol": symbol,
            "margin_balance": balance,
            "margin_buy": random.randint(1000000, 50000000),
            "short_balance": random.randint(100000, 5000000),
            "change_pct": round(random.uniform(-0.05, 0.05), 4),
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
