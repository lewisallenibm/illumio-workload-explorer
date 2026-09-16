from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import func
from sqlalchemy import select

from app.database import SessionLocal
from app.models.workload import Workload
from app.models.workload_ip import WorkloadIP


class DuplicatesWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.hostname_table = QTableWidget()
        self.hostname_table.setColumnCount(2)
        self.hostname_table.setHorizontalHeaderLabels(
            ["Hostname", "Count"]
        )

        self.ip_table = QTableWidget()
        self.ip_table.setColumnCount(2)
        self.ip_table.setHorizontalHeaderLabels(
            ["IP Address", "Count"]
        )

        layout = QVBoxLayout()

        layout.addWidget(self.hostname_table)
        layout.addWidget(self.ip_table)

        self.setLayout(layout)

        self.load_duplicates()

    def load_duplicates(self):

        session = SessionLocal()

        try:

            hostname_stmt = (
                select(
                    Workload.hostname,
                    func.count()
                )
                .group_by(
                    Workload.hostname
                )
                .having(
                    func.count() > 1
                )
            )

            hostname_results = (
                session.execute(
                    hostname_stmt
                ).all()
            )

            self.hostname_table.setRowCount(
                len(hostname_results)
            )

            for row, item in enumerate(
                hostname_results
            ):

                self.hostname_table.setItem(
                    row,
                    0,
                    QTableWidgetItem(
                        item[0]
                    )
                )

                self.hostname_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(
                        str(item[1])
                    )
                )

            ip_stmt = (
                select(
                    WorkloadIP.ip_address,
                    func.count()
                )
                .group_by(
                    WorkloadIP.ip_address
                )
                .having(
                    func.count() > 1
                )
            )

            ip_results = (
                session.execute(
                    ip_stmt
                ).all()
            )

            self.ip_table.setRowCount(
                len(ip_results)
            )

            for row, item in enumerate(
                ip_results
            ):

                self.ip_table.setItem(
                    row,
                    0,
                    QTableWidgetItem(
                        item[0]
                    )
                )

                self.ip_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(
                        str(item[1])
                    )
                )

        finally:

            session.close()