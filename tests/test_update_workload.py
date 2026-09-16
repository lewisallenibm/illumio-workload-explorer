if __name__ != "__main__":
    import pytest
    pytest.skip("Legacy manual database script; excluded from automated tests.", allow_module_level=True)

from app.services.workload_update_service import (
    WorkloadUpdateService
)

WorkloadUpdateService.update_workload(
    workload_id=1,
    updates={
        "agent_status": "active",
    }
)

print(
    "update completed"
)
