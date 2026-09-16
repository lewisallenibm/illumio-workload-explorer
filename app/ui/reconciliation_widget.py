import time
from math import ceil

from PySide6.QtCore import QSignalBlocker, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.repositories.cmdb_repository import ReconciliationRepository
from app.services.performance import timed
from app.ui.paged_table_model import PagedTableModel
from app.config import settings


# ---------------------------------------------------------------------------
# Display mappings
# ---------------------------------------------------------------------------

_STATUS_DISPLAY = {
    "LABEL_MISMATCH": "Label Mismatch",
    "LABEL_MISSING": "Label Missing",
    "NO_EXPECTED_VALUE": "No Expected Value",
    "ORPHANED_IN_ILLUMIO": "Orphaned in Illumio",
    "MISSING_IN_ILLUMIO": "Missing in Illumio",
    "AMBIGUOUS_MATCH": "Ambiguous Match",
    # Legacy records remain readable.
    "mismatch": "Mismatch", "label_missing": "Label Missing",
    "orphaned": "Orphaned (not in CMDB)", "missing_in_illumio": "Missing in Illumio",
}

_FIELD_DISPLAY = {
    "application": "Application", "role": "Role", "environment": "Environment",
    "location": "Location", "workload": "Workload",
    "role_label": "Role", "env_label": "Environment", "loc_label": "Location",
    "app_label": "Application", "existence": "Existence",
}


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _ReconcileWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            t0 = time.time()
            from app.services.reconciliation_service import ReconciliationService
            result = ReconciliationService.run(
                progress_callback=lambda done, total: self.progress.emit(done, total)
            )
            result["_elapsed"] = time.time() - t0
            self.finished.emit(result)
        except Exception as ex:
            self.error.emit(str(ex))


class _ApplyWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, run_id):
        super().__init__()
        self._run_id = run_id

    def run(self):
        try:
            from app.services.illumio_write_back_service import IllumioWriteBackService
            result = IllumioWriteBackService.apply_approved(run_id=self._run_id)
            self.finished.emit(result)
        except Exception as ex:
            self.error.emit(str(ex))


class _PreflightWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, run_id):
        super().__init__()
        self._run_id = run_id

    def run(self):
        try:
            from app.services.illumio_write_back_service import IllumioWriteBackService
            self.finished.emit(IllumioWriteBackService.preview_approved(run_id=self._run_id))
        except Exception as ex:
            self.error.emit(str(ex))


class _PageWorker(QThread):
    """Fetches a page off the UI thread, reusing stable filter counts."""
    finished = Signal(object, list)    # total, rows
    error = Signal(str)

    def __init__(self, status, field_name, resolution_action, hostname, run_id, limit, offset, cached_total=None):
        super().__init__()
        self._status = status
        self._field_name = field_name
        self._resolution_action = resolution_action
        self._hostname = hostname
        self._run_id = run_id
        self._limit = limit
        self._offset = offset
        self._cached_total = cached_total

    def run(self):
        try:
            total = self._cached_total
            if total is None:
                total = ReconciliationRepository.count(
                    status=self._status,
                    field_name=self._field_name,
                    resolution_action=self._resolution_action,
                    hostname=self._hostname,
                    run_id=self._run_id,
                )
            rows = ReconciliationRepository.search(
                status=self._status,
                field_name=self._field_name,
                resolution_action=self._resolution_action,
                hostname=self._hostname,
                run_id=self._run_id,
                limit=self._limit,
                offset=self._offset,
            )
            self.finished.emit(total, rows)
        except Exception as ex:
            self.error.emit(str(ex))


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class ReconciliationWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.current_page = 0
        self.page_size = 500
        self.total_pages = 1
        latest = ReconciliationRepository.latest_completed_run()
        self._current_run_id = latest.id if latest else None
        self._page_worker = None  # keep reference to prevent GC
        self._request_filter_key = None
        self._filtered_count_cache = {}

        # Debounce timer — fires _reset_refresh 250 ms after last keystroke
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._reset_refresh)

        # ---- Filters ----
        self.hostname_box = QLineEdit()
        self.hostname_box.setPlaceholderText("Filter by hostname…")

        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "All",
            "LABEL_MISMATCH", "LABEL_MISSING", "NO_EXPECTED_VALUE",
            "AMBIGUOUS_MATCH", "ORPHANED_IN_ILLUMIO", "MISSING_IN_ILLUMIO",
        ])

        self.field_filter = QComboBox()
        self.field_filter.addItems([
            "All",
            "application", "role", "environment", "location", "workload",
        ])

        self.action_filter = QComboBox()
        self.action_filter.addItems([
            "All", "pending", "approved", "applied", "skipped", "failed"
        ])

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Hostname"))
        filter_row.addWidget(self.hostname_box, 2)
        filter_row.addWidget(QLabel("Status"))
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(QLabel("Field"))
        filter_row.addWidget(self.field_filter)
        filter_row.addWidget(QLabel("Action"))
        filter_row.addWidget(self.action_filter)

        # ---- Buttons ----
        self.run_button = QPushButton("Run Reconciliation")
        self.approve_button = QPushButton("Approve Selected")
        self.skip_button = QPushButton("Skip Selected")
        self.preflight_button = QPushButton("Preview Approved Changes")
        self.preflight_button.setToolTip(
            "Local-only check of approved changes; it never contacts the PCE"
        )
        self.apply_button = QPushButton("Apply Approved → PCE")
        self.apply_button.setToolTip(
            "Push all approved changes directly to the Illumio PCE via API"
        )

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        action_row = QHBoxLayout()
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.approve_button)
        action_row.addWidget(self.skip_button)
        action_row.addWidget(self.preflight_button)
        action_row.addWidget(self.apply_button)
        action_row.addStretch()

        # ---- Summary ----
        self.summary = QLabel("Run reconciliation to see results.")
        self.run_summary = QLabel()

        # ---- Table ----
        self.table = QTableView()
        self.table_model = PagedTableModel(
            ["Hostname", "Field", "Illumio Value", "CMDB Value", "Status", "Action"],
            ["hostname", "field_name", "illumio_value", "cmdb_value", "status", "resolution_action"],
            self.table,
            formatter=self._format_table_value,
        )
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        # ---- Nav ----
        self.first_btn = QPushButton("|<<")
        self.back_ten_btn = QPushButton("<<")
        self.prev_btn = QPushButton("<")
        self.page_label = QLabel("Page 1 of 1")
        self.next_btn = QPushButton(">")
        self.forward_ten_btn = QPushButton(">>")
        self.last_btn = QPushButton(">>|")
        self.first_btn.setToolTip("First page")
        self.back_ten_btn.setToolTip("Back 10 pages")
        self.prev_btn.setToolTip("Previous page")
        self.next_btn.setToolTip("Next page")
        self.forward_ten_btn.setToolTip("Forward 10 pages")
        self.last_btn.setToolTip("Last page")

        self.jump_spin = QSpinBox()
        self.jump_spin.setMinimum(1)
        self.jump_spin.setMaximum(1)
        self.jump_spin.setFixedWidth(64)
        self.jump_spin.setToolTip("Jump to page")

        self.jump_btn = QPushButton("Go")
        self.jump_btn.setFixedWidth(36)

        nav_row = QHBoxLayout()
        nav_row.addStretch()
        nav_row.addWidget(self.first_btn)
        nav_row.addWidget(self.back_ten_btn)
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.page_label)
        nav_row.addWidget(self.next_btn)
        nav_row.addWidget(self.forward_ten_btn)
        nav_row.addWidget(self.last_btn)
        nav_row.addSpacing(16)
        nav_row.addWidget(QLabel("Jump to page"))
        nav_row.addWidget(self.jump_spin)
        nav_row.addWidget(self.jump_btn)
        nav_row.addStretch()

        # ---- Signals ----
        self.run_button.clicked.connect(self._run_reconciliation)
        self.approve_button.clicked.connect(self._approve_selected)
        self.skip_button.clicked.connect(self._skip_selected)
        self.preflight_button.clicked.connect(self._preview_approved)
        self.apply_button.clicked.connect(self._apply_approved)
        self.hostname_box.textChanged.connect(self._debounce.start)
        self.status_filter.currentTextChanged.connect(self._reset_refresh)
        self.field_filter.currentTextChanged.connect(self._reset_refresh)
        self.action_filter.currentTextChanged.connect(self._reset_refresh)
        self.first_btn.clicked.connect(self._first_page)
        self.back_ten_btn.clicked.connect(self._back_ten_pages)
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        self.forward_ten_btn.clicked.connect(self._forward_ten_pages)
        self.last_btn.clicked.connect(self._last_page)
        self.jump_btn.clicked.connect(self._jump_to_page)

        # ---- Layout ----
        layout = QVBoxLayout()
        layout.addLayout(filter_row)
        layout.addLayout(action_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.run_summary)
        layout.addWidget(self.summary)
        layout.addLayout(nav_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self._refresh()

    # ------------------------------------------------------------------ #
    # Reconciliation run                                                   #
    # ------------------------------------------------------------------ #

    def _run_reconciliation(self):
        self.run_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self._worker = _ReconcileWorker()
        self._worker.progress.connect(
            lambda done, total: (
                self.progress.setRange(0, total),
                self.progress.setValue(done),
            )
        )
        self._worker.finished.connect(self._reconcile_done)
        self._worker.error.connect(self._reconcile_error)
        self._worker.start()

    def _reconcile_done(self, result):
        from app.ui.app_events import app_events
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)
        self._current_run_id = result.get("run_id")
        self._filtered_count_cache.clear()
        elapsed = result.get("_elapsed", 0)
        app_events.status_message.emit(
            f"Reconciliation completed in {elapsed:.1f}s  —  "
            f"Mismatches: {result.get('label_mismatches', 0):,}  "
            f"Missing Labels: {result.get('label_missing', 0):,}  "
            f"Ambiguous: {result.get('ambiguous_matches', 0):,}"
        )
        self.run_summary.setText(
            f"Run {self._current_run_id}  —  "
            f"Illumio: {result.get('total_illumio', 0):,}  "
            f"CMDB: {result.get('total_cmdb', 0):,}  |  "
            f"Matched: {result.get('matched_workloads', 0):,}  "
            f"Mismatches: {result.get('label_mismatches', 0):,}  "
            f"Missing Labels: {result.get('label_missing', 0):,}  "
            f"Ambiguous: {result.get('ambiguous_matches', 0):,}"
        )
        self._show_run_context()
        self._reset_refresh()

    def _reconcile_error(self, msg):
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Reconciliation Failed", msg)

    # ------------------------------------------------------------------ #
    # Approve / Skip / Apply                                               #
    # ------------------------------------------------------------------ #

    def _selected_ids(self):
        rows = self.table.selectionModel().selectedRows()
        return [self.table_model.row_object(index.row()).id for index in rows]

    @staticmethod
    def _format_table_value(column, value, _row):
        if column == "field_name":
            return _FIELD_DISPLAY.get(value, value or "")
        if column == "status":
            return _STATUS_DISPLAY.get(value, value or "")
        if column in ("illumio_value", "cmdb_value"):
            return value or "—"
        return value or ""

    def _approve_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        ReconciliationRepository.mark_approved(ids)
        self._filtered_count_cache.clear()
        self._refresh()

    def _skip_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        ReconciliationRepository.mark_skipped(ids)
        self._filtered_count_cache.clear()
        self._refresh()

    def _apply_approved(self):
        if settings.ILLUMIO_USE_REAL_CLIENT and settings.ILLUMIO_ALLOW_PCE_WRITEBACK:
            answer = QMessageBox.question(
                self,
                "Confirm PCE Write-Back",
                "This will update labels in the real Illumio PCE for approved results. "
                "Run Preview Approved Changes first if you have not already. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.apply_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self._apply_worker = _ApplyWorker(self._current_run_id)
        self._apply_worker.finished.connect(self._apply_done)
        self._apply_worker.error.connect(self._apply_error)
        self._apply_worker.start()

    def _preview_approved(self):
        self.preflight_button.setEnabled(False)
        self._preflight_worker = _PreflightWorker(self._current_run_id)
        self._preflight_worker.finished.connect(self._preflight_done)
        self._preflight_worker.error.connect(self._preflight_error)
        self._preflight_worker.start()

    def _preflight_done(self, result):
        self.preflight_button.setEnabled(True)
        mode = "enabled" if result["real_writes_enabled"] else "disabled"
        QMessageBox.information(
            self,
            "Approved Changes Preview",
            f"Approved results: {result['approved']:,}\n"
            f"Eligible changes: {result['eligible']:,}\n"
            f"Affected workloads: {result['workloads']:,}\n"
            f"Missing workload reference: {result['missing_href']:,}\n"
            f"Unsupported field: {result['unsupported']:,}\n\n"
            f"Real PCE writes are currently {mode}.\n"
            "This preview did not contact the PCE.",
        )

    def _preflight_error(self, msg):
        self.preflight_button.setEnabled(True)
        QMessageBox.critical(self, "Preview Failed", msg)

    def _apply_done(self, result):
        self.apply_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.information(
            self, "Apply Complete",
            f"Applied:  {result.get('applied', 0):,}\n"
            f"Failed:   {result.get('failed', 0):,}\n"
            f"Skipped (no href): {result.get('skipped_no_href', 0):,}\n"
            + (f"\nNote: {result.get('note', '')}" if result.get("note") else "")
        )
        self._filtered_count_cache.clear()
        self._refresh()

    def _apply_error(self, msg):
        self.apply_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Apply Failed", msg)

    def _show_run_context(self):
        context = ReconciliationRepository.get_run_context(self._current_run_id)
        if context is None:
            return
        _, cmdb_run, _, source = context
        cmdb_name = cmdb_run.source_filename if cmdb_run and cmdb_run.source_filename else "Mock/unnamed CMDB"
        illumio_name = source.source_filename if source and source.source_filename else (
            source.source_type if source else "Illumio ingestion"
        )
        self.run_summary.setText(self.run_summary.text() + f"\nCMDB snapshot: {cmdb_name}  |  Illumio snapshot: {illumio_name}")

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _reset_refresh(self):
        self.current_page = 0
        self._filtered_count_cache.clear()
        self._refresh()

    def _filter_key(self):
        return (
            self._current_run_id,
            self.status_filter.currentText(),
            self.field_filter.currentText(),
            self.action_filter.currentText(),
            self.hostname_box.text().strip() or None,
        )

    def _first_page(self):
        self.current_page = 0
        self._refresh()

    def _last_page(self):
        self.current_page = max(0, self.total_pages - 1)
        self._refresh()

    def _back_ten_pages(self):
        if self.current_page > 0:
            self.current_page = max(0, self.current_page - 10)
            self._refresh()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._refresh()

    def _next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._refresh()

    def _forward_ten_pages(self):
        if self.current_page < self.total_pages - 1:
            self.current_page = min(self.total_pages - 1, self.current_page + 10)
            self._refresh()

    def _jump_to_page(self):
        page = self.jump_spin.value() - 1  # spin is 1-based
        page = max(0, min(page, self.total_pages - 1))
        self.current_page = page
        self._refresh()

    def _set_nav_enabled(self, enabled):
        """Disable nav while a page fetch is in flight."""
        for btn in (
            self.first_btn, self.prev_btn,
            self.back_ten_btn, self.next_btn, self.forward_ten_btn,
            self.last_btn, self.jump_btn,
        ):
            btn.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    # Async refresh                                                        #
    # ------------------------------------------------------------------ #

    def _refresh(self):
        """Kick off a background page fetch. Returns immediately."""
        if self._page_worker and self._page_worker.isRunning():
            return

        hostname = self.hostname_box.text().strip() or None
        status = self.status_filter.currentText()
        field = self.field_filter.currentText()
        action = self.action_filter.currentText()
        run_id = self._current_run_id
        offset = self.current_page * self.page_size
        filter_key = self._filter_key()

        self._set_nav_enabled(False)
        self.summary.setText("Loading…")
        self._request_filter_key = filter_key

        self._page_worker = _PageWorker(
            status, field, action, hostname, run_id, self.page_size, offset,
            cached_total=self._filtered_count_cache.get(filter_key),
        )
        self._page_worker.finished.connect(self._on_page_loaded)
        self._page_worker.error.connect(self._on_page_error)
        self._page_worker.start()

    def _on_page_loaded(self, total, rows):
        self._set_nav_enabled(True)
        if self._filter_key() != self._request_filter_key:
            # Do not render/cross-cache a page fetched before a filter change.
            self._page_worker = None
            self._refresh()
            return
        self._filtered_count_cache[self._request_filter_key] = total

        self.total_pages = max(1, ceil(total / self.page_size))
        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1

        offset = self.current_page * self.page_size
        start = offset + 1 if total else 0
        end = offset + len(rows)

        self.summary.setText(
            f"Total results: {total:,}  |  Showing: {start}–{end}"
        )
        self.page_label.setText(
            f"Page {self.current_page + 1} of {self.total_pages}"
        )
        self.first_btn.setEnabled(self.current_page > 0)
        self.back_ten_btn.setEnabled(self.current_page > 0)
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.forward_ten_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.last_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.jump_spin.setMaximum(max(1, self.total_pages))
        self.jump_spin.setValue(self.current_page + 1)

        with timed("reconciliation.ui.table_population"):
            blocker = QSignalBlocker(self.table)
            self.table.setUpdatesEnabled(False)
            try:
                self.table_model.set_rows(rows)
            finally:
                self.table.setUpdatesEnabled(True)
                del blocker

    def _on_page_error(self, msg):
        self._set_nav_enabled(True)
        self.summary.setText(f"Error: {msg}")
