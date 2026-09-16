"""Deterministic mock CMDB snapshots through the same safe persistence path."""

from app.database import SessionLocal
from app.models.illumio.illumio_workload import IllumioWorkload
from app.services.cmdb_import_service import CmdbImportService
from app.services.mock_cmdb_generator import MockCmdbGenerator


class MockCmdbSyncService:
    @staticmethod
    def sync(count=300_000, progress_callback=None):
        session = SessionLocal()
        try:
            illumio_hostnames = [
                row[0]
                for row in session.query(IllumioWorkload.hostname)
                .filter(IllumioWorkload.hostname.isnot(None))
                .all()
            ]
        finally:
            session.close()

        records = MockCmdbGenerator.generate(
            count=count, illumio_hostnames=illumio_hostnames,
        )
        return CmdbImportService.replace_mock_records(
            records, progress_callback=progress_callback,
        )
