"""
大宗交易数据工具
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

try:
    import akshare as ak
except ImportError:
    ak = None


class BlockTradeTool:

    async def get_recent(self, symbol: str, days: int = 5) -> List[Dict]:
        """获取个股近N天大宗交易记录"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_recent, symbol, days
        )

    def _sync_get_recent(self, symbol: str, days: int) -> List[Dict]:
        if ak is None:
            return []
        code = symbol.replace("sh", "").replace("sz", "")
        try:
            df = ak.stock_dzjy_mrtj()
            df = df[df["证券代码"] == code]
            result = []
            for _, row in df.iterrows():
                close_price = float(row.get("收盘价", 1))
                trade_price = float(row.get("成交价", 1))
                discount = (trade_price - close_price) / max(close_price, 0.01)
                result.append({
                    "date": str(row.get("交易日期", "")),
                    "price": trade_price,
                    "close": close_price,
                    "discount": round(discount, 4),
                    "volume": float(row.get("成交量", 0)),
                    "amount": float(row.get("成交额", 0)),
                    "buyer": row.get("买方营业部", ""),
                    "seller": row.get("卖方营业部", ""),
                })
            return result
        except Exception:
            return []
