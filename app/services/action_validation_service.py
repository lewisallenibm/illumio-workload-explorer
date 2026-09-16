from app.database import SessionLocal

from app.models.workload import (
    Workload,
)

from app.services.search_service import (
    SearchService,
)


class ActionValidationService:

    @staticmethod
    def validate(plan):

        workload_id = plan.get(
            "workload_id"
        )

        if workload_id:

            session = SessionLocal()

            try:

                workload = session.get(
                    Workload,
                    workload_id
                )

                if workload is None:

                    return {
                        "valid": False,
                        "message": (
                            f"Workload ID "
                            f"{workload_id} "
                            f"not found."
                        ),
                    }

                return {
                    "valid": True,
                    "workload": workload,
                }

            finally:

                session.close()

        hostname = plan.get(
            "hostname"
        )

        if not hostname:

            return {
                "valid": False,
                "message": (
                    "No hostname found."
                ),
            }

        matches = (
            SearchService.search_hostname(
                hostname
            )
        )

        if len(matches) == 0:

            return {
                "valid": False,
                "message": (
                    f"Hostname not found: "
                    f"{hostname}"
                ),
            }

        if len(matches) > 1:

            return {
                "valid": False,
                "message": (
                    "Multiple workloads "
                    f"found for hostname: "
                    f"{hostname}"
                ),
                "matches": matches,
            }

        return {
            "valid": True,
            "workload": matches[0],
        }