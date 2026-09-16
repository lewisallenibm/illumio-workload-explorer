if __name__ != "__main__":
    import pytest
    pytest.skip("Legacy manual database script; excluded from automated tests.", allow_module_level=True)

from app.services.reconciliation_service import (
    ReconciliationService
)


result = ReconciliationService.reconcile(
    "AZGDSTRAT01",
    "10.50.122.51"
)

print(result)


result = ReconciliationService.reconcile(
    "AZGDSTRAT01",
    "10.99.99.99"
)

print(result)


result = ReconciliationService.reconcile(
    "NOTREALHOST",
    "10.80.1.1"
)
