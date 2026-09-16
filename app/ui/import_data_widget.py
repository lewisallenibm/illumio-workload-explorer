import importlib
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import delete

from app.database import SessionLocal

from app.models.import_run import ImportRun
from app.models.workload import Workload
from app.models.workload_ip import WorkloadIP


class ImportDataWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.file_path = None

        self.file_label = QLabel(
            "No file selected"
        )

        self.browse_button = QPushButton(
            "Browse"
        )

        self.import_button = QPushButton(
            "Import"
        )

        self.append_mode = QRadioButton(
            "Append Data"
        )

        self.replace_mode = QRadioButton(
            "Replace Existing Data"
        )

        self.append_mode.setChecked(True)

        self.status = QTextEdit()
        self.status.setReadOnly(True)

        self.browse_button.clicked.connect(
            self.select_file
        )

        self.import_button.clicked.connect(
            self.import_file
        )

        layout = QVBoxLayout()

        layout.addWidget(
            self.file_label
        )

        layout.addWidget(
            self.browse_button
        )

        layout.addWidget(
            self.append_mode
        )

        layout.addWidget(
            self.replace_mode
        )

        layout.addWidget(
            self.import_button
        )

        layout.addWidget(
            self.status
        )

        self.setLayout(layout)

    def select_file(self):

        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            "",
            "Data Files (*.csv *.xlsx)"
        )

        if file_name:

            self.file_path = file_name

            self.file_label.setText(
                file_name
            )

    def load_dataframe(self):

        # CSV remains the supported pilot import path. Keep the legacy
        # spreadsheet dependency lazy so an optional Excel reader does not
        # inflate or block the native desktop package.
        pd = importlib.import_module("pandas")

        suffix = Path(
            self.file_path
        ).suffix.lower()

        if suffix == ".csv":

            return pd.read_csv(
                self.file_path
            )

        if suffix == ".xlsx":

            return pd.read_excel(
                self.file_path
            )

        raise ValueError(
            f"Unsupported file type: {suffix}"
        )

    def import_file(self):

        if not self.file_path:

            self.status.setText(
                "Please select a file."
            )

            return

        session = SessionLocal()

        try:

            if self.replace_mode.isChecked():

                session.execute(
                    delete(WorkloadIP)
                )

                session.execute(
                    delete(Workload)
                )

                session.execute(
                    delete(ImportRun)
                )

                session.commit()

            df = self.load_dataframe()

            import_run = ImportRun(
                filename=Path(
                    self.file_path
                ).name,
                row_count=len(df),
                status="SUCCESS"
            )

            session.add(
                import_run
            )

            session.commit()

            for _, row in df.iterrows():

                workload = Workload(
                    import_run_id=import_run.id,
                    hostname=row["hostname"],
                    app=row["app"],
                    env=row["env"],
                    loc=row["loc"],
                    role=row["role"],
                    enforcement=row["enforcement"],
                    online=bool(row["online"]),
                    agent_status=row["agent_status"],
                    agent_health=row["agent_health"]
                )

                session.add(
                    workload
                )

                session.flush()

                workload_ip = WorkloadIP(
                    workload_id=workload.id,
                    interface_name="eth0",
                    ip_address=row["ip_address"]
                )

                session.add(
                    workload_ip
                )

            session.commit()

            self.status.setText(
                f"Imported {len(df)} workloads successfully."
            )

        except Exception as ex:

            self.status.setText(
                f"ERROR:\n{ex}"
            )

        finally:

            session.close()
