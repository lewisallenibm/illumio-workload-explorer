from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class ReviewChangesDialog(QDialog):

    def __init__(
        self,
        changes,
        parent=None
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "Review Changes"
        )

        self.accept_button = QPushButton(
            "Confirm"
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.accept_button.clicked.connect(
            self.accept
        )

        self.cancel_button.clicked.connect(
            self.reject
        )

        text = QTextEdit()

        text.setReadOnly(True)

        output = []

        for field_name, values in changes.items():

            output.append(
                f"""
Field: {field_name}

Old:
{values["old"]}

New:
{values["new"]}

--------------------
"""
            )

        text.setText(
            "\n".join(output)
        )

        layout = QVBoxLayout()

        layout.addWidget(text)
        layout.addWidget(self.accept_button)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)