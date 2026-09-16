if __name__ != "__main__":
    import pytest
    pytest.skip("Manual sync script; excluded from automated tests.", allow_module_level=True)

from app.services.illumio.illumio_sync_service import (
    IllumioSyncService
)

from app.services.illumio.illumio_stats_service import (
    IllumioStatsService
)


result = (
    IllumioSyncService.sync()
)

print()

print("SYNC RESULT")
print(result)

print()

stats = (
    IllumioStatsService
    .get_summary()
)

print("DATABASE SUMMARY")
print(stats)
