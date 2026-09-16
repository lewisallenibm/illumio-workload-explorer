from sqlalchemy import select

from app.database import SessionLocal

from app.models.workload import Workload
from app.models.workload_ip import WorkloadIP


class WorkloadRepository:

    @staticmethod
    def find_by_hostname(hostname: str):

        session = SessionLocal()

        try:
            stmt = (
                select(Workload)
                .where(
                    Workload.hostname == hostname
                )
            )

            return session.execute(
                stmt
            ).scalars().all()

        finally:
            session.close()

    @staticmethod
    def find_by_ip(ip_address: str):

        session = SessionLocal()

        try:
            stmt = (
                select(Workload)
                .join(
                    WorkloadIP,
                    Workload.id == WorkloadIP.workload_id
                )
                .where(
                    WorkloadIP.ip_address == ip_address
                )
            )

            return session.execute(
                stmt
            ).scalars().all()

        finally:
            session.close()

    @staticmethod
    def get_workload_ips(
        workload_id: int
    ):

        session = SessionLocal()

        try:
            stmt = (
                select(WorkloadIP)
                .where(
                    WorkloadIP.workload_id
                    == workload_id
                )
            )

            return session.execute(
                stmt
            ).scalars().all()

        finally:
            session.close()