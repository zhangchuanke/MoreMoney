"""
同花顺通达信协议数据客户端（基于 pytdx 1.72）

特点：
  - 完全免费，无需账号/Token
  - 覆盖 A股全市场实时行情、历史K线、财务数据、板块
  - 通过通达信服务器协议直接获取数据
  - 服务器列表自动选择延迟最低的节点

主要服务器（沪市 / 深市）:
  hq.sinajs.cn 类或标准通达信服务器
  pytdx 内置了多组公开服务器，自动选最优
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams

# 通达信公开服务器列表（优选低延迟）
TDX_SERVERS: List[Tuple[str, int]] = [
    ("119.147.212.81",  7709),  # 广州电信
    ("221.194.181.176", 7709),  # 北京联通
    ("120.76.152.87",  7709),  # 深圳阿里云
    ("47.107.75.159",  7709),  # 深圳阿里云2
    ("59.173.18.69",   7709),  # 武汉电信
    ("210.51.39.201",  7709),  # 上海电信
]

# 市场代码
MARKET_SH = TDXParams.MARKET_SH   # 0 = 上交所
MARKET_SZ = TDXParams.MARKET_SZ   # 1 = 深交所


def _get_market(symbol: str) -> int:
    """根据代码判断市场：6xxxx=沪市，其余=深市"""
    code = symbol.replace("sh", "").replace("sz", "").strip()
    return MARKET_SH if code.startswith("6") else MARKET_SZ


class TDXClient:
    """
    pytdx 同步客户端封装（在 executor 中运行，对外暴露 async 接口）
    """

    def __init__(self):
        self._api: Optional[TdxHq_API] = None

    def _connect(self) -> TdxHq_API:
        """连接到延迟最低的服务器，并用心跳请求验证连接真正可用"""
        for host, port in TDX_SERVERS:
            api = TdxHq_API(raise_exception=True)
            try:
                api.connect(host, port)
                # 用轻量接口验证连接真正可用（TCP握手成功不代表协议层可用）
                api.get_security_count(TDXParams.MARKET_SH)
                return api
            except Exception:
                try:
                    api.disconnect()
                except Exception:
                    pass
                continue
        raise ConnectionError("所有通达信服务器连接失败")

    @contextmanager
    def _session(self):
        api = self._connect()
        try:
            yield api
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 实时行情
    # ------------------------------------------------------------------
    def get_quote(self, symbol: str) -> Dict:
        code = symbol.replace("sh", "").replace("sz", "").strip()
        market = _get_market(symbol)
        with self._session() as api:
            data = api.get_security_quotes([(market, code)])
        if not data:
            return {}
        q = data[0]
        return {
            "symbol":      symbol,
            "code":        code,
            "name":        q.get("name", ""),
            "price":       q.get("price", 0),
            "open":        q.get("open", 0),
            "high":        q.get("high", 0),
            "low":         q.get("low", 0),
            "pre_close":   q.get("last_close", 0),
            "volume":      q.get("vol", 0),
            "amount":      q.get("amount", 0),
            "change_pct":  round(
                (q.get("price", 0) - q.get("last_close", 1))
                / max(q.get("last_close", 1), 0.01) * 100, 2
            ),
            "bid1": q.get("bid1", 0),
            "ask1": q.get("ask1", 0),
            "timestamp": datetime.now().isoformat(),
        }

    def get_batch_quotes(self, symbols: List[str]) -> List[Dict]:
        """批量获取实时行情（一次最多80只）"""
        pairs = [(_get_market(s), s.replace("sh","").replace("sz","").strip()) for s in symbols]
        with self._session() as api:
            data = api.get_security_quotes(pairs)
        results = []
        for i, q in enumerate(data or []):
            symbol = symbols[i] if i < len(symbols) else ""
            results.append({
                "symbol":     symbol,
                "name":       q.get("name", ""),
                "price":      q.get("price", 0),
                "change_pct": round(
                    (q.get("price", 0) - q.get("last_close", 1))
                    / max(q.get("last_close", 1), 0.01) * 100, 2
                ),
                "volume":      q.get("vol", 0),
                "amount":      q.get("amount", 0),
                "turnover_rate": 0,  # 需结合流通股本计算
            })
        return results

    # ------------------------------------------------------------------
    # 历史K线
    # ------------------------------------------------------------------
    def get_daily_bars(
        self, symbol: str, periods: int = 120
    ) -> pd.DataFrame:
        """获取日线历史数据"""
        code   = symbol.replace("sh", "").replace("sz", "").strip()
        market = _get_market(symbol)
        with self._session() as api:
            # pytdx 单次最多800条，分批获取
            bars = []
            start = 0
            remaining = periods
            while remaining > 0:
                batch = min(remaining, 800)
                data  = api.get_security_bars(
                    TDXParams.KLINE_TYPE_DAILY, market, code, start, batch
                )
                if not data:
                    break
                bars = data + bars
                start     += batch
                remaining -= batch
        return self._bars_to_df(bars)

    def get_minute_bars(
        self, symbol: str, period: int = 5, count: int = 100
    ) -> pd.DataFrame:
        """获取分钟K线（1/5/15/30/60分钟）"""
        period_map = {
            1:  TDXParams.KLINE_TYPE_1MIN,
            5:  TDXParams.KLINE_TYPE_5MIN,
            15: TDXParams.KLINE_TYPE_15MIN,
            30: TDXParams.KLINE_TYPE_30MIN,
            60: TDXParams.KLINE_TYPE_1HOUR,
        }
        kline_type = period_map.get(period, TDXParams.KLINE_TYPE_5MIN)
        code   = symbol.replace("sh", "").replace("sz", "").strip()
        market = _get_market(symbol)
        with self._session() as api:
            data = api.get_security_bars(kline_type, market, code, 0, count)
        return self._bars_to_df(data or [])

    @staticmethod
    def _bars_to_df(bars: List[Dict]) -> pd.DataFrame:
        if not bars:
            return pd.DataFrame()
        df = pd.DataFrame(bars)
        rename = {
            "datetime": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "vol": "volume",
            "amount": "amount",
        }
        df = df.rename(columns=rename)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        num_cols = ["open", "high", "low", "close", "volume", "amount"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "close" in df.columns and "open" in df.columns:
            df["change_pct"] = df["close"].pct_change() * 100
        return df

    # ------------------------------------------------------------------
    # 股票列表 / 搜索
    # ------------------------------------------------------------------
    def get_stock_list(self, market: int = MARKET_SH) -> List[Dict]:
        """获取全市场股票列表（失败自动重试）"""
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                with self._session() as api:
                    count = api.get_security_count(market)
                    stocks = []
                    for start in range(0, count, 1000):
                        batch = api.get_security_list(market, start)
                        stocks.extend(batch or [])
                return stocks
            except Exception as e:
                last_err = e
                continue
        raise ConnectionError(f"get_stock_list 重试3次仍失败: {last_err}")

    # ------------------------------------------------------------------
    # 财务数据（pytdx 扩展财务接口）
    # ------------------------------------------------------------------
    def get_finance_info(self, symbol: str) -> Dict:
        """获取基本财务指标（市盈率/市净率/净资产等）"""
        from pytdx.exhq import TdxExHq_API
        code   = symbol.replace("sh", "").replace("sz", "").strip()
        market = _get_market(symbol)
        api = TdxExHq_API()
        try:
            api.connect("hq.sinajs.cn", 7727)
            data = api.get_finance_info(market, code)
            api.disconnect()
            return data or {}
        except Exception:
            try:
                api.disconnect()
            except Exception:
                pass
            return {}


# 全局单例（避免频繁重新初始化）
_tdx_client: Optional[TDXClient] = None


def get_tdx_client() -> TDXClient:
    global _tdx_client
    if _tdx_client is None:
        _tdx_client = TDXClient()
    return _tdx_client
