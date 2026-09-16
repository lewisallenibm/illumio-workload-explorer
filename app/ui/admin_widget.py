"""Guarded local-only operational controls for the optional Admin tab."""

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.scripts.backup_database import create_backup
from app.scripts.health_check import collect_health
from app.scripts.reset_local_data import reset_local_data


RESET_CONFIRMATION = "RESET LOCAL DATA"


def reset_confirmation_is_valid(value: str) -> bool:
    return value.strip() == RESET_CONFIRMATION


def format_health_report(report: dict) -> str:
    lines = [
        f"Database: {report['database']}",
        f"PCE reads: {'enabled' if report['real_pce_reads'] else 'disabled'}",
        f"PCE write-back: {'enabled' if report['pce_writeback'] else 'disabled'}",
        f"Qt plugin: {'ready' if report['qt_platform_plugin_available'] else 'missing'}",
        f"Local backup tool: {'ready' if report['pg_dump_available'] else 'unavailable'}",
        "",
        "Local row counts:",
    ]
    lines.extend(f"- {table}: {count:,}" for table, count in report["counts"].items())
    if report["missing_tables"]:
        lines.append("Missing tables: " + ", ".join(report["missing_tables"]))
    if report["missing_indexes"]:
        lines.append("Missing performance indexes: " + ", ".join(report["missing_indexes"]))
    return "\n".join(lines)


class _AdminWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self._operation = operation

    def run(self):
        try:
            self.finished.emit(self._operation())
        except Exception as exc:
            self.error.emit(str(exc))


class AdminWidget(QWidget):
    """Local operations only; this tab never contacts the Illumio PCE."""

    def __init__(self):
        super().__init__()
        self._worker = None
        self._operation_name = None
        self._backup_created_this_session = False

        self.health_button = QPushButton("Run Local Health Check")
        self.backup_button = QPushButton("Create Local Backup")
        self.reset_button = QPushButton("Reset Local Data…")
        self.reset_button.setEnabled(False)
        self.reset_button.setToolTip("Create a local backup in this session before reset is enabled")

        self.notice = QLabel(
            "These controls affect only this computer’s PostgreSQL data. They never contact PCE."
        )
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.health_button)
        buttons.addWidget(self.backup_button)
        buttons.addWidget(self.reset_button)
        buttons.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self.notice)
        layout.addLayout(buttons)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.health_button.clicked.connect(self.run_health_check)
        self.backup_button.clicked.connect(self.create_backup)
        self.reset_button.clicked.connect(self.request_reset)

    def _start(self, name, operation):
        self._operation_name = name
        for button in (self.health_button, self.backup_button, self.reset_button):
            button.setEnabled(False)
        self.output.setPlainText(f"{name} is running…")
        self._worker = _AdminWorker(operation)
        self._worker.finished.connect(self._operation_finished)
        self._worker.error.connect(self._operation_failed)
        self._worker.start()

    def _restore_buttons(self):
        self.health_button.setEnabled(True)
        self.backup_button.setEnabled(True)
        self.reset_button.setEnabled(self._backup_created_this_session)

    def run_health_check(self):
        self._start("Local health check", collect_health)

    def create_backup(self):
        self._start("Local backup", create_backup)

    def request_reset(self):
        confirmation, accepted = QInputDialog.getText(
            self,
            "Confirm Local Reset",
            f"This permanently clears local snapshots and reconciliation history.\n"
            f"Type {RESET_CONFIRMATION} to continue:",
        )
        if not accepted or not reset_confirmation_is_valid(confirmation):
            self.output.setPlainText("Local reset cancelled. No data was changed.")
            return
        self._start("Local data reset", reset_local_data)

    def _operation_finished(self, result):
        name = self._operation_name
        if name == "Local health check":
            self.output.setPlainText(format_health_report(result))
        elif name == "Local backup":
            self._backup_created_this_session = True
            self.output.setPlainText(f"Local backup created:\n{Path(result)}\n\nReset is now enabled for this session.")
        else:
            self.output.setPlainText(
                "Local data reset completed. No PCE data was changed. Restart the app to refresh all tabs."
            )
            QMessageBox.information(self, "Local Reset Complete", "Restart the app to refresh all tabs.")
        self._restore_buttons()

    def _operation_failed(self, message):
        self.output.setPlainText(f"{self._operation_name} failed:\n{message}")
        self._restore_buttons()
