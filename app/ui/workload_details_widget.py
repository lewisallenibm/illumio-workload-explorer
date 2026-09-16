from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.repositories.workload_repository import (
    WorkloadRepository
)

from app.services.workload_update_service import (
    WorkloadUpdateService
)

from app.ui.review_changes_dialog import (
    ReviewChangesDialog
)


class WorkloadDetailsWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.workload = None

        self.hostname_label = QLabel()

        self.app_input = QLineEdit()
        self.env_input = QLineEdit()
        self.role_input = QLineEdit()
        self.status_input = QLineEdit()
        self.health_input = QLineEdit()

        self.ips = QTextEdit()
        self.ips.setReadOnly(True)

        self.review_button = QPushButton(
            "Review Changes"
        )

        self.review_button.clicked.connect(
            self.review_changes
        )

        layout = QVBoxLayout()

        layout.addWidget(
            self.hostname_label
        )

        layout.addWidget(
            QLabel("IP Addresses")
        )

        layout.addWidget(
            self.ips
        )

        layout.addWidget(
            QLabel("Application")
        )

        layout.addWidget(
            self.app_input
        )

        layout.addWidget(
            QLabel("Environment")
        )

        layout.addWidget(
            self.env_input
        )

        layout.addWidget(
            QLabel("Role")
        )

        layout.addWidget(
            self.role_input
        )

        layout.addWidget(
            QLabel("Agent Status")
        )

        layout.addWidget(
            self.status_input
        )

        layout.addWidget(
            QLabel("Agent Health")
        )

        layout.addWidget(
            self.health_input
        )

        layout.addWidget(
            self.review_button
        )

        self.setLayout(layout)

    def clear(self):

        self.workload = None

        self.hostname_label.setText("")

        self.ips.clear()

        self.app_input.clear()
        self.env_input.clear()
        self.role_input.clear()
        self.status_input.clear()
        self.health_input.clear()

    def load_workload(
        self,
        workload
    ):

        self.workload = workload

        if workload is None:
            self.clear()
            return

        ips = (
            WorkloadRepository
            .get_workload_ips(
                workload.id
            )
        )

        self.hostname_label.setText(
            f"Hostname: {workload.hostname}"
        )

        self.ips.setText(
            "\n".join(
                ip.ip_address
                for ip in ips
            )
        )

        self.app_input.setText(
            workload.app or ""
        )

        self.env_input.setText(
            workload.env or ""
        )

        self.role_input.setText(
            workload.role or ""
        )

        self.status_input.setText(
            workload.agent_status or ""
        )

        self.health_input.setText(
            workload.agent_health or ""
        )

    def review_changes(self):

        if self.workload is None:
            return

        changes = {}

        def check(
            field_name,
            old_value,
            new_value
        ):

            if str(old_value) != str(new_value):

                changes[field_name] = {
                    "old": old_value,
                    "new": new_value
                }

        check(
            "app",
            self.workload.app,
            self.app_input.text()
        )

        check(
            "env",
            self.workload.env,
            self.env_input.text()
        )

        check(
            "role",
            self.workload.role,
            self.role_input.text()
        )

        check(
            "agent_status",
            self.workload.agent_status,
            self.status_input.text()
        )

        check(
            "agent_health",
            self.workload.agent_health,
            self.health_input.text()
        )

        if not changes:
            return

        dialog = ReviewChangesDialog(
            changes,
            self
        )

        if dialog.exec():

            updates = {}

            for field_name, values in changes.items():

                updates[field_name] = (
                    values["new"]
                )

            WorkloadUpdateService.update_workload(
                self.workload.id,
                updates
            )

            self.load_workload(
                self.workload
            )