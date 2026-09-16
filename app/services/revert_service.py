from app.database import SessionLocal

from app.models.workload import Workload
from app.models.workload_change import (
    WorkloadChange
)

from app.services.audit_service import (
    AuditService
)


class RevertService:

    @staticmethod
    def revert_change(
        change_id
    ):

        session = SessionLocal()

        try:

            change = session.get(
                WorkloadChange,
                change_id
            )

            if change is None:
                raise ValueError(
                    "Change not found."
                )

            workload = session.get(
                Workload,
                change.workload_id
            )

            old_current_value = getattr(
                workload,
                change.field_name
            )

            setattr(
                workload,
                change.field_name,
                change.old_value
            )

            session.commit()

            AuditService.log_change(
                workload_id=workload.id,
                field_name=change.field_name,
                old_value=old_current_value,
                new_value=change.old_value,
            )

        finally:

            session.close()