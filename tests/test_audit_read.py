if __name__ != "__main__":
    import pytest
    pytest.skip("Legacy manual database script; excluded from automated tests.", allow_module_level=True)

from app.database import SessionLocal

from app.models.workload_change import (
    WorkloadChange
)

session = SessionLocal()

records = (
    session.query(
        WorkloadChange
    ).all()
)

print(
    f"Records Found: {len(records)}"
)

for record in records:

    print(
        record.id,
        record.workload_id,
        record.field_name,
        record.old_value,
        record.new_value
    )

session.close()
