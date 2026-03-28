"""
全局配置 - pydantic-settings >=2.7

pydantic v2 变化:
  - BaseSettings 从 pydantic_settings 导入
  - 使用 model_config = SettingsConfigDict() 替代内部 Config 类
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === LLM ===
    DASHSCOPE_API_KEY: str = ""
    QWEN_MODEL: str = "qwen-max"
    QWEN_TURBO_MODEL: str = "qwen-turbo"
    QWEN_LONG_MODEL: str = "qwen-long"

    # === 交易模式 ===
    TRADING_MODE: str = "paper"           # paper | live
    INITIAL_CAPITAL: float = 1_000_000.0

    # === 券商（迅投QMT）===
    XT_ACCOUNT: str = ""
    XT_CLIENT_PATH: str = "C:/国金证券QMT交易端/userdata_mini"

    # === 数据源 ===
    TUSHARE_TOKEN: Optional[str] = None
    AKSHARE_TIMEOUT: int = 30

    # === 存储 ===
    DB_PATH: str = "storage/database/memory.db"
    CHROMA_PATH: str = "storage/vector_store"
    REDIS_URL: str = "redis://localhost:6379/0"

    # === 运行参数 ===
    MAX_ITERATIONS_PER_DAY: int = 20
    ANALYSIS_INTERVAL_MINUTES: int = 15
    TOP_N_STOCKS: int = 20
    UNIVERSE_SIZE: int = 300

    # === 日志 ===
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/trading.log"


settings = Settings()
