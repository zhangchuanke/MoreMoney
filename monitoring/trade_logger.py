"""
交易日志记录器
"""
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from config.settings import settings


def setup_logger() -> logging.Logger:
    Path("logs").mkdir(exist_ok=True)
    logger = logging.getLogger("MoreMoney")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 文件 handler
    fh = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    # 控制台 handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


class TradeLogger:

    def __init__(self):
        self.logger = setup_logger()

    def log_state(self, state: Dict) -> None:
        iteration = state.get("iteration_count", 0)
        risk = state.get("risk_level", "N/A")
        sentiment = state.get("market_sentiment", "N/A")
        self.logger.info(
            f"[Iter {iteration}] risk={risk} sentiment={sentiment} "
            f"signals={len(state.get('signals', []))} "
            f"decisions={len(state.get('decisions', []))}"
        )

    def log_orders(self, orders: list) -> None:
        for order in orders:
            self.logger.info(
                f"[ORDER] {order.get('action','?').upper()} "
                f"{order.get('symbol','?')} x{order.get('quantity','?')} "
                f"@ {order.get('filled_price', order.get('price', '?'))} "
                f"status={order.get('status','?')}"
            )

    def log_error(self, msg: str) -> None:
        self.logger.error(msg)

    def log_info(self, msg: str) -> None:
        self.logger.info(msg)
