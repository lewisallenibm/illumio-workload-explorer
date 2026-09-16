from PySide6.QtWidgets import (
    QLabel,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class IllumioWorkloadDetailsWidget(QWidget):

    def __init__(self):
        super().__init__()

        self._tabs = QTabWidget()

        # --- Overview tab ---
        self._overview = QTextEdit()
        self._overview.setReadOnly(True)
        self._tabs.addTab(self._overview, "Overview")

        # --- Labels tab ---
        self._labels_view = QTextEdit()
        self._labels_view.setReadOnly(True)
        self._tabs.addTab(self._labels_view, "Labels")

        # --- Interfaces tab ---
        self._interfaces_view = QTextEdit()
        self._interfaces_view.setReadOnly(True)
        self._tabs.addTab(self._interfaces_view, "Interfaces")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Workload Details"))
        layout.addWidget(self._tabs)
        self.setLayout(layout)

    def clear(self):
        self._overview.clear()
        self._labels_view.clear()
        self._interfaces_view.clear()

    def load_workload(self, workload):

        if workload is None:
            self.clear()
            return

        # ---- Overview ----
        self._overview.setText(
            f"Hostname        {workload.hostname or '—'}\n"
            f"Name            {workload.name or '—'}\n"
            f"\n"
            f"Online          {workload.online}\n"
            f"Connectivity    {workload.connectivity_status or '—'}\n"
            f"\n"
            f"Enforcement     {workload.enforcement_mode or '—'}\n"
            f"Policy Sync     {workload.policy_sync_status or '—'}\n"
            f"Visibility      {getattr(workload, 'visibility_status', None) or '—'}\n"
            f"\n"
            f"Protection      {workload.protection_status or '—'}\n"
            f"Coverage Score  {workload.protection_coverage_score or '—'}\n"
            f"\n"
            f"VEN Version     {workload.ven_version or '—'}\n"
            f"OS              {workload.os or '—'}\n"
            f"OS Release      {workload.os_release or '—'}\n"
        )

        # ---- Labels ----
        label_lines = [
            f"{workload_label.label.label_type or '?':<16} "
            f"{workload_label.label.value or '—'}"
            for workload_label in workload.labels
            if workload_label.label is not None
        ]

        self._labels_view.setText(
            "\n".join(label_lines) if label_lines else "(no labels)"
        )

        # ---- Interfaces ----
        iface_lines = [
            f"{iface.interface_name or '?':<12} {iface.ip_address or '—'}"
            + (
                f"  ({iface.network_name_or_type})"
                if iface.network_name_or_type
                else ""
            )
            for iface in workload.interfaces
        ]

        self._interfaces_view.setText(
            "\n".join(iface_lines) if iface_lines else "(no interfaces)"
        )
