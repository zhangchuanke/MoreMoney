"""
公司公告解析工具
获取：业绩预告、定增、并购、股权激励、重大合同等
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

try:
    import akshare as ak
except ImportError:
    ak = None


class AnnouncementParser:

    # 重要公告关键词（触发高置信度）
    HIGH_IMPACT_KEYWORDS = [
        "业绩预增", "业绩预减", "定向增发", "股票回购",
        "重大资产重组", "收购", "战略合作", "中标",
        "股权激励", "分红", "特别分红",
    ]

    async def fetch(self, symbol: str, days: int = 7) -> List[Dict]:
        """获取个股近N天公告"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_fetch, symbol, days
        )

    def _sync_fetch(self, symbol: str, days: int) -> List[Dict]:
        if ak is None:
            return []
        code = symbol.replace("sh", "").replace("sz", "")
        try:
            df = ak.stock_notice_report(symbol=code)
            cutoff = datetime.now() - timedelta(days=days)
            results = []
            for _, row in df.iterrows():
                results.append({
                    "title":    row.get("公告标题", ""),
                    "type":     row.get("公告类型", ""),
                    "pub_date": str(row.get("公告日期", "")),
                    "is_high_impact": any(
                        kw in row.get("公告标题", "")
                        for kw in self.HIGH_IMPACT_KEYWORDS
                    ),
                    "url": row.get("公告链接", ""),
                })
            return results[:10]
        except Exception:
            return []
