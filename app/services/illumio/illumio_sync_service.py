from app.services.illumio.illumio_service import IllumioService
from app.services.illumio.ingestion_service import IllumioIngestionService


class IllumioSyncService:

    @staticmethod
    def sync(records=None):
        """Synchronize client records through the shared canonical pipeline."""
        if records is None:
            records = IllumioService.get_workloads()
        return IllumioIngestionService.ingest(
            records,
            source="illumio_api" if IllumioService.using_real_client() else "mock",
        )
