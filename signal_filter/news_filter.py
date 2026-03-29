"""
消息面信号降噪与可信度分级模块

功能：
  1. 仅采信证监会指定信息披露媒体（白名单过滤）
  2. 通过 ChromaDB 历史向量比对识别旧闻新炒
  3. 给新闻源做可信度权重分级
  4. 过滤社交媒体噪音
  5. 作为 LangGraph 节点写入 state["filtered_news"]
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 证监会指定信息披露媒体白名单
# 来源：《上市公司信息披露管理办法》第十三条
# ---------------------------------------------------------------------------
OFFICIAL_DISCLOSURE_SOURCES: List[str] = [
    # 证监会指定报纸
    "中国证券报",
    "上海证券报",
    "证券时报",
    "证券日报",
    # 交易所官方渠道
    "上交所",
    "深交所",
    "上海证券交易所",
    "深圳证券交易所",
    # 官方网络平台
    "巨潮资讯",
    "上市公司公告",
    "东方财富公告",
    "同花顺公告",
]

# 可信度权重分级（0.0 ~ 1.0）
SOURCE_CREDIBILITY: Dict[str, float] = {
    # 官方信披媒体 — 最高可信度
    "中国证券报":     1.0,
    "上海证券报":     1.0,
    "证券时报":       1.0,
    "证券日报":       1.0,
    "上交所":         1.0,
    "深交所":         1.0,
    "上海证券交易所": 1.0,
    "深圳证券交易所": 1.0,
    "巨潮资讯":       1.0,
    # 主流财经媒体 — 高可信度
    "新华社":         0.95,
    "人民日报":       0.95,
    "央视财经":       0.90,
    "第一财经":       0.85,
    "财联社":         0.85,
    "界面新闻":       0.80,
    "21世纪经济报道":  0.80,
    "经济观察报":     0.80,
    "经济日报":       0.80,
    # 商业财经媒体 — 中等可信度
    "东方财富":       0.65,
    "同花顺":         0.65,
    "腾讯财经":       0.60,
    "网易财经":       0.60,
    "新浪财经":       0.60,
    # 社交/论坛 — 低可信度（通常过滤）
    "雪球":           0.30,
    "股吧":           0.20,
    "微博":           0.15,
    "抖音":           0.10,
    "微信":           0.20,
}

# 可信度阈值：低于此值的来源被过滤
CREDIBILITY_THRESHOLD = 0.50

# 旧闻相似度阈值：ChromaDB 余弦相似度超过此值视为旧闻
DUPLICATE_SIMILARITY_THRESHOLD = 0.85

# 旧闻时间窗口：仅检测近 N 天内的历史新闻
DUPLICATE_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class NewsItem:
    title: str
    content: str
    source: str
    pub_time: str
    url: str = ""
    symbol: str = ""
    credibility: float = 0.0        # 来源可信度权重
    is_official: bool = False       # 是否来自官方信披媒体
    is_duplicate: bool = False      # 是否为旧闻
    duplicate_of: str = ""          # 重复的原始新闻标题
    similarity_score: float = 0.0   # 与历史新闻的相似度
    content_hash: str = ""          # 内容哈希，用于精确去重


@dataclass
class FilteredNewsResult:
    symbol: str
    original_count: int
    accepted: List[NewsItem] = field(default_factory=list)
    rejected_noise: List[NewsItem] = field(default_factory=list)
    rejected_duplicate: List[NewsItem] = field(default_factory=list)
    rejected_low_credibility: List[NewsItem] = field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def weighted_signal_strength(self) -> float:
        """加权信号强度：通过的新闻条数 × 平均可信度"""
        if not self.accepted:
            return 0.0
        avg_cred = sum(n.credibility for n in self.accepted) / len(self.accepted)
        # 新闻数量对数归一化，防止刷量
        import math
        count_factor = min(1.0, math.log1p(len(self.accepted)) / math.log1p(10))
        return round(avg_cred * count_factor, 4)
