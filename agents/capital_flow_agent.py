"""
资金面分析 Agent
分析：北向资金、主力资金流向、融资融券、大宗交易、龙虎榜
"""
import json
from datetime import datetime
from typing import Dict, List

from llm.qwen_client import QwenClient
from llm.prompts.analysis_prompts import CAPITAL_FLOW_PROMPT
from core.state.agent_state import AgentState, MarketSignal
from tools.capital_flow.northbound_flow import NorthboundFlowTool
from tools.capital_flow.block_trade import BlockTradeTool
from tools.capital_flow.margin_data import MarginDataTool


class CapitalFlowAgent:
    """
    资金面分析 Agent。
    数据维度:
      - 北向资金（沪深港通）净买入
      - 主力资金流向（超大单/大单净流入）
      - 融资融券余额变化
      - 大宗交易（折溢价、机构席位）
      - 龙虎榜席位
    """

    def __init__(self):
        self.llm = QwenClient()
        self.northbound = NorthboundFlowTool()
        self.block_trade = BlockTradeTool()
        self.margin = MarginDataTool()

    async def analyze(self, state: AgentState) -> AgentState:
        symbols = state.get("target_symbols", [])
        signals: List[MarketSignal] = []

        # 先获取全市场北向总量（宏观资金环境）
        northbound_total = await self.northbound.get_total_flow()

        for symbol in symbols:
            try:
                signal = await self._analyze_single(symbol, northbound_total)
                signals.append(signal)
            except Exception as e:
                state.setdefault("errors", []).append(f"[CapitalFlowAgent] {symbol}: {e}")

        return {
            **state,
            "signals": signals,
            "logs": [f"[CapitalFlowAgent] 完成 {len(signals)}/{len(symbols)} 只标的资金面分析"],
        }

    async def _analyze_single(self, symbol: str, northbound_total: Dict) -> MarketSignal:
        # 1. 个股北向净买入
        nb_stock = await self.northbound.get_stock_flow(symbol)

        # 2. 主力资金流向（当日5分钟级别累计）
        main_flow = await self._get_main_capital_flow(symbol)

        # 3. 融资融券
        margin_info = await self.margin.get_latest(symbol)

        # 4. 大宗交易
        block_trades = await self.block_trade.get_recent(symbol, days=5)

        context = {
            "symbol": symbol,
            "northbound_market_total_net": northbound_total.get("net_buy", 0),
            "northbound_stock_net": nb_stock.get("net_buy", 0),
            "northbound_hold_pct": nb_stock.get("hold_pct", 0),
            "main_capital_net_inflow": main_flow.get("net_inflow", 0),
            "super_large_net": main_flow.get("super_large_net", 0),
            "large_net": main_flow.get("large_net", 0),
            "small_net": main_flow.get("small_net", 0),
            "margin_balance": margin_info.get("margin_balance", 0),
            "margin_change_pct": margin_info.get("change_pct", 0),
            "block_trade_count": len(block_trades),
            "block_trade_avg_discount": (
                sum(b.get("discount", 0) for b in block_trades) / len(block_trades)
                if block_trades else 0
            ),
        }

        prompt = CAPITAL_FLOW_PROMPT.format(
            data=json.dumps(context, ensure_ascii=False, indent=2)
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            result = json.loads(response)
        except Exception:
            result = {"direction": "neutral", "strength": 0.3, "confidence": 0.3, "reasoning": response}

        return MarketSignal(
            dimension="capital_flow",
            direction=result.get("direction", "neutral"),
            strength=float(result.get("strength", 0.3)),
            confidence=float(result.get("confidence", 0.3)),
            reasoning=result.get("reasoning", ""),
            indicators=context,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
        )

    async def _get_main_capital_flow(self, symbol: str) -> Dict:
        """调用行情API获取主力资金流向（可对接 akshare/tushare）"""
        # 占位实现，实际对接数据源
        return {"net_inflow": 0, "super_large_net": 0, "large_net": 0, "small_net": 0}
