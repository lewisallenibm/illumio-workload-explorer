from sqlalchemy import func, case

from app.database import SessionLocal
from app.models.illumio.illumio_workload import IllumioWorkload
from app.services.performance import timed


class IllumioStatsService:

    @staticmethod
    def get_summary():
        """
        Return total/online/offline in a SINGLE query using conditional aggregation.
        One round-trip to Postgres instead of three.
        """
        session = SessionLocal()
        try:
            with timed("workloads.repository.stats"):
                row = session.query(
                    func.count(IllumioWorkload.id).label("total"),
                    func.count(
                        case((IllumioWorkload.online == True, 1))
                    ).label("online"),
                    func.count(
                        case((IllumioWorkload.online == False, 1))
                    ).label("offline"),
                ).one()

            return {
                "total":   row.total,
                "online":  row.online,
                "offline": row.offline,
            }
        finally:
            session.close()
