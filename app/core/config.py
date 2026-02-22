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
    """All external API source configs (FNA / DNA)."""

    fna: SourceConfig = SourceConfig()
    dna: SourceConfig = SourceConfig()


class GnmsPingConfig(BaseModel):
    """GNMS Ping per-tenant config.

    每個 tenant_group 有自己的 base_url，endpoint 相同。
    .env 範例::

        GNMSPING__TIMEOUT=60
        GNMSPING__ENDPOINT=/api/v1/ping
        GNMSPING__BASE_URLS__F18=http://gnmsping-f18:8001
        GNMSPING__BASE_URLS__F6=http://gnmsping-f6:8001
    """

    timeout: int = 60
    endpoint: str = "/api/v1/ping"
    base_urls: dict[str, str] = {}  # TenantGroup value → base_url


class FetcherEndpointConfig(BaseModel):
    """Per-fetcher endpoint templates.

    屬性名必須與 scheduler.yaml 的 fetcher key 完全一致（get_* 命名）。
    ConfiguredFetcher 透過 getattr(settings.fetcher_endpoint, fetch_type) 查找。

    支援佔位符: {switch_ip}, {device_type}, {tenant_group} 等。
    佔位符會從 FetchContext 帶入路徑；未被消耗的變數自動成為 query params。

    .env 設定範例::

        FETCHER_ENDPOINT__GET_FAN=/api/v1/fan/{switch_ip}
        FETCHER_ENDPOINT__GET_GBIC_DETAILS=/api/v1/transceiver/{switch_ip}
    """

    # FNA (7)
    get_gbic_details: str = "/api/v1/transceiver/{switch_ip}"
    get_channel_group: str = "/api/v1/port-channel/{switch_ip}"
    get_uplink: str = "/api/v1/neighbors/{switch_ip}"
    get_error_count: str = "/api/v1/error-count/{switch_ip}"
    get_static_acl: str = "/api/v1/acl/static/{switch_ip}"
    get_dynamic_acl: str = "/api/v1/acl/dynamic/{switch_ip}"
    # DNA (4)
    get_mac_table: str = "/api/v1/mac-table/{switch_ip}"
    get_fan: str = "/api/v1/fan/{switch_ip}"
    get_power: str = "/api/v1/power/{switch_ip}"
    get_version: str = "/api/v1/version/{switch_ip}"
    # DNA (1)
    get_interface_status: str = "/api/v1/interface-status/{switch_ip}"


class MinioConfig(BaseModel):
    """MinIO / S3-compatible object storage config."""

    endpoint: str = "minio:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "netora-uploads"
    secure: bool = False
    region: str = ""
    public_url: str = ""  # 外部存取 URL（Ingress），空值則自動組合 endpoint


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # Object Storage (MinIO)
    minio: MinioConfig = MinioConfig()

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

    # GNMS Ping (per-tenant base_url + 統一 endpoint)
    gnmsping: GnmsPingConfig = GnmsPingConfig()

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
    retention_days_after_deactivation: int = Field(
        default=7,
        description="Days to keep collection data after maintenance is deactivated.",
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
    # 邏輯：delta = 最新變化點 - 上一個變化點，delta > 0 即異常（無閾值設定）

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
