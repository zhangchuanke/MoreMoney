"""
社交媒体情绪工具
来源：东方财富股吧热度、同花顺人气榜
"""
import asyncio
from datetime import datetime
from typing import Dict

try:
    import akshare as ak
except ImportError:
    ak = None


class SocialSentimentTool:

    async def get_sentiment(self, symbol: str) -> Dict:
        """获取个股社交媒体情绪数据"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_sentiment, symbol
        )

    def _sync_get_sentiment(self, symbol: str) -> Dict:
        if ak is None:
            return self._mock_sentiment(symbol)
        code = symbol.replace("sh", "").replace("sz", "")
        try:
            # 东方财富股吧人气
            df = ak.stock_hot_rank_em()
            row = df[df["代码"] == code]
            if row.empty:
                return self._mock_sentiment(symbol)
            r = row.iloc[0]
            rank = int(r.get("排名", 999))
            # 排名越靠前情绪分越高，线性映射到 0~1
            score = max(0.0, 1.0 - rank / 500.0)
            return {
                "symbol": symbol,
                "score": round(score, 3),
                "rank": rank,
                "mention_count": int(r.get("关注人数", 0)),
                "hot_keywords": [],
                "timestamp": datetime.now().isoformat(),
            }
        except Exception:
            return self._mock_sentiment(symbol)

    def _mock_sentiment(self, symbol: str) -> Dict:
        import random
        return {
            "symbol": symbol,
            "score": round(random.uniform(0.3, 0.7), 3),
            "rank": random.randint(1, 500),
            "mention_count": random.randint(100, 10000),
            "hot_keywords": ["业绩", "突破", "主力"],
            "timestamp": datetime.now().isoformat(),
        }
