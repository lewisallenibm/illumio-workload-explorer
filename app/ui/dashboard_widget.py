from PySide6.QtWidgets import (
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import desc
from sqlalchemy import func
from sqlalchemy import select

from app.database import SessionLocal

from app.models.workload import Workload
from app.models.workload_change import (
    WorkloadChange
)
from app.models.workload_ip import (
    WorkloadIP
)


class DashboardWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.refresh_button = QPushButton(
            "Refresh Dashboard"
        )

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button.clicked.connect(
            self.load_data
        )

        layout = QVBoxLayout()

        layout.addWidget(
            self.refresh_button
        )

        layout.addWidget(
            self.output
        )

        self.setLayout(layout)

        self.load_data()

    def load_data(self):

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

            duplicate_hosts = len(
                session.execute(
                    select(
                        Workload.hostname
                    )
                    .group_by(
                        Workload.hostname
                    )
                    .having(
                        func.count() > 1
                    )
                ).all()
            )

            duplicate_ips = len(
                session.execute(
                    select(
                        WorkloadIP.ip_address
                    )
                    .group_by(
                        WorkloadIP.ip_address
                    )
                    .having(
                        func.count() > 1
                    )
                ).all()
            )

            recent_changes = session.execute(
                select(
                    WorkloadChange,
                    Workload.hostname
                )
                .join(
                    Workload,
                    Workload.id
                    == WorkloadChange.workload_id
                )
                .order_by(
                    desc(
                        WorkloadChange.changed_at
                    )
                )
                .limit(10)
            ).all()

            activity_lines = []

            for change, hostname in recent_changes:

                if change.old_value == change.new_value:
                    continue

                activity_lines.append(
                    f"""
Hostname: {hostname}

Field:
{change.field_name}

{change.old_value}
→
{change.new_value}

{change.changed_at}

--------------------
"""
                )

            top_modified = session.execute(
                select(
                    Workload.hostname,
                    func.count(
                        WorkloadChange.id
                    )
                )
                .join(
                    Workload,
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

            top_modified_text = []

            for hostname, count in top_modified:

                top_modified_text.append(
                    f"{hostname}: {count} changes"
                )

            self.output.setText(
                f"""
Total Workloads: {total}

Healthy Agents: {healthy}

Stopped Agents: {stopped}

Suspended Agents: {suspended}

Duplicate Hostnames: {duplicate_hosts}

Duplicate IPs: {duplicate_ips}

=================================

RECENT ACTIVITY

{chr(10).join(activity_lines)}

=================================

TOP MODIFIED WORKLOADS

{chr(10).join(top_modified_text)}
"""
            )

        finally:

            session.close()