"""
基本面分析 Agent
分析：财务报表、估值指标、行业地位、成长性、股东结构
"""
import json
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.analysis_prompts import FUNDAMENTAL_ANALYSIS_PROMPT
from core.state.agent_state import AgentState, MarketSignal
from tools.fundamental.financial_report import FinancialReportTool
from tools.fundamental.valuation import ValuationTool
from tools.fundamental.industry_analysis import IndustryAnalysisTool


class FundamentalAgent:
    """
    基本面分析 Agent。
    核心分析维度:
      - 盈利能力：ROE / ROA / 净利率 / 毛利率
      - 成长性：营收/净利 YoY / QoQ
      - 估值：PE / PB / PEG / EV/EBITDA
      - 财务健康：资产负债率 / 流动比率 / 现金流
      - 行业地位：市占率、竞争格局
      - 股东结构：机构持仓变化
    """

    def __init__(self):
        self.llm = QwenClient()
        self.fin_report = FinancialReportTool()
        self.valuation = ValuationTool()
        self.industry = IndustryAnalysisTool()

    async def analyze(self, state: AgentState) -> AgentState:
        symbols = state.get("target_symbols", [])
        signals: List[MarketSignal] = []

        for symbol in symbols:
            try:
                signal = await self._analyze_single(symbol, state)
                signals.append(signal)
            except Exception as e:
                state.setdefault("errors", []).append(f"[FundamentalAgent] {symbol}: {e}")

        return {
            **state,
            "signals": signals,
            "logs": [f"[FundamentalAgent] 完成 {len(signals)}/{len(symbols)} 只标的基本面分析"],
        }

    async def _analyze_single(self, symbol: str, state: AgentState) -> MarketSignal:
        # 1. 最新财报关键指标
        fin = await self.fin_report.get_key_metrics(symbol)

        # 2. 估值指标
        val = await self.valuation.get_valuation(symbol)

        # 3. 行业分析
        ind = await self.industry.get_industry_context(symbol)

        context = {
            "symbol": symbol,
            # 盈利能力
            "roe_ttm": fin.get("roe_ttm"),
            "net_profit_margin": fin.get("net_profit_margin"),
            "gross_profit_margin": fin.get("gross_profit_margin"),
            # 成长性
            "revenue_yoy": fin.get("revenue_yoy"),
            "net_profit_yoy": fin.get("net_profit_yoy"),
            "revenue_qoq": fin.get("revenue_qoq"),
            # 估值
            "pe_ttm": val.get("pe_ttm"),
            "pb": val.get("pb"),
            "peg": val.get("peg"),
            "pe_percentile": val.get("pe_percentile"),  # 历史估值分位
            # 财务健康
            "debt_ratio": fin.get("debt_ratio"),
            "current_ratio": fin.get("current_ratio"),
            "free_cash_flow_yield": fin.get("free_cash_flow_yield"),
            # 行业
            "industry": ind.get("industry"),
            "industry_rank": ind.get("rank"),
            "industry_pe_avg": ind.get("pe_avg"),
            "market_cap": val.get("market_cap"),
            "institutional_hold_pct": fin.get("institutional_hold_pct"),
            "major_shareholder_change": fin.get("major_shareholder_change"),
        }

        prompt = FUNDAMENTAL_ANALYSIS_PROMPT.format(
            data=json.dumps(context, ensure_ascii=False, indent=2)
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            result = json.loads(response)
        except Exception:
            result = {"direction": "neutral", "strength": 0.3, "confidence": 0.3, "reasoning": response}

        return MarketSignal(
            dimension="fundamental",
            direction=result.get("direction", "neutral"),
            strength=float(result.get("strength", 0.3)),
            confidence=float(result.get("confidence", 0.3)),
            reasoning=result.get("reasoning", ""),
            indicators=context,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
        )
