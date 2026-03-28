"""
K线形态识别工具
识别：锤头/倒锤头/吞没/十字星/跳空缺口/头肩顶底等
"""
from typing import List
import pandas as pd
import numpy as np


class PatternRecognition:

    def detect(self, df: pd.DataFrame) -> List[str]:
        """识别最近K线中的形态，返回形态名称列表"""
        patterns = []
        if len(df) < 5:
            return patterns

        o = df["open"].values
        h = df["high"].values
        l = df["low"].values
        c = df["close"].values
        v = df["volume"].values

        # 最近几根K线
        i = -1  # 最新

        body     = abs(c[i] - o[i])
        upper_wick = h[i] - max(c[i], o[i])
        lower_wick = min(c[i], o[i]) - l[i]
        total_range = h[i] - l[i] + 1e-9

        # 1. 锤头（bullish）：下影线 >= 2*实体，上影线小
        if lower_wick >= 2 * body and upper_wick <= body * 0.3 and c[i-1] < o[i-1]:
            patterns.append("hammer_bullish")

        # 2. 倒锤头 / 流星（bearish）
        if upper_wick >= 2 * body and lower_wick <= body * 0.3 and c[i-1] > o[i-1]:
            patterns.append("shooting_star_bearish")

        # 3. 吞没形态
        if c[i-1] < o[i-1] and c[i] > o[i]:  # 前阴后阳
            if c[i] > o[i-1] and o[i] < c[i-1]:
                patterns.append("bullish_engulfing")
        if c[i-1] > o[i-1] and c[i] < o[i]:  # 前阳后阴
            if c[i] < o[i-1] and o[i] > c[i-1]:
                patterns.append("bearish_engulfing")

        # 4. 十字星
        if body / total_range < 0.1:
            patterns.append("doji")

        # 5. 跳空缺口
        if l[i] > h[i-1]:
            patterns.append("gap_up")
        if h[i] < l[i-1]:
            patterns.append("gap_down")

        # 6. 量能异常（放量 3 倍以上）
        avg_vol = np.mean(v[-6:-1])
        if v[i] > avg_vol * 3:
            patterns.append("volume_surge")
        if v[i] < avg_vol * 0.3:
            patterns.append("volume_dry_up")

        # 7. 连续3根阳线/阴线
        if all(c[-3:] > o[-3:]):
            patterns.append("three_white_soldiers")
        if all(c[-3:] < o[-3:]):
            patterns.append("three_black_crows")

        return patterns
