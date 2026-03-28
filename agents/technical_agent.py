"""
技术面分析 Agent
分析：均线/MACD/KDJ/RSI/布林带/成交量/形态/支撑压力位等
"""
import json
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.analysis_prompts import TECHNICAL_ANALYSIS_PROMPT
from core.state.agent_state import AgentState, MarketSignal
from tools.technical.indicators import TechnicalIndicators
from tools.technical.pattern_recognition import PatternRecognition
from tools.market_data.historical_data import HistoricalDataTool


class TechnicalAgent:
    """
    技术面分析 Agent。
    对 state.target_symbols 中每只股票:
      1. 获取历史K线
      2. 计算多维技术指标
      3. 识别K线形态
      4. 调用 LLM 给出技术面信号
    """

    def __init__(self):
        self.llm = QwenClient()
        self.indicators = TechnicalIndicators()
        self.patterns = PatternRecognition()
        self.hist_data = HistoricalDataTool()

    async def analyze(self, state: AgentState) -> AgentState:
        symbols = state.get("target_symbols", [])
        signals: List[MarketSignal] = []

        for symbol in symbols:
            try:
                signal = await self._analyze_single(symbol, state)
                signals.append(signal)
            except Exception as e:
                state.setdefault("errors", []).append(f"[TechnicalAgent] {symbol}: {e}")

        return {
            **state,
            "signals": signals,
            "logs": [f"[TechnicalAgent] 完成 {len(signals)}/{len(symbols)} 只标的技术分析"],
        }

    async def _analyze_single(self, symbol: str, state: AgentState) -> MarketSignal:
        # 1. 获取日线数据（近120日）
        df = await self.hist_data.get_daily(symbol, periods=120)

        # 2. 计算指标
        ind = self.indicators.compute_all(df)

        # 3. 识别形态
        patterns_found = self.patterns.detect(df)

        # 4. 组织数据给 LLM
        latest = df.iloc[-1]
        summary = {
            "symbol": symbol,
            "date": str(latest.name),
            "close": float(latest["close"]),
            "change_pct": float(latest.get("change_pct", 0)),
            "volume_ratio": float(ind.get("volume_ratio", 1)),
            "ma5": float(ind.get("ma5", 0)),
            "ma20": float(ind.get("ma20", 0)),
            "ma60": float(ind.get("ma60", 0)),
            "macd": float(ind.get("macd", 0)),
            "macd_signal": float(ind.get("macd_signal", 0)),
            "macd_hist": float(ind.get("macd_hist", 0)),
            "rsi14": float(ind.get("rsi14", 50)),
            "kdj_k": float(ind.get("kdj_k", 50)),
            "kdj_d": float(ind.get("kdj_d", 50)),
            "boll_upper": float(ind.get("boll_upper", 0)),
            "boll_lower": float(ind.get("boll_lower", 0)),
            "atr14": float(ind.get("atr14", 0)),
            "patterns": patterns_found,
            "support_levels": self.indicators.find_support_resistance(df, mode="support"),
            "resistance_levels": self.indicators.find_support_resistance(df, mode="resistance"),
        }

        prompt = TECHNICAL_ANALYSIS_PROMPT.format(
            data=json.dumps(summary, ensure_ascii=False, indent=2)
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            result = json.loads(response)
        except Exception:
            result = {"direction": "neutral", "strength": 0.3, "confidence": 0.3, "reasoning": response}

        return MarketSignal(
            dimension="technical",
            direction=result.get("direction", "neutral"),
            strength=float(result.get("strength", 0.3)),
            confidence=float(result.get("confidence", 0.3)),
            reasoning=result.get("reasoning", ""),
            indicators=summary,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
        )
