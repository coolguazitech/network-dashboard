"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables or .env file.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    db_host: str = Field(default="localhost", description="DB host")
    db_port: int = Field(default=3306, description="DB port")
    db_name: str = Field(
        default="network_dashboard",
        description="DB name",
    )
    db_user: str = Field(default="admin", description="DB user")
    db_password: str = Field(default="admin", description="DB password")

    # External API
    external_api_server: str = Field(
        default="http://localhost:9000",
        description="External API server URL",
    )
    external_api_timeout: int = Field(
        default=30,
        description="API request timeout in seconds",
    )
    use_mock_api: bool = Field(
        default=False,
        description=(
            "Use in-memory MockApiClient (no external server needed). "
            "When False, uses ExternalApiClient pointing at EXTERNAL_API_SERVER."
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

    # Application
    app_name: str = Field(
        default="Network Dashboard",
        description="Application name",
    )
    app_debug: bool = Field(default=False, description="Debug mode")
    app_env: Literal["development", "production", "testing"] = Field(
        default="development",
        description="Environment",
    )
    api_prefix: str = Field(default="/api/v1", description="API prefix")

    # Config paths
    switches_config_path: Path = Field(
        default=Path("config/switches.yaml"),
        description="Path to switches config",
    )
    indicators_config_path: Path = Field(
        default=Path("config/indicators.yaml"),
        description="Path to indicators config",
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
