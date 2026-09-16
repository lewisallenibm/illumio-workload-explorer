from sqlalchemy import desc

from app.database import SessionLocal

from app.models.workload_change import (
    WorkloadChange
)


class AuditService:

    @staticmethod
    def log_change(
        workload_id,
        field_name,
        old_value,
        new_value,
        actor="unknown"
    ):

        session = SessionLocal()

        try:

            change = WorkloadChange(
                workload_id=workload_id,
                field_name=field_name,
                old_value=str(old_value),
                new_value=str(new_value),
                actor=str(actor or "unknown"),
            )

            session.add(
                change
            )

            session.commit()

        finally:

            session.close()

    @staticmethod
    def get_latest_change_for_workload(
        workload_id
    ):

        session = SessionLocal()

        try:

            return (
                session.query(
                    WorkloadChange
                )
                .filter(
                    WorkloadChange.workload_id
                    == workload_id
                )
                .order_by(
                    desc(
                        WorkloadChange.id
                    )
                )
                .first()
            )

        finally:

            session.close()