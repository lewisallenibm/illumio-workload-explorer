# Import all illumio models here so SQLAlchemy's mapper registry
# has every class available before any relationship is resolved.
from app.models.illumio.illumio_workload import IllumioWorkload
from app.models.illumio.illumio_interface import IllumioInterface
from app.models.illumio.illumio_label import IllumioLabel
from app.models.illumio.illumio_workload_label import IllumioWorkloadLabel
from app.models.illumio.sync_run import SyncRun
from app.models.illumio.ingestion_source import IngestionSource

__all__ = [
    "IllumioWorkload",
    "IllumioInterface",
    "IllumioLabel",
    "IllumioWorkloadLabel",
    "SyncRun",
    "IngestionSource",
]
