"""
新闻爬虫工具
对接：东方财富财经新闻、同花顺、雪球（通过 akshare）
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None


class NewsCrawler:

    async def fetch(self, symbol: str, days: int = 3) -> List[Dict]:
        """获取个股近N天财经新闻"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_fetch, symbol, days
        )

    def _sync_fetch(self, symbol: str, days: int) -> List[Dict]:
        if ak is None:
            return self._mock_news(symbol)
        code = symbol.replace("sh", "").replace("sz", "")
        results = []
        try:
            df = ak.stock_news_em(symbol=code)
            cutoff = datetime.now() - timedelta(days=days)
            for _, row in df.iterrows():
                try:
                    pub_time = pd.to_datetime(row.get("发布时间", ""))
                    if pub_time < cutoff:
                        continue
                except Exception:
                    pass
                results.append({
                    "title":   row.get("新闻标题", ""),
                    "content": row.get("新闻内容", "")[:500],
                    "source":  row.get("文章来源", ""),
                    "pub_time": str(row.get("发布时间", "")),
                    "url":     row.get("新闻链接", ""),
                })
        except Exception:
            return self._mock_news(symbol)
        return results[:20]

    def _mock_news(self, symbol: str) -> List[Dict]:
        return [
            {
                "title": f"[{symbol}] 模拟新闻：公司发布季报，业绩符合预期",
                "content": "公司本季度营收同比增长15%，净利润增长12%。",
                "source": "东方财富",
                "pub_time": datetime.now().isoformat(),
                "url": "",
            }
        ]
