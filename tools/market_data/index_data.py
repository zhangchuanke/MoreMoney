"""
指数与大盘数据工具 - 基于同花顺通达信协议（pytdx）
指数代码：上证 sh000001 / 深证 sz399001 / 创业板 sz399006
"""
import asyncio
from datetime import datetime
from typing import Dict, List

from tools.market_data.tdx_client import get_tdx_client, _get_market

# 主要指数
INDICES = {
    "sh": ("sh000001", "上证指数"),
    "sz": ("sz399001", "深证成指"),
    "cy": ("sz399006", "创业板指"),
    "kc": ("sh000688", "科创50"),
}


class IndexDataTool:

    def __init__(self):
        self._client = get_tdx_client()

    async def get_overview(self) -> Dict:
        """获取大盘概览（主要指数实时行情）"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_overview
        )

    def _sync_get_overview(self) -> Dict:
        try:
            symbols = [sym for sym, _ in INDICES.values()]
            quotes  = self._client.get_batch_quotes(symbols)

            result: Dict = {"timestamp": datetime.now().isoformat()}
            for i, (key, (sym, name)) in enumerate(INDICES.items()):
                q = quotes[i] if i < len(quotes) else {}
                price     = q.get("price", 0)
                pre_close = q.get("pre_close", price or 1)
                change_pct = round(
                    (price - pre_close) / max(pre_close, 0.01) * 100, 3
                ) if pre_close else 0
                result[f"{key}_index"]            = price
                result[f"{key}_index_change_pct"] = change_pct
                result[f"{key}_volume"]           = q.get("volume", 0)
                result[f"{key}_amount"]           = q.get("amount", 0)

            # A股无官方VIX，用上证当日振幅粗略估算
            sh_q = quotes[0] if quotes else {}
            sh_high = sh_q.get("high", 0)
            sh_low  = sh_q.get("low",  1)
            sh_pre  = sh_q.get("pre_close", 1)
            vix_proxy = round(
                (sh_high - sh_low) / max(sh_pre, 1) * 100, 2
            ) if sh_pre else 20.0
            result["vix"]                  = vix_proxy
            result["advance_decline_ratio"] = 1.0  # 需单独接口，此处占位
            return result
        except Exception as e:
            return self._mock_overview(str(e))

    def _mock_overview(self, reason: str = "") -> Dict:
        import random
        print(f"[IndexDataTool] 降级使用模拟数据: {reason}")
        return {
            "timestamp":            datetime.now().isoformat(),
            "sh_index":             round(3200 + random.uniform(-80, 80), 2),
            "sh_index_change_pct":  round(random.uniform(-1.5, 1.5), 3),
            "sh_volume":            random.randint(200000000, 400000000),
            "sz_index":             round(10500 + random.uniform(-200, 200), 2),
            "sz_index_change_pct":  round(random.uniform(-1.5, 1.5), 3),
            "cy_index":             round(2000 + random.uniform(-80, 80), 2),
            "cy_index_change_pct":  round(random.uniform(-2, 2), 3),
            "vix":                  round(random.uniform(10, 25), 1),
            "advance_decline_ratio": round(random.uniform(0.6, 1.8), 2),
        }

    async def get_index_daily(
        self, symbol: str = "sh000001", periods: int = 60
    ) -> "pd.DataFrame":
        """获取指数日线历史"""
        from tools.market_data.tdx_client import _get_market
        return await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_daily_bars, symbol, periods
        )

    async def get_sector_heatmap(self) -> List[Dict]:
        """
        板块热力图。pytdx 支持板块数据，但需要扩展行情服务器。
        此处降级使用 akshare。
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_sector_heatmap
        )

    def _sync_sector_heatmap(self) -> List[Dict]:
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            result = [
                {
                    "sector":     row.get("板块名称", ""),
                    "change_pct": float(row.get("涨跌幅", 0)),
                    "amount":     float(row.get("成交额", 0)),
                }
                for _, row in df.iterrows()
            ]
            return sorted(result, key=lambda x: x["change_pct"], reverse=True)
        except Exception:
            return []
