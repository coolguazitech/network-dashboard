"""Mock Server 設定。"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class MockServerSettings(BaseSettings):
    """Mock API Server 的配置。讀取同一個 .env 檔。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DB 連線（與主應用共用同一個 MariaDB）
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "netora"
    db_user: str = "admin"
    db_password: str = "admin"

    # 模式：convergence（時間收斂）或 steady_state（穩態）
    mock_mode: str = "convergence"

    # 收斂時間常數 T（秒）— convergence 模式用
    mock_converge_time: int = 7200

    # 穩態模式設定 — steady_state 模式用
    mock_steady_failure_rate: float = 0.05  # 5% 設備+API 組合會故障
    mock_steady_onset_range: float = 3600   # 故障出現時間分散在 1 小時內

    # 服務器設定
    mock_server_port: int = 9999

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = MockServerSettings()
