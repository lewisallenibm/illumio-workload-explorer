from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from app.services.illumio.workloader_source_adapter import WorkloaderPreview


class WorkloaderImportPreviewDialog(QDialog):
    """Confirmation dialog that exposes file shape, never source row values."""

    def __init__(self, preview: WorkloaderPreview, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workloader Import Preview")
        self.setMinimumSize(620, 360)

        lines = [
            f"File: {preview.filename}",
            f"Rows detected: {preview.readable_rows:,}",
            f"Identifier: {preview.identifier or 'Not detected'}",
            f"Known columns: {', '.join(preview.known_columns) or 'None'}",
            f"Unknown columns preserved in source data: {', '.join(preview.unknown_columns) or 'None'}",
        ]
        if preview.malformed_rows:
            lines.append(f"Malformed rows: {preview.malformed_rows:,}")
        if preview.warnings:
            lines.extend(["", "Warnings:", *preview.warnings])
        if preview.errors:
            lines.extend(["", "Validation errors:", *preview.errors])

        detail = QTextEdit("\n".join(lines))
        detail.setReadOnly(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        if preview.valid:
            buttons.addButton("Import", QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Review the CSV structure before importing into the current Illumio dataset."))
        layout.addWidget(detail)
        layout.addWidget(buttons)
        self.setLayout(layout)
