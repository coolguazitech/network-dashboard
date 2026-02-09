"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables or .env file.

Nested config（如 FetcherSourceConfig）使用 ``__`` 分隔符：
    FETCHER_SOURCE__FNA__BASE_URL=http://...
    FETCHER_SOURCE__FNA__TIMEOUT=30
"""
from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SourceConfig(BaseModel):
    """Connection config for an external API source."""

    base_url: str = ""
    timeout: int = 30


class FetcherSourceConfig(BaseModel):
    """All external API source configs (FNA / DNA / GNMSPing)."""

    fna: SourceConfig = SourceConfig()
    dna: SourceConfig = SourceConfig()
    gnmsping: SourceConfig = SourceConfig(timeout=60)


class FetcherEndpointConfig(BaseModel):
    """Per-fetcher endpoint templates.

    支援佔位符: {switch_ip}, {device_type}, {tenant_group} 等
    （FetchContext.params 中的任意 key 亦可用）。

    佔位符會從 FetchContext 帶入路徑；未被消耗的變數自動成為 query params。

    .env 設定範例::

        FETCHER_ENDPOINT__TRANSCEIVER=/api/v1/transceiver/{switch_ip}
        FETCHER_ENDPOINT__VERSION=/api/v1/version/{switch_ip}
    """

    # FNA
    transceiver: str = "/api/v1/transceiver/{switch_ip}"
    port_channel: str = "/api/v1/port-channel/{switch_ip}"
    acl: str = "/api/v1/acl/{switch_ip}"
    # DNA
    version: str = "/api/v1/version/{switch_ip}"
    uplink: str = "/api/v1/neighbors/{switch_ip}"
    fan: str = "/api/v1/fan/{switch_ip}"
    power: str = "/api/v1/power/{switch_ip}"
    error_count: str = "/api/v1/error-count/{switch_ip}"
    mac_table: str = "/api/v1/mac-table/{switch_ip}"
    arp_table: str = "/api/v1/arp-table/{switch_ip}"
    interface_status: str = "/api/v1/interface-status/{switch_ip}"
    # GNMSPing
    ping: str = "/api/v1/ping/batch"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # Database
    db_host: str = Field(default="localhost", description="DB host")
    db_port: int = Field(default=3306, description="DB port")
    db_name: str = Field(
        default="netora",
        description="DB name",
    )
    db_user: str = Field(default="admin", description="DB user")
    db_password: str = Field(default="admin", description="DB password")

    # Fetcher Sources (per-source connection config)
    fetcher_source: FetcherSourceConfig = FetcherSourceConfig()

    # Fetcher Endpoints (per-fetcher endpoint templates)
    fetcher_endpoint: FetcherEndpointConfig = FetcherEndpointConfig()

    use_mock_api: bool = Field(
        default=False,
        description=(
            "Use in-memory MockFetcher (no external server needed). "
            "When False, uses ConfiguredFetcher calling external APIs "
            "defined in FETCHER_SOURCE / FETCHER_ENDPOINT."
        ),
    )
    mock_ping_converge_time: int = Field(
        default=600,
        description=(
            "Mock ping convergence time in seconds. "
            "Devices become reachable within this time window. "
            "Default is 600 (10 minutes). Set to 0 for instant reachability."
        ),
    )

    # Scheduling
    collection_interval_seconds: int = Field(
        default=120,
        description="Default data collection interval in seconds (fallback if scheduler.yaml omits interval).",
    )
    checkpoint_interval_minutes: int = Field(
        default=60,
        description="Checkpoint snapshot interval in minutes.",
    )
    frontend_polling_interval_seconds: int = Field(
        default=60,
        description="Frontend polling interval in seconds.",
    )
    max_collection_days: int = Field(
        default=7,
        description="Maximum collection days per maintenance (auto-stop after this period).",
    )

    # JWT / Auth
    jwt_secret: str = Field(
        default="CHANGE-THIS-IN-PRODUCTION",
        description="JWT signing secret key (use strong random string in production)",
    )
    jwt_expire_hours: int = Field(
        default=24,
        description="JWT token expiration time in hours",
    )

    # Application
    app_name: str = Field(
        default="NETORA",
        description="Application name",
    )
    app_debug: bool = Field(default=False, description="Debug mode")
    api_prefix: str = Field(default="/api/v1", description="API prefix")

    # Timezone
    timezone: str = Field(
        default="Asia/Taipei",
        description="Application timezone (e.g., 'Asia/Taipei', 'UTC', 'America/New_York')",
    )

    # Indicator Thresholds — Operational Status (fan / power)
    operational_healthy_statuses: str = Field(
        default="ok,good,normal,online,active",
        description="逗號分隔的健康狀態值（fan/power 共用）",
    )

    @property
    def operational_healthy_set(self) -> set[str]:
        """解析為 set，供 fan/power indicator 使用。"""
        return {s.strip().lower() for s in self.operational_healthy_statuses.split(",") if s.strip()}

    # Indicator Thresholds — Error Count
    # 換設備（is_replaced=True）→ 必須為 0
    # 未換設備（is_replaced=False）→ 容許閾值
    error_count_same_device_max: int = Field(
        default=100,
        description="未換設備時（is_replaced=False），每個 error 欄位的容許上限",
    )

    # Indicator Thresholds — Transceiver (雙向閾值)
    transceiver_tx_power_min: float = Field(
        default=-12.0,
        description="Transceiver minimum TX power (dBm)",
    )
    transceiver_tx_power_max: float = Field(
        default=3.0,
        description="Transceiver maximum TX power (dBm)",
    )
    transceiver_rx_power_min: float = Field(
        default=-18.0,
        description="Transceiver minimum RX power (dBm)",
    )
    transceiver_rx_power_max: float = Field(
        default=1.0,
        description="Transceiver maximum RX power (dBm)",
    )
    transceiver_temperature_min: float = Field(
        default=0.0,
        description="Transceiver minimum temperature (°C)",
    )
    transceiver_temperature_max: float = Field(
        default=70.0,
        description="Transceiver maximum temperature (°C)",
    )
    transceiver_voltage_min: float = Field(
        default=3.0,
        description="Transceiver minimum voltage (V)",
    )
    transceiver_voltage_max: float = Field(
        default=3.6,
        description="Transceiver maximum voltage (V)",
    )

    @property
    def database_url(self) -> str:
        """Build database connection URL."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def async_database_url(self) -> str:
        """Build async database connection URL."""
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance (Singleton pattern)."""
    return Settings()


# Global settings instance
settings = get_settings()
