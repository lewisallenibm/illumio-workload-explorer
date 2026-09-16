from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import select

from app.database import SessionLocal
from app.models.import_run import ImportRun


class ImportHistoryWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.table = QTableWidget()

        self.table.setColumnCount(4)

        self.table.setHorizontalHeaderLabels([
            "Filename",
            "Rows",
            "Status",
            "Imported At"
        ])

        layout = QVBoxLayout()
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.load_imports()

    def load_imports(self):

        session = SessionLocal()

        try:

            stmt = select(ImportRun)

            imports = (
                session.execute(stmt)
                .scalars()
                .all()
            )

            self.table.setRowCount(
                len(imports)
            )

            for row, item in enumerate(imports):

                self.table.setItem(
                    row,
                    0,
                    QTableWidgetItem(
                        item.filename
                    )
                )

                self.table.setItem(
                    row,
                    1,
                    QTableWidgetItem(
                        str(item.row_count)
                    )
                )

                self.table.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        item.status
                    )
                )

                self.table.setItem(
                    row,
                    3,
                    QTableWidgetItem(
                        str(item.imported_at)
                    )
                )

        finally:
            session.close()