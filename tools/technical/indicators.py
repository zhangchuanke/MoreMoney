"""
技术指标计算工具
包含：MA/EMA/MACD/KDJ/RSI/BOLL/ATR/量比/支撑压力位
"""
from typing import Dict, List
import pandas as pd
import numpy as np


class TechnicalIndicators:

    def compute_all(self, df: pd.DataFrame) -> Dict:
        """一次性计算所有指标，返回最新一根K线的指标字典"""
        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        vol   = df["volume"]

        ind: Dict = {}

        # 均线
        for n in [5, 10, 20, 60, 120]:
            ma = close.rolling(n).mean()
            ind[f"ma{n}"] = float(ma.iloc[-1]) if len(ma) >= n else float(close.iloc[-1])

        # EMA
        ind["ema12"] = float(close.ewm(span=12).mean().iloc[-1])
        ind["ema26"] = float(close.ewm(span=26).mean().iloc[-1])

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif   = ema12 - ema26
        dea   = dif.ewm(span=9, adjust=False).mean()
        ind["macd"]        = float(dif.iloc[-1])
        ind["macd_signal"] = float(dea.iloc[-1])
        ind["macd_hist"]   = float((dif - dea).iloc[-1] * 2)

        # RSI(14)
        ind["rsi14"] = float(self._rsi(close, 14))
        ind["rsi6"]  = float(self._rsi(close, 6))

        # KDJ
        k, d, j = self._kdj(high, low, close)
        ind["kdj_k"] = float(k)
        ind["kdj_d"] = float(d)
        ind["kdj_j"] = float(j)

        # 布林带(20, 2)
        mid  = close.rolling(20).mean()
        std  = close.rolling(20).std()
        ind["boll_upper"] = float((mid + 2 * std).iloc[-1])
        ind["boll_mid"]   = float(mid.iloc[-1])
        ind["boll_lower"] = float((mid - 2 * std).iloc[-1])

        # ATR(14)
        ind["atr14"] = float(self._atr(high, low, close, 14))

        # 量比（当日量 / 近5日均量）
        avg_vol = vol.iloc[-6:-1].mean()
        ind["volume_ratio"] = float(vol.iloc[-1] / avg_vol) if avg_vol > 0 else 1.0

        # OBV
        obv = (np.sign(close.diff()) * vol).cumsum()
        ind["obv"] = float(obv.iloc[-1])

        return ind

    def find_support_resistance(
        self, df: pd.DataFrame, mode: str = "support", window: int = 20
    ) -> List[float]:
        """简单支撑/压力位：近N根K线的局部极值"""
        close = df["close"]
        levels = []
        for i in range(window, len(close) - window):
            if mode == "support":
                if close.iloc[i] == close.iloc[i-window:i+window].min():
                    levels.append(round(float(close.iloc[i]), 3))
            else:
                if close.iloc[i] == close.iloc[i-window:i+window].max():
                    levels.append(round(float(close.iloc[i]), 3))
        return sorted(set(levels))[-3:] if levels else []

    # ------------------------------------------------------------------
    @staticmethod
    def _rsi(close: pd.Series, period: int) -> float:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

    @staticmethod
    def _kdj(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int = 9
    ):
        low_min  = low.rolling(period).min()
        high_max = high.rolling(period).max()
        rsv = (close - low_min) / (high_max - low_min + 1e-9) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        j = 3 * k - 2 * d
        return float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])

    @staticmethod
    def _atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> float:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
