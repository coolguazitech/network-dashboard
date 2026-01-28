"""
Services package.

Provides external API client, data collection, client collection, and scheduler services.
"""
from app.services.api_client import (
    BaseApiClient,
    ExternalApiClient,
    MockApiClient,
    get_api_client,
)
from app.services.client_collection_service import (
    ClientCollectionService,
    get_client_collection_service,
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
    # Client Collection
    "ClientCollectionService",
    "get_client_collection_service",
    # Data Collection
    "DataCollectionService",
    "get_collection_service",
    # Scheduler
    "SchedulerService",
    "get_scheduler_service",
    "setup_scheduled_jobs",
]
