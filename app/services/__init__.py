"""
Services package.

Provides external API client, data collection, and scheduler services.
"""
from app.services.api_client import (
    BaseApiClient,
    ExternalApiClient,
    MockApiClient,
    get_api_client,
)
from app.services.data_collection import (
    DataCollectionService,
    get_collection_service,
)
from app.services.scheduler import (
    SchedulerService,
    get_scheduler_service,
    setup_scheduled_jobs,
)

__all__ = [
    # API Client
    "BaseApiClient",
    "ExternalApiClient",
    "MockApiClient",
    "get_api_client",
    # Data Collection
    "DataCollectionService",
    "get_collection_service",
    # Scheduler
    "SchedulerService",
    "get_scheduler_service",
    "setup_scheduled_jobs",
]
