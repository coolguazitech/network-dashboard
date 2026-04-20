"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables or .env file.

Nested config（如 FetcherSourceConfig）使用 ``__`` 分隔符：
    FETCHER_SOURCE__FNA__BASE_URL=http://...
    FETCHER_SOURCE__FNA__TIMEOUT=30
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SourceConfig(BaseModel):
    """Connection config for an external API source."""

    base_url: str = ""
    timeout: int = 30
    token: str = ""  # FNA: Bearer token; DNA: 留空


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
        GNMSPING__TOKEN=your-gnmsping-token
        GNMSPING__BASE_URLS__F18=http://gnmsping-f18:8001
        GNMSPING__BASE_URLS__F6=http://gnmsping-f6:8001
    """

    timeout: int = 60
    endpoint: str = "/api/v1/ping"
    token: str = ""  # GNMSPING token（所有 tenant 共用）
    base_urls: dict[str, str] = {}  # TenantGroup value → base_url


class GnmsMacArpConfig(BaseModel):
    """GNMS MacARP API config.

    用於從 GNMS 批次查詢設備的 client MAC/IP 清單。
    .env 範例::

        GNMS_MACARP__BASE_URL=http://netinv.netsre.icsd.tsmc.com
        GNMS_MACARP__TOKEN=7ab602f257702f02f16815036bc8b1fb2b3d7343
        GNMS_MACARP__TIMEOUT=60
        GNMS_MACARP__BATCH_SIZE=100
    """

    base_url: str = ""
    token: str = ""
    timeout: int = 60
    batch_size: int = 100  # API 每次最多查詢設備數



class FetcherEndpointConfig(BaseModel):
    """Per-fetcher endpoint templates.

    屬性名必須與 scheduler.yaml 的 fetcher key 完全一致（get_* 命名）。
    ConfiguredFetcher 透過 getattr(settings.fetcher_endpoint, fetch_type) 查找。

    FNA endpoint: str 型別，所有廠牌共用，支援 {switch_ip} 佔位符。
    DNA endpoint: str | dict[str, str] 型別：
      - dict 模式（production）: key 為 device_type ("hpe"/"ios"/"nxos")
        .env 用 __HPE/__IOS/__NXOS 後綴設定：
          FETCHER_ENDPOINT__GET_FAN__HPE=/api/v1/hpe/environment/display_fan
      - str 模式（mock）: 單一模板，所有 device_type 共用
        .env 直接設定：FETCHER_ENDPOINT__GET_FAN=/api/get_fan

    佔位符會從 FetchContext 帶入路徑。
    模板含 '?' → 顯式 query params（如 ?hosts={switch_ip}）；
    模板不含 '?' → 未消耗變數自動附加為 query params（Mock 相容）。
    """

    # FNA (5) — 所有廠牌共用，IP 在 path 中
    get_gbic_details: str = "/switch/network/get_gbic_details/{switch_ip}"
    get_channel_group: str = "/switch/network/get_channel_group/{switch_ip}"
    get_error_count: str = "/switch/network/get_interface_error_count/{switch_ip}"
    get_static_acl: str = "/switch/network/get_static_acl/{switch_ip}"
    get_dynamic_acl: str = "/switch/network/get_dynamic_acl/{switch_ip}"
    # DNA (7) — per-device-type，IP 透過 ?hosts={switch_ip} 顯式帶入
    get_mac_table: str | dict[str, str] = {
        "hpe": "/api/v1/hpe/macaddress/display_macaddress?hosts={switch_ip}",
        "ios": "/api/v1/ios/macaddress/show_mac_address_table?hosts={switch_ip}",
        "nxos": "/api/v1/nxos/macaddress/show_mac_address_table?hosts={switch_ip}",
    }
    get_fan: str | dict[str, str] = {
        "hpe": "/api/v1/hpe/environment/display_fan?hosts={switch_ip}",
        "ios": "/api/v1/ios/environment/show_env_fan?hosts={switch_ip}",
        "nxos": "/api/v1/nxos/environment/show_environment_fan?hosts={switch_ip}",
    }
    get_power: str | dict[str, str] = {
        "hpe": "/api/v1/hpe/environment/display_power?hosts={switch_ip}",
        "ios": "/api/v1/ios/environment/show_env_power?hosts={switch_ip}",
        "nxos": "/api/v1/nxos/environment/show_environment_power?hosts={switch_ip}",
    }
    get_version: str = "/switch/network/get_install_active/{switch_ip}"
    get_interface_status: str | dict[str, str] = {
        "hpe": "/api/v1/hpe/interface/display_interface_brief?hosts={switch_ip}",
        "ios": "/api/v1/ios/interface/show_interface_status?hosts={switch_ip}",
        "nxos": "/api/v1/nxos/interface/show_interface_status?hosts={switch_ip}",
    }
    get_uplink_lldp: str | dict[str, str] = {
        "hpe": "/api/v1/hpe/neighbor/display_lldp_neighbor-information_list?hosts={switch_ip}",
        "ios": "/api/v1/ios/neighbor/show_lldp_neighbors?hosts={switch_ip}",
        "nxos": "/api/v1/nxos/neighbor/show_lldp_neighbors?hosts={switch_ip}",
    }
    get_uplink_cdp: str | dict[str, str] = {
        "ios": "/api/v1/ios/neighbor/show_cdp_neighbors?hosts={switch_ip}",
        "nxos": "/api/v1/nxos/neighbor/show_cdp_neighbors?hosts={switch_ip}",
    }


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
    db_pool_size: int = Field(
        default=10,
        description="SQLAlchemy connection pool size (base connections kept open).",
    )
    db_max_overflow: int = Field(
        default=20,
        description="SQLAlchemy max overflow connections beyond pool_size.",
    )

    # Fetcher Sources (per-source connection config)
    fetcher_source: FetcherSourceConfig = FetcherSourceConfig()

    # Fetcher Endpoints (per-fetcher endpoint templates)
    fetcher_endpoint: FetcherEndpointConfig = FetcherEndpointConfig()

    # GNMS Ping (per-tenant base_url + 統一 endpoint)
    gnmsping: GnmsPingConfig = GnmsPingConfig()

    # GNMS MacARP (批次查詢設備 client 清單)
    gnms_macarp: GnmsMacArpConfig = GnmsMacArpConfig()


    # Scheduler toggle (set to false for API-only replicas in K8s)
    enable_scheduler: bool = Field(
        default=True,
        description="Enable background scheduler. Set false for API-only pods in K8s split deployment.",
    )

    # Scheduling
    min_round_gap: int = Field(
        default=10,
        description="Minimum seconds between collection rounds. "
        "After a round finishes, wait at least this long before starting the next. "
        "Keeps the loop from hammering devices when rounds are very fast (few devices).",
    )
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

    # Collection Mode
    collection_mode: str = Field(
        default="api",
        description="Collection mode: 'api' (REST API fetchers) or 'snmp' (direct SNMP polling)",
    )

    # SNMP Settings (only used when collection_mode=snmp)
    snmp_communities: str = Field(
        default="tccd03ro,public",
        description="Comma-separated SNMP v2c community strings to try, in order",
    )
    snmp_port: int = Field(default=161, description="SNMP target port")
    snmp_timeout: float = Field(
        default=3.0,
        description="SNMP PDU timeout in seconds. "
        "LibreNMS uses 1s. Most responsive devices reply in <500ms. "
        "Combined with retries, per-PDU hard cap = timeout*(retries+1)+2.",
    )
    snmp_retries: int = Field(
        default=1,
        description="SNMP PDU retry count. With timeout=3s, retries=1: "
        "per-PDU hard cap = 3*(1+1)+2 = 8s (was 26s with 8s/2 retries).",
    )
    snmp_max_repetitions: int = Field(
        default=25, description="SNMP GETBULK max-repetitions per PDU",
    )
    snmp_engine: str = Field(
        default="subprocess",
        description="SNMP engine backend: 'subprocess' (net-snmp CLI, recommended) "
        "or 'pysnmp' (legacy, limited concurrency).",
    )
    snmp_concurrency: int = Field(
        default=50,
        description="Global max concurrent SNMP device walks across ALL jobs. "
        "subprocess engine: 50+ is safe (process-isolated). "
        "pysnmp engine: keep <=20 (shared event loop, callback races).",
    )
    snmp_walk_timeout: float = Field(
        default=30.0,
        description="Overall timeout for a single SNMP walk (seconds). "
        "Large tables (MAC on 48-port) typically complete in 5-15s. "
        "30s is generous; must be < per-device hard timeout to allow "
        "multiple collectors to complete within the hard timeout budget.",
    )
    snmp_collector_retries: int = Field(
        default=1,
        description="Collector-level retry count on walk timeout. "
        "With walk_timeout=30s, 1 retry = max 60s per collector.",
    )
    snmp_negative_ttl: float = Field(
        default=600.0,
        description="Negative cache TTL (seconds) for SNMP-unreachable devices. "
        "During this period, unreachable devices are skipped without probing. "
        "600s = skip ~3 fast_rounds before re-probing. For maintenance scenarios "
        "where most devices are unreachable, longer TTL avoids wasting ~96s/round "
        "re-probing 380+ known-down devices.",
    )
    snmp_mock: bool = Field(
        default=False,
        description="Use mock SNMP engine (no real devices needed)",
    )

    @property
    def snmp_community_list(self) -> list[str]:
        """Parse comma-separated community strings into a list."""
        return [c.strip() for c in self.snmp_communities.split(",") if c.strip()]

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
