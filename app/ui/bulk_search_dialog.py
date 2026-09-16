from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)


class BulkSearchDialog(QDialog):
    """
    Modal dialog that accepts a paste of lookup values (one per line).
    Accepts up to 10 000 lines.

    After exec_() check .terms for the list of strings to search.
    """

    MAX_TERMS = 10_000

    def __init__(self, parent=None, lookup_description="hostnames or IP addresses"):
        super().__init__(parent)

        self.setWindowTitle("Bulk Search")
        self.setMinimumSize(520, 400)

        self.terms = []

        self._text = QPlainTextEdit()
        self._lookup_description = lookup_description
        self._text.setPlaceholderText(
            f"Paste {lookup_description} here — one per line.\n\n"
            "Examples:\n"
            "  app-server-1.example.com\n"
            "  192.168.1.100\n"
            "  web-server-42\n\n"
            f"Up to {self.MAX_TERMS:,} entries supported."
        )

        self._hint = QLabel()
        self._hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_hint()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        self._text.textChanged.connect(self._update_hint)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Paste {lookup_description} (one per line):"))
        layout.addWidget(self._text)
        layout.addWidget(self._hint)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _update_hint(self):
        lines = [
            l.strip()
            for l in self._text.toPlainText().splitlines()
            if l.strip()
        ]
        count = len(lines)
        if count > self.MAX_TERMS:
            self._hint.setText(
                f"⚠  {count:,} entries — only the first {self.MAX_TERMS:,} will be used."
            )
        else:
            self._hint.setText(f"{count:,} entr{'y' if count == 1 else 'ies'}")

    def _accept(self):
        lines = [
            l.strip()
            for l in self._text.toPlainText().splitlines()
            if l.strip()
        ]
        self.terms = lines[: self.MAX_TERMS]
        self.accept()
