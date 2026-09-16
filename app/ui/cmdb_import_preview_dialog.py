from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from app.services.cmdb_import_service import CmdbImportPreview


class CmdbImportPreviewDialog(QDialog):
    def __init__(self, preview: CmdbImportPreview, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CMDB / Inventory Import Preview")
        self.setMinimumSize(620, 360)
        lines = [
            f"File: {preview.filename}",
            f"Source type: {preview.source_type}",
            f"Rows detected: {preview.readable_rows:,}",
            f"Identifier: {preview.identifier_strategy or 'Not detected'}",
            f"Recognized headers: {', '.join(preview.recognized_headers) or 'None'}",
            f"Unknown headers retained: {', '.join(preview.unknown_headers) or 'None'}",
        ]
        if preview.malformed_rows:
            lines.append(f"Malformed rows: {preview.malformed_rows:,}")
        if preview.duplicate_identities:
            lines.append(f"Duplicate identities retained: {preview.duplicate_identities:,}")
        if preview.warnings:
            lines.extend(["", "Warnings:", *preview.warnings])
        if preview.errors:
            lines.extend(["", "Validation errors:", *preview.errors])

        text = QTextEdit("\n".join(lines))
        text.setReadOnly(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        if preview.valid:
            buttons.addButton("Import Snapshot", QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("The current CMDB snapshot is unchanged until this validated import finishes staging."))
        layout.addWidget(text)
        layout.addWidget(buttons)
        self.setLayout(layout)
