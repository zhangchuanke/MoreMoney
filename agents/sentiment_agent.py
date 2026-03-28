"""
消息面 / 情绪面分析 Agent
分析：财经新闻、公司公告、社交媒体情绪、研报摘要等
"""
import json
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.analysis_prompts import SENTIMENT_ANALYSIS_PROMPT
from core.state.agent_state import AgentState, MarketSignal
from tools.news.news_crawler import NewsCrawler
from tools.news.announcements import AnnouncementParser
from tools.news.social_sentiment import SocialSentimentTool


class SentimentAgent:
    """
    消息面分析 Agent。
    对每只目标股票:
      1. 抓取近期财经新闻
      2. 解析公司公告（业绩预告、重大事项等）
      3. 采集社交媒体情绪指数
      4. LLM 综合分析 → 消息面信号
    """

    def __init__(self):
        self.llm = QwenClient()
        self.news_crawler = NewsCrawler()
        self.announcement_parser = AnnouncementParser()
        self.social_tool = SocialSentimentTool()

    async def analyze(self, state: AgentState) -> AgentState:
        symbols = state.get("target_symbols", [])
        signals: List[MarketSignal] = []
        news_summaries = []

        for symbol in symbols:
            try:
                signal, news_data = await self._analyze_single(symbol)
                signals.append(signal)
                news_summaries.append({"symbol": symbol, "data": news_data})
            except Exception as e:
                state.setdefault("errors", []).append(f"[SentimentAgent] {symbol}: {e}")

        return {
            **state,
            "signals": signals,
            "news_summaries": news_summaries,
            "logs": [f"[SentimentAgent] 完成 {len(signals)}/{len(symbols)} 只标的消息面分析"],
        }

    async def _analyze_single(self, symbol: str):
        # 1. 新闻（近3天）
        news_list = await self.news_crawler.fetch(symbol, days=3)

        # 2. 公告
        announcements = await self.announcement_parser.fetch(symbol, days=7)

        # 3. 社交媒体情绪
        social = await self.social_tool.get_sentiment(symbol)

        # 4. 组织数据
        context = {
            "symbol": symbol,
            "news_count": len(news_list),
            "news_headlines": [n.get("title", "") for n in news_list[:10]],
            "key_announcements": [a.get("title", "") for a in announcements[:5]],
            "social_sentiment_score": social.get("score", 0.5),
            "social_mention_count": social.get("mention_count", 0),
            "hot_keywords": social.get("hot_keywords", []),
        }

        prompt = SENTIMENT_ANALYSIS_PROMPT.format(
            data=json.dumps(context, ensure_ascii=False, indent=2)
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            result = json.loads(response)
        except Exception:
            result = {"direction": "neutral", "strength": 0.3, "confidence": 0.3, "reasoning": response}

        signal = MarketSignal(
            dimension="sentiment",
            direction=result.get("direction", "neutral"),
            strength=float(result.get("strength", 0.3)),
            confidence=float(result.get("confidence", 0.3)),
            reasoning=result.get("reasoning", ""),
            indicators=context,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
        )
        return signal, context
