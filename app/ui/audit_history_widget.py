from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import select

from app.database import SessionLocal

from app.models.workload import Workload
from app.models.workload_change import (
    WorkloadChange
)

from app.services.revert_service import (
    RevertService
)


class AuditHistoryWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.records = []

        self.hostname_filter = QLineEdit()
        self.hostname_filter.setPlaceholderText(
            "Hostname"
        )

        self.field_filter = QLineEdit()
        self.field_filter.setPlaceholderText(
            "Field Name"
        )

        self.filter_button = QPushButton(
            "Apply Filter"
        )

        self.refresh_button = QPushButton(
            "Refresh"
        )

        self.revert_button = QPushButton(
            "Revert Selected Change"
        )

        self.table = QTableWidget()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "Hostname",
            "Field",
            "Old Value",
            "New Value",
            "Changed At"
        ])

        self.filter_button.clicked.connect(
            self.load_history
        )

        self.refresh_button.clicked.connect(
            self.refresh_history
        )

        self.revert_button.clicked.connect(
            self.revert_selected
        )

        filter_layout = QHBoxLayout()

        filter_layout.addWidget(
            self.hostname_filter
        )

        filter_layout.addWidget(
            self.field_filter
        )

        filter_layout.addWidget(
            self.filter_button
        )

        layout = QVBoxLayout()

        layout.addLayout(
            filter_layout
        )

        layout.addWidget(
            self.refresh_button
        )

        layout.addWidget(
            self.revert_button
        )

        layout.addWidget(
            self.table
        )

        self.setLayout(
            layout
        )

        self.load_history()

    def refresh_history(self):

        self.hostname_filter.clear()
        self.field_filter.clear()

        self.load_history()

    def load_history(self):

        session = SessionLocal()

        try:

            stmt = (
                select(
                    WorkloadChange,
                    Workload.hostname
                )
                .join(
                    Workload,
                    Workload.id
                    == WorkloadChange.workload_id
                )
            )

            hostname = (
                self.hostname_filter.text()
                .strip()
            )

            field_name = (
                self.field_filter.text()
                .strip()
            )

            if hostname:

                stmt = stmt.where(
                    Workload.hostname.ilike(
                        f"%{hostname}%"
                    )
                )

            if field_name:

                stmt = stmt.where(
                    WorkloadChange.field_name.ilike(
                        f"%{field_name}%"
                    )
                )

            stmt = stmt.order_by(
                WorkloadChange.changed_at.desc()
            )

            self.records = (
                session.execute(stmt)
                .all()
            )

            self.table.setRowCount(
                len(self.records)
            )

            for row, item in enumerate(
                self.records
            ):

                change = item[0]
                hostname = item[1]

                self.table.setItem(
                    row,
                    0,
                    QTableWidgetItem(
                        hostname
                    )
                )

                self.table.setItem(
                    row,
                    1,
                    QTableWidgetItem(
                        change.field_name
                    )
                )

                self.table.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        change.old_value
                    )
                )

                self.table.setItem(
                    row,
                    3,
                    QTableWidgetItem(
                        change.new_value
                    )
                )

                self.table.setItem(
                    row,
                    4,
                    QTableWidgetItem(
                        str(change.changed_at)
                    )
                )

        finally:

            session.close()

    def revert_selected(self):

        row = self.table.currentRow()

        if row < 0:
            return

        change = self.records[row][0]

        reply = QMessageBox.question(
            self,
            "Confirm Revert",
            (
                f"Revert '{change.field_name}'\n\n"
                f"Current Value:\n"
                f"{change.new_value}\n\n"
                f"Will Become:\n"
                f"{change.old_value}"
            )
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        RevertService.revert_change(
            change.id
        )

        self.load_history()
  