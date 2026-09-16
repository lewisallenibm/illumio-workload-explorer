from sqlalchemy import desc
from sqlalchemy import func
from sqlalchemy import select

from app.database import SessionLocal

from app.models.workload import Workload
from app.models.workload_change import (
    WorkloadChange,
)
from app.models.workload_ip import (
    WorkloadIP,
)


class OperationsService:

    @staticmethod
    def get_duplicate_hostnames():

        session = SessionLocal()

        try:

            hostnames = session.execute(
                select(
                    Workload.hostname
                )
                .group_by(
                    Workload.hostname
                )
                .having(
                    func.count() > 1
                )
            ).scalars().all()

            return hostnames

        finally:

            session.close()

    @staticmethod
    def get_duplicate_ips():

        session = SessionLocal()

        try:

            ips = session.execute(
                select(
                    WorkloadIP.ip_address
                )
                .group_by(
                    WorkloadIP.ip_address
                )
                .having(
                    func.count() > 1
                )
            ).scalars().all()

            return ips

        finally:

            session.close()

    @staticmethod
    def get_unhealthy_workloads():

        session = SessionLocal()

        try:

            workloads = session.execute(
                select(
                    Workload
                )
                .where(
                    Workload.agent_health
                    != "healthy"
                )
            ).scalars().all()

            return workloads

        finally:

            session.close()

    @staticmethod
    def get_stopped_agents():

        session = SessionLocal()

        try:

            workloads = session.execute(
                select(
                    Workload
                )
                .where(
                    Workload.agent_status
                    == "stopped"
                )
            ).scalars().all()

            return workloads

        finally:

            session.close()

    @staticmethod
    def get_suspended_agents():

        session = SessionLocal()

        try:

            workloads = session.execute(
                select(
                    Workload
                )
                .where(
                    Workload.agent_status
                    == "suspended"
                )
            ).scalars().all()

            return workloads

        finally:

            session.close()

    @staticmethod
    def get_recent_changes():

        session = SessionLocal()

        try:

            changes = session.execute(
                select(
                    WorkloadChange
                )
                .order_by(
                    desc(
                        WorkloadChange.changed_at
                    )
                )
                .limit(10)
            ).scalars().all()

            return changes

        finally:

            session.close()

    @staticmethod
    def get_top_modified_workloads():

        session = SessionLocal()

        try:

            results = session.execute(
                select(
                    Workload.hostname,
                    func.count(
                        WorkloadChange.id
                    )
                )
                .join(
                    WorkloadChange,
                    Workload.id
                    == WorkloadChange.workload_id
                )
                .group_by(
                    Workload.hostname
                )
                .order_by(
                    desc(
                        func.count(
                            WorkloadChange.id
                        )
                    )
                )
                .limit(10)
            ).all()

            return results

        finally:

            session.close()

    @staticmethod
    def get_dashboard_summary():

        session = SessionLocal()

        try:

            total = session.scalar(
                select(func.count())
                .select_from(Workload)
            )

            healthy = session.scalar(
                select(func.count())
                .select_from(Workload)
                .where(
                    Workload.agent_health
                    == "healthy"
                )
            )

            stopped = session.scalar(
                select(func.count())
                .select_from(Workload)
                .where(
                    Workload.agent_status
                    == "stopped"
                )
            )

            suspended = session.scalar(
                select(func.count())
                .select_from(Workload)
                .where(
                    Workload.agent_status
                    == "suspended"
                )
            )

            return {
                "total": total,
                "healthy": healthy,
                "stopped": stopped,
                "suspended": suspended,
            }

        finally:

            session.close()