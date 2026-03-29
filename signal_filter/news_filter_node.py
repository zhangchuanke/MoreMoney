"""
news_filter_node  ——  LangGraph 节点入口

插入位置：data_quality -> news_filter -> (technical / sentiment / capital_flow / fundamental)

职责：
  1. 对 target_symbols 的新闻列表执行降噪 + 可信度过滤
  2. 将过滤后的新闻写入 state["filtered_news"]
  3. 旧闻 / 低信噪比情况写入 risk_flags 告警
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from core.state.agent_state import AgentState
from signal_filter._news_filter_impl import filter_news_items
from tools.news.news_crawler import NewsCrawler
from tools.news.announcements import AnnouncementParser

logger = logging.getLogger(__name__)

_crawler    = NewsCrawler()
_ann_parser = AnnouncementParser()


async def news_filter_node(state: AgentState) -> AgentState:
    """
    LangGraph 异步节点：消息面信号降噪与可信度分级。

    读取  state["target_symbols"]
    写入  state["filtered_news"]     — {symbol: FilteredNewsResult.to_dict()}
          state["news_summaries"]    — 供情绪 Agent 使用的已过滤新闻摘要
          state["risk_flags"]        — 旧闻 / 噪音告警
          state["logs"]              — 运行日志
    """
    symbols: List[str] = state.get("target_symbols", [])
    if not symbols:
        return {**state, "logs": ["[NewsFilter] target_symbols 为空，跳过新闻过滤"]}

    # 并发拉取所有标的的新闻（普通新闻 + 官方公告）
    news_tasks = [_crawler.fetch(sym, days=3) for sym in symbols]
    ann_tasks  = [_ann_parser.fetch(sym, days=7) for sym in symbols]
    all_news_raw, all_ann_raw = await asyncio.gather(
        asyncio.gather(*news_tasks),
        asyncio.gather(*ann_tasks),
    )

    filtered_news: Dict[str, Dict] = {}
    news_summaries: List[Dict]     = []
    risk_flags: List[str]          = []
    total_accepted = 0
    total_rejected = 0

    for i, sym in enumerate(symbols):
        # 合并普通新闻和公告，公告标记来源为「上市公司公告」
        raw_items = list(all_news_raw[i])
        for ann in all_ann_raw[i]:
            ann.setdefault("source", "上市公司公告")
            raw_items.append(ann)

        result = filter_news_items(raw_items, sym, official_only=False)

        total_accepted += result.accepted_count
        total_rejected += (
            len(result.rejected_noise)
            + len(result.rejected_duplicate)
            + len(result.rejected_low_credibility)
        )

        # 旧闻告警
        if result.rejected_duplicate:
            risk_flags.append(
                f"[NewsFilter] {sym} 检测到 {len(result.rejected_duplicate)} 条旧闻新炒，已过滤"
            )

        # 信噪比极低告警
        if result.original_count > 0 and result.accepted_count == 0:
            risk_flags.append(
                f"[NewsFilter] {sym} 全部 {result.original_count} 条新闻均被过滤，消息面信号无效"
            )

        filtered_news[sym] = {
            "accepted_count":    result.accepted_count,
            "rejected_noise":    len(result.rejected_noise),
            "rejected_duplicate": len(result.rejected_duplicate),
            "rejected_low_cred": len(result.rejected_low_credibility),
            "signal_strength":   result.weighted_signal_strength,
            "items": [
                {
                    "title":       n.title,
                    "source":      n.source,
                    "pub_time":    n.pub_time,
                    "credibility": n.credibility,
                    "is_official": n.is_official,
                    "content":     n.content[:300],
                }
                for n in result.accepted[:10]  # 最多传 10 条给下游
            ],
        }

        # 为情绪 Agent 构建摘要
        if result.accepted:
            news_summaries.append({
                "symbol":   sym,
                "news":     filtered_news[sym]["items"],
                "strength": result.weighted_signal_strength,
            })

    log_msg = (
        f"[NewsFilter] 完成：{len(symbols)} 个标的，"
        f"接受 {total_accepted} / 过滤 {total_rejected} 条新闻"
    )
    logger.info(log_msg)

    return {
        **state,
        "filtered_news":  filtered_news,
        "news_summaries": news_summaries,
        "risk_flags":     risk_flags,
        "logs":           [log_msg],
    }
