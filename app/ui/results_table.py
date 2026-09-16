from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
)


class ResultsTable(QTableWidget):

    def __init__(self):
        super().__init__()

        self.workloads = []

        self.setColumnCount(5)

        self.setHorizontalHeaderLabels([
            "Hostname",
            "App",
            "Environment",
            "Status",
            "Health"
        ])

    def load_workloads(self, workloads):

        self.workloads = workloads

        self.setRowCount(
            len(workloads)
        )

        for row, workload in enumerate(workloads):

            self.setItem(
                row,
                0,
                QTableWidgetItem(workload.hostname)
            )

            self.setItem(
                row,
                1,
                QTableWidgetItem(
                    workload.app or ""
                )
            )

            self.setItem(
                row,
                2,
                QTableWidgetItem(
                    workload.env or ""
                )
            )

            self.setItem(
                row,
                3,
                QTableWidgetItem(
                    workload.agent_status or ""
                )
            )

            self.setItem(
                row,
                4,
                QTableWidgetItem(
                    workload.agent_health or ""
                )
            )
