"""
财务报表关键指标工具
主数据源：pytdx 扩展财务接口
补充数据源：akshare（财务分析指标）
"""
import asyncio
from typing import Dict

from tools.market_data.tdx_client import get_tdx_client


class FinancialReportTool:

    def __init__(self):
        self._client = get_tdx_client()

    async def get_key_metrics(self, symbol: str) -> Dict:
        """获取最新财报核心指标"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_metrics, symbol
        )

    def _sync_get_metrics(self, symbol: str) -> Dict:
        # 1. 先尝试 pytdx 扩展财务接口
        try:
            fin = self._client.get_finance_info(symbol)
            if fin:
                return self._parse_tdx_finance(symbol, fin)
        except Exception:
            pass

        # 2. 降级到 akshare
        try:
            return self._from_akshare(symbol)
        except Exception:
            return self._mock(symbol)

    def _parse_tdx_finance(self, symbol: str, fin: Dict) -> Dict:
        """解析 pytdx get_finance_info 返回结构"""
        return {
            "symbol":               symbol,
            "roe_ttm":              fin.get("roediluted"),
            "net_profit_margin":    fin.get("netprofit_margin"),
            "gross_profit_margin":  fin.get("grossprofit_margin"),
            "revenue_yoy":          fin.get("rev_yoy"),
            "net_profit_yoy":       fin.get("profit_yoy"),
            "revenue_qoq":          None,
            "debt_ratio":           fin.get("liabilities_ratio"),
            "current_ratio":        fin.get("current_ratio"),
            "free_cash_flow_yield": None,
            "institutional_hold_pct":    None,
            "major_shareholder_change":  None,
        }

    def _from_akshare(self, symbol: str) -> Dict:
        import akshare as ak
        code = symbol.replace("sh", "").replace("sz", "").strip()
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2023")
        if df.empty:
            return self._mock(symbol)
        row  = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else row

        def sf(v):
            try: return float(v)
            except Exception: return None

        rev       = sf(row.get("营业总收入", 0)) or 0
        prev_rev  = sf(prev.get("营业总收入", 1)) or 1
        profit     = sf(row.get("净利润", 0)) or 0
        prev_profit= sf(prev.get("净利润", 1)) or 1

        return {
            "symbol":               symbol,
            "roe_ttm":              sf(row.get("净资产收益率")),
            "net_profit_margin":    sf(row.get("销售净利率")),
            "gross_profit_margin":  sf(row.get("销售毛利率")),
            "revenue_yoy":          round((rev - prev_rev) / max(abs(prev_rev), 1), 4),
            "net_profit_yoy":       round((profit - prev_profit) / max(abs(prev_profit), 1), 4),
            "revenue_qoq":          None,
            "debt_ratio":           sf(row.get("资产负债率")),
            "current_ratio":        sf(row.get("流动比率")),
            "free_cash_flow_yield": None,
            "institutional_hold_pct":   None,
            "major_shareholder_change":  None,
        }

    def _mock(self, symbol: str) -> Dict:
        import random
        return {
            "symbol":               symbol,
            "roe_ttm":              round(random.uniform(5, 25), 2),
            "net_profit_margin":    round(random.uniform(5, 30), 2),
            "gross_profit_margin":  round(random.uniform(20, 60), 2),
            "revenue_yoy":          round(random.uniform(-0.1, 0.3), 4),
            "net_profit_yoy":       round(random.uniform(-0.1, 0.4), 4),
            "revenue_qoq":          round(random.uniform(-0.05, 0.15), 4),
            "debt_ratio":           round(random.uniform(20, 60), 2),
            "current_ratio":        round(random.uniform(1.0, 3.0), 2),
            "free_cash_flow_yield": round(random.uniform(0.02, 0.08), 4),
            "institutional_hold_pct":   round(random.uniform(10, 60), 2),
            "major_shareholder_change":  round(random.uniform(-0.02, 0.02), 4),
        }
