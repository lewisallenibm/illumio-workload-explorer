from app.database import SessionLocal

from app.models.workload import Workload
from app.models.workload_ip import WorkloadIP

from app.services.audit_service import (
    AuditService
)


class WorkloadUpdateService:

    @staticmethod
    def update_workload(
        workload_id,
        updates
    ):

        print(
            f"UPDATE REQUEST: workload_id={workload_id}"
        )

        session = SessionLocal()

        try:

            workload = session.get(
                Workload,
                workload_id
            )

            if workload is None:

                print(
                    "WORKLOAD NOT FOUND"
                )

                raise ValueError(
                    f"Workload {workload_id} not found."
                )

            for field_name, new_value in updates.items():

                old_value = getattr(
                    workload,
                    field_name
                )

                print(
                    f"FIELD: {field_name}"
                )

                print(
                    f"OLD: {old_value}"
                )

                print(
                    f"NEW: {new_value}"
                )

                if str(old_value) == str(new_value):

                    print(
                        "NO CHANGE DETECTED"
                    )

                    continue

                setattr(
                    workload,
                    field_name,
                    new_value
                )

                print(
                    "AUDIT RECORD CREATED"
                )

                AuditService.log_change(
                    workload_id=workload_id,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                )

            print(
                "COMMITTING DATABASE CHANGES"
            )

            session.commit()

            print(
                "COMMIT COMPLETE"
            )

            return True

        except Exception as ex:

            print(
                f"ERROR: {ex}"
            )

            session.rollback()

            raise

        finally:

            session.close()