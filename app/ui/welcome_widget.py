"""Plain-language starting point for pilot users of the desktop app."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.managed_workspace import removal_guidance


class WelcomeWidget(QWidget):
    """Explain the two pilot paths without exposing implementation detail."""

    requested_tab = Signal(str)

    def __init__(self):
        super().__init__()

        title = QLabel("Welcome to Illumio Workload Explorer")
        title.setObjectName("welcomeTitle")

        introduction = QLabel(
            "Use Demo Mode to explore safely with mock data, or use your own "
            "approved files to compare CMDB records with Illumio workloads."
        )
        introduction.setWordWrap(True)

        demo_title = QLabel("Demo Mode")
        demo_title.setObjectName("welcomeHeading")
        demo_text = QLabel(
            "1. In Workloads, choose Load Mock Workloads.\n"
            "2. In CMDB, choose Load 300k Mock CMDB.\n"
            "3. In Reconciliation, choose Run Reconciliation.\n\n"
            "The demo uses mock records only. It never contacts a real PCE."
        )
        demo_text.setWordWrap(True)

        import_title = QLabel("Use Your Data")
        import_title.setObjectName("welcomeHeading")
        import_text = QLabel(
            "Import a Workloader CSV in Workloads, then import a CMDB or inventory "
            "file in CMDB. Reconciliation compares the two saved local snapshots."
        )
        import_text.setWordWrap(True)

        pce_title = QLabel("Authorized PCE Access")
        pce_title.setObjectName("welcomeHeading")
        pce_text = QLabel(
            "Only authorized users should configure a live PCE connection. "
            "Connection testing and synchronization are read-only by default. "
            "Label write-back remains separately guarded."
        )
        pce_text.setWordWrap(True)

        local_title = QLabel("Where the data lives")
        local_title.setObjectName("welcomeHeading")
        local_text = QLabel(
            "The app saves its data in a private local PostgreSQL workspace on this "
            "computer. It does not upload demo or imported data to Box. A safe removal "
            "command removes only this app's local workspace; it never changes PCE data.\n\n"
            + removal_guidance()
        )
        local_text.setWordWrap(True)

        workloads_button = QPushButton("Open Workloads")
        cmdb_button = QPushButton("Open CMDB")
        reconciliation_button = QPushButton("Open Reconciliation")
        workloads_button.clicked.connect(lambda: self.requested_tab.emit("Workloads"))
        cmdb_button.clicked.connect(lambda: self.requested_tab.emit("CMDB"))
        reconciliation_button.clicked.connect(
            lambda: self.requested_tab.emit("Reconciliation")
        )

        actions = QHBoxLayout()
        actions.addWidget(workloads_button)
        actions.addWidget(cmdb_button)
        actions.addWidget(reconciliation_button)
        actions.addStretch()

        layout = QVBoxLayout()
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(introduction)
        layout.addSpacing(10)
        layout.addWidget(demo_title)
        layout.addWidget(demo_text)
        layout.addLayout(actions)
        layout.addSpacing(10)
        layout.addWidget(import_title)
        layout.addWidget(import_text)
        layout.addSpacing(10)
        layout.addWidget(pce_title)
        layout.addWidget(pce_text)
        layout.addSpacing(10)
        layout.addWidget(local_title)
        layout.addWidget(local_text)
        layout.addStretch()
        self.setLayout(layout)
