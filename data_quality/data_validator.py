"""
数据质量校验器

双源交叉比对 pytdx 与 akshare 行情数据，
支持自动降级使用单一数据源 / 暂停不可信标的交易。
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataSource(str, Enum):
    AKSHARE   = "akshare"
    PYTDX     = "pytdx"
    DEGRADED  = "degraded"
    SUSPENDED = "suspended"


class DataQualityLevel(str, Enum):
    GOOD      = "good"
    DEGRADED  = "degraded"
    SUSPENDED = "suspended"


@dataclass
class DataQualityResult:
    symbol:           str
    quality_level:    DataQualityLevel
    active_source:    DataSource
    price_deviation:  float          = 0.0
    volume_deviation: float          = 0.0
    anomalies:        List[str]      = field(default_factory=list)
    recommendation:   str            = ""
    akshare_data:     Optional[Dict] = None
    pytdx_data:       Optional[Dict] = None
    merged_data:      Optional[Dict] = None

    @property
    def is_tradable(self) -> bool:
        return self.quality_level != DataQualityLevel.SUSPENDED

    @property
    def position_ratio(self) -> float:
        return {
            DataQualityLevel.GOOD:      1.0,
            DataQualityLevel.DEGRADED:  0.5,
            DataQualityLevel.SUSPENDED: 0.0,
        }[self.quality_level]


PRICE_DEVIATION_WARN   = 0.005
PRICE_DEVIATION_ERROR  = 0.020
VOLUME_DEVIATION_WARN  = 0.10
VOLUME_DEVIATION_ERROR = 0.30
STALENESS_SECONDS      = 300
MIN_TRADING_VOLUME     = 1_000

_TDX_SERVERS: List[Tuple[str, int]] = [
    ("119.147.212.81",  7709),
    ("121.14.110.210",  7709),
    ("180.153.18.170",  7709),
    ("202.108.253.130", 7709),
]


class DataQualityValidator:
    """
    数据质量校验器核心类。

    用法::

        validator = DataQualityValidator()
        results = validator.validate_batch(["000001", "600519"])
        tradable, suspended = validator.filter_tradable(results)
        data = results["000001"].merged_data
    """

    def __init__(
        self,
        price_warn:   float = PRICE_DEVIATION_WARN,
        price_error:  float = PRICE_DEVIATION_ERROR,
        volume_warn:  float = VOLUME_DEVIATION_WARN,
        volume_error: float = VOLUME_DEVIATION_ERROR,
        staleness_s:  int   = STALENESS_SECONDS,
    ):
        self.price_warn   = price_warn
        self.price_error  = price_error
        self.volume_warn  = volume_warn
        self.volume_error = volume_error
        self.staleness_s  = staleness_s
        self._best_server: Optional[Tuple[str, int]] = None

    def validate(self, symbol: str, date: Optional[str] = None) -> DataQualityResult:
        ak_raw  = self._fetch_akshare(symbol, date)
        tdx_raw = self._fetch_pytdx(symbol, date)
        return self._cross_validate(symbol, ak_raw, tdx_raw)

    def validate_batch(
        self, symbols: List[str], date: Optional[str] = None
    ) -> Dict[str, DataQualityResult]:
        results: Dict[str, DataQualityResult] = {}
        for sym in symbols:
            try:
                results[sym] = self.validate(sym, date)
            except Exception as exc:
                logger.exception("validate %s failed", sym)
                results[sym] = DataQualityResult(
                    symbol=sym,
                    quality_level=DataQualityLevel.SUSPENDED,
                    active_source=DataSource.SUSPENDED,
                    anomalies=[f"校验异常: {exc}"],
                    recommendation="双源均失败，暂停该标的今日交易",
                )
        return results

    def filter_tradable(
        self, results: Dict[str, DataQualityResult]
    ) -> Tuple[List[str], List[str]]:
        tradable  = [s for s, r in results.items() if r.is_tradable]
        suspended = [s for s, r in results.items() if not r.is_tradable]
        if suspended:
            logger.warning("以下标的数据质量不合格，已暂停: %s", ", ".join(suspended))
        return tradable, suspended

    def _fetch_akshare(self, symbol: str, date: Optional[str]) -> Optional[Dict]:
        try:
            import akshare as ak  # type: ignore
            today = pd.Timestamp.today().strftime("%Y%m%d")
            qdate = (date or today).replace("-", "")
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily",
                start_date=qdate, end_date=qdate, adjust="",
            )
            if df is None or df.empty:
                return None
            row = df.iloc[-1]
            return {
                "open":     float(row.get("开盘",  0)),
                "high":     float(row.get("最高",  0)),
                "low":      float(row.get("最低",  0)),
                "close":    float(row.get("收盘",  0)),
                "volume":   float(row.get("成交量", 0)),
                "amount":   float(row.get("成交额", 0)),
                "source":   DataSource.AKSHARE,
                "fetch_ts": time.time(),
            }
        except Exception as exc:
            logger.warning("[akshare] fetch failed [%s]: %s", symbol, exc)
            return None

    def _fetch_pytdx(self, symbol: str, date: Optional[str]) -> Optional[Dict]:
        try:
            from pytdx.hq import TdxHq_API  # type: ignore
            ip, port = self._resolve_server()
            api = TdxHq_API()
            with api.connect(ip, port):
                market = 1 if symbol.startswith("6") else 0
                data   = api.get_security_bars(9, market, symbol, 0, 1)
            if not data:
                return None
            bar = data[0]
            return {
                "open":     float(bar["open"]),
                "high":     float(bar["high"]),
                "low":      float(bar["low"]),
                "close":    float(bar["close"]),
                "volume":   float(bar.get("vol", 0)),
                "amount":   float(bar.get("amount", 0)),
                "source":   DataSource.PYTDX,
                "fetch_ts": time.time(),
            }
        except Exception as exc:
            logger.warning("[pytdx] fetch failed [%s]: %s", symbol, exc)
            return None

    def _resolve_server(self) -> Tuple[str, int]:
        if self._best_server is not None:
            return self._best_server
        best: Tuple[str, int] = _TDX_SERVERS[0]
        best_lat = float("inf")
        for ip, port in _TDX_SERVERS:
            try:
                t0 = time.perf_counter()
                with socket.create_connection((ip, port), timeout=1):
                    pass
                lat = time.perf_counter() - t0
                if lat < best_lat:
                    best_lat = lat
                    best = (ip, port)
            except OSError:
                continue
        self._best_server = best
        return best

    @staticmethod
    def _rel_diff(a: float, b: float) -> float:
        denom = max(abs(a), abs(b), 1e-9)
        return abs(a - b) / denom

    def _sanitize(self, raw: Dict) -> Dict:
        return {k: v for k, v in raw.items() if k not in ("source", "fetch_ts")}

    def _cross_validate(
        self,
        symbol:   str,
        ak_data:  Optional[Dict],
        tdx_data: Optional[Dict],
    ) -> DataQualityResult:
        anomalies: List[str] = []

        if ak_data is None and tdx_data is None:
            return DataQualityResult(
                symbol=symbol,
                quality_level=DataQualityLevel.SUSPENDED,
                active_source=DataSource.SUSPENDED,
                anomalies=["akshare and pytdx both unavailable"],
                recommendation="双源均失败，暂停该标的今日交易",
            )

        if ak_data is None:
            return DataQualityResult(
                symbol=symbol,
                quality_level=DataQualityLevel.DEGRADED,
                active_source=DataSource.PYTDX,
                anomalies=["akshare unavailable, degraded to pytdx"],
                recommendation="建议减少仓位至常规的50%",
                pytdx_data=tdx_data,
                merged_data=self._sanitize(tdx_data),  # type: ignore[arg-type]
            )

        if tdx_data is None:
            return DataQualityResult(
                symbol=symbol,
                quality_level=DataQualityLevel.DEGRADED,
                active_source=DataSource.AKSHARE,
                anomalies=["pytdx unavailable, degraded to akshare"],
                recommendation="建议减少仓位至常规的50%",
                akshare_data=ak_data,
                merged_data=self._sanitize(ak_data),
            )

        ak_close  = ak_data["close"]
        tdx_close = tdx_data["close"]
        price_dev = self._rel_diff(ak_close, tdx_close) if ak_close and tdx_close else 0.0

        ak_vol  = ak_data["volume"]
        tdx_vol = tdx_data["volume"]
        vol_dev = self._rel_diff(ak_vol, tdx_vol) if ak_vol and tdx_vol else 0.0

        if price_dev >= self.price_warn:
            anomalies.append(f"price deviation {price_dev:.2%} (ak={ak_close}, tdx={tdx_close})")
        if vol_dev >= self.volume_warn:
            anomalies.append(f"volume deviation {vol_dev:.2%} (ak={ak_vol:.0f}, tdx={tdx_vol:.0f})")
        for src, d in (("akshare", ak_data), ("pytdx", tdx_data)):
            if d["close"] <= 0:
                anomalies.append(f"{src} close price is zero or negative")
        for src, d in (("akshare", ak_data), ("pytdx", tdx_data)):
            if 0 < d["volume"] < MIN_TRADING_VOLUME:
                anomalies.append(f"{src} volume {d['volume']:.0f} lots below threshold")
        now = time.time()
        for src, d in (("akshare", ak_data), ("pytdx", tdx_data)):
            age = now - d.get("fetch_ts", now)
            if age > self.staleness_s:
                anomalies.append(f"{src} quote stale {age:.0f}s")

        if price_dev >= self.price_error or vol_dev >= self.volume_error:
            return DataQualityResult(
                symbol=symbol,
                quality_level=DataQualityLevel.DEGRADED,
                active_source=DataSource.AKSHARE,
                price_deviation=price_dev,
                volume_deviation=vol_dev,
                anomalies=anomalies,
                recommendation="双源偏差过大，降级使用 akshare，建议仓位减至50%",
                akshare_data=ak_data,
                pytdx_data=tdx_data,
                merged_data=self._sanitize(ak_data),
            )

        merged: Dict = {**self._sanitize(ak_data)}
        if merged.get("volume", 0) == 0 and tdx_vol > 0:
            merged["volume"] = tdx_vol
        if merged.get("amount", 0) == 0 and tdx_data.get("amount", 0) > 0:
            merged["amount"] = tdx_data["amount"]

        return DataQualityResult(
            symbol=symbol,
            quality_level=DataQualityLevel.GOOD,
            active_source=DataSource.AKSHARE,
            price_deviation=price_dev,
            volume_deviation=vol_dev,
            anomalies=anomalies,
            recommendation="cross-validation passed" if not anomalies else "minor deviation recorded",
            akshare_data=ak_data,
            pytdx_data=tdx_data,
            merged_data=merged,
        )
