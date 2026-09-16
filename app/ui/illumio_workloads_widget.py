import time
from math import ceil

from PySide6.QtCore import QSignalBlocker, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QLineEdit,
    QHBoxLayout,
    QSplitter,
    QComboBox,
    QMessageBox,
    QHeaderView,
    QFileDialog,
)

from app.services.illumio.illumio_sync_service import IllumioSyncService
from app.services.illumio.illumio_service import IllumioService
from app.services.illumio.illumio_stats_service import IllumioStatsService
from app.ui.illumio_workload_details_widget import IllumioWorkloadDetailsWidget
from app.ui.paged_table_model import PagedTableModel
from app.ui.bulk_search_dialog import BulkSearchDialog
from app.ui.workloader_import_preview_dialog import WorkloaderImportPreviewDialog
from app.repositories.illumio_workload_repository import IllumioWorkloadRepository
from app.services.performance import timed
from app.services.illumio.workloader_source_adapter import WorkloaderCsvSourceAdapter


class _SyncWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            t0 = time.time()
            result = IllumioSyncService.sync()
            result["_elapsed"] = time.time() - t0
            self.finished.emit(result)
        except Exception as ex:
            self.error.emit(str(ex))


class _WorkloaderImportWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, path):
        super().__init__()
        self._path = path

    def run(self):
        try:
            preview, records = WorkloaderCsvSourceAdapter.load_records(self._path)
            from app.services.illumio.ingestion_service import IllumioIngestionService
            result = IllumioIngestionService.ingest(
                records,
                source=WorkloaderCsvSourceAdapter.source_type,
                source_filename=preview.filename,
            )
            self.finished.emit(result)
        except Exception as ex:
            self.error.emit(str(ex))


class _PcePreflightWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            from app.services.illumio.pce_preflight_service import PcePreflightService
            self.finished.emit(PcePreflightService.check())
        except Exception as ex:
            self.error.emit(str(ex))


class IllumioWorkloadsWidget(QWidget):

    def __init__(self):
        super().__init__()

        # ------------------------------------------------------------------ #
        # State                                                                #
        # ------------------------------------------------------------------ #
        self.current_page = 0
        self.page_size = 500
        self.total_pages = 1

        # When bulk mode is active this holds the pre-fetched workload list
        # and missing terms.  None means we are in normal single-search mode.
        self._bulk_results = None
        self._bulk_missing = []

        # Stats cache — total/online/offline never change between syncs.
        # Recalculating on every page turn wastes 10-20ms for no reason.
        self._stats_cache = {"total": 0, "online": 0, "offline": 0}
        self._filtered_count_cache = {}

        # Debounce timer for search box — wait 250ms after last keystroke
        # before firing a query. Prevents 6 queries for typing "server".
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.reset_and_refresh)

        # ------------------------------------------------------------------ #
        # Row 1 — Search bar only                                             #
        # ------------------------------------------------------------------ #
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "Search hostname, IP, name, label, or Illumio href…"
        )

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search"))
        search_row.addWidget(self.search_box, 1)

        # ------------------------------------------------------------------ #
        # Row 2 — Filters + Bulk Search + Rows                               #
        # ------------------------------------------------------------------ #
        self.bulk_button = QPushButton("Bulk Search…")
        self.bulk_button.setToolTip(
            "Paste up to 10 000 workload identifiers or label values and search all at once"
        )

        self.online_filter = QComboBox()
        self.online_filter.addItems(["All", "Online", "Offline"])

        self.enforcement_filter = QComboBox()
        self.enforcement_filter.addItems(["All", "full", "visibility", "selective"])

        self.page_size_box = QComboBox()
        self.page_size_box.addItems(["100", "250", "500", "1000"])
        self.page_size_box.setCurrentText("500")

        filters_row = QHBoxLayout()
        filters_row.addWidget(self.bulk_button)
        filters_row.addSpacing(16)
        filters_row.addWidget(QLabel("Online"))
        filters_row.addWidget(self.online_filter)
        filters_row.addSpacing(8)
        filters_row.addWidget(QLabel("Enforcement"))
        filters_row.addWidget(self.enforcement_filter)
        filters_row.addSpacing(8)
        filters_row.addWidget(QLabel("Rows"))
        filters_row.addWidget(self.page_size_box)
        filters_row.addStretch()

        # ------------------------------------------------------------------ #
        # Row 2 — Navigation                                                  #
        # ------------------------------------------------------------------ #
        self.first_button = QPushButton("|<<")
        self.back_ten_button = QPushButton("<<")
        self.prev_button = QPushButton("<")
        self.page_label = QLabel("Page 1 of 1")
        self.next_button = QPushButton(">")
        self.forward_ten_button = QPushButton(">>")
        self.last_button = QPushButton(">>|")

        self.jump_page = QLineEdit()
        self.jump_page.setFixedWidth(60)
        self.go_button = QPushButton("Go")

        nav_row = QHBoxLayout()
        nav_row.addStretch()
        nav_row.addWidget(self.first_button)
        nav_row.addWidget(self.back_ten_button)
        nav_row.addWidget(self.prev_button)
        nav_row.addWidget(self.page_label)
        nav_row.addWidget(self.next_button)
        nav_row.addWidget(self.forward_ten_button)
        nav_row.addWidget(self.last_button)
        nav_row.addSpacing(20)
        nav_row.addWidget(QLabel("Jump To Page"))
        nav_row.addWidget(self.jump_page)
        nav_row.addWidget(self.go_button)
        nav_row.addStretch()

        # ------------------------------------------------------------------ #
        # Row 3 — Actions                                                     #
        # ------------------------------------------------------------------ #
        self.sync_button = QPushButton(self._sync_button_label())
        self.sync_button.setToolTip(self._sync_button_tooltip())
        self.pce_preflight_button = QPushButton("Test PCE Connection")
        self.pce_preflight_button.setToolTip(
            "Read-only one-row PCE access test; never changes PCE data"
        )
        self.import_workloader_button = QPushButton("Import Workloader Export…")
        self.import_workloader_button.setToolTip(
            "Validate and import a local Workloader CSV into the current Illumio dataset"
        )
        self.clear_bulk_button = QPushButton("Clear Bulk Search")
        self.clear_bulk_button.setVisible(False)

        action_row = QHBoxLayout()
        action_row.addWidget(self.sync_button)
        action_row.addWidget(self.pce_preflight_button)
        action_row.addWidget(self.import_workloader_button)
        action_row.addWidget(self.clear_bulk_button)
        action_row.addStretch()

        # ------------------------------------------------------------------ #
        # Row 4 — Summary                                                     #
        # ------------------------------------------------------------------ #
        self.summary = QLabel()
        self.source_metadata = QLabel("Source: no completed ingestion yet")

        # ------------------------------------------------------------------ #
        # Table + details splitter                                            #
        # ------------------------------------------------------------------ #
        self.table = QTableView()
        self.table_model = PagedTableModel(
            ["Hostname", "Online", "Enforcement", "VEN Version", "OS"],
            ["hostname", "online", "enforcement_mode", "ven_version", "os"],
            self.table,
        )
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows
        )

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)         # Hostname
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # Online
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Enforcement
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # VEN Version
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)            # OS
        self.table.setColumnWidth(4, 90)

        self.details = IllumioWorkloadDetailsWidget()

        self.workloads = []

        # ------------------------------------------------------------------ #
        # Wire signals                                                        #
        # ------------------------------------------------------------------ #
        self.sync_button.clicked.connect(self.run_sync)
        self.pce_preflight_button.clicked.connect(self.test_pce_connection)
        self.import_workloader_button.clicked.connect(self.import_workloader_export)
        self.bulk_button.clicked.connect(self.open_bulk_search)
        self.clear_bulk_button.clicked.connect(self.clear_bulk_search)

        # Search box: debounced — fires 250ms after typing stops
        self.search_box.textChanged.connect(
            lambda: self._search_timer.start()
        )
        self.online_filter.currentTextChanged.connect(self.reset_and_refresh)
        self.enforcement_filter.currentTextChanged.connect(self.reset_and_refresh)
        self.page_size_box.currentTextChanged.connect(self.change_page_size)

        self.first_button.clicked.connect(self.first_page)
        self.back_ten_button.clicked.connect(self.back_ten_pages)
        self.prev_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)
        self.forward_ten_button.clicked.connect(self.forward_ten_pages)
        self.last_button.clicked.connect(self.last_page)
        self.go_button.clicked.connect(self.jump_to_page)

        self.table.selectionModel().selectionChanged.connect(self.show_selected_workload)

        # ------------------------------------------------------------------ #
        # Layout assembly                                                     #
        # ------------------------------------------------------------------ #
        left_layout = QVBoxLayout()
        left_layout.addLayout(search_row)
        left_layout.addLayout(filters_row)
        left_layout.addLayout(nav_row)
        left_layout.addLayout(action_row)
        left_layout.addWidget(self.summary)
        left_layout.addWidget(self.source_metadata)
        left_layout.addWidget(self.table)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(self.details)
        splitter.setSizes([900, 380])

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        # Initial load — populate stats cache on first run
        self.refresh(refresh_stats=True)
        self.refresh_source_metadata()

    # ---------------------------------------------------------------------- #
    # Bulk search                                                             #
    # ---------------------------------------------------------------------- #

    def open_bulk_search(self):

        dlg = BulkSearchDialog(
            self,
            "hostnames, IP addresses, names, labels, or Illumio hrefs",
        )

        if dlg.exec() != BulkSearchDialog.DialogCode.Accepted:
            return

        if not dlg.terms:
            return

        online = self._current_online_filter()
        enforcement = self._current_enforcement_filter()

        result = IllumioWorkloadRepository.bulk_search(
            terms=dlg.terms,
            online=online,
            enforcement=enforcement,
        )

        self._bulk_results = result["found"]
        self._bulk_missing = result["missing"]

        self.search_box.setEnabled(False)
        self.clear_bulk_button.setVisible(True)
        self.current_page = 0

        self._render_bulk()

    def clear_bulk_search(self):

        self._bulk_results = None
        self._bulk_missing = []
        self.search_box.setEnabled(True)
        self.clear_bulk_button.setVisible(False)
        self.reset_and_refresh()

    def _render_bulk(self):
        """Paginate and display the bulk result set."""

        all_workloads = self._bulk_results or []
        total = len(all_workloads)

        self.total_pages = max(1, ceil(total / self.page_size))

        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1

        offset = self.current_page * self.page_size
        page_workloads = all_workloads[offset: offset + self.page_size]

        self.workloads = page_workloads

        start_row = offset + 1 if total else 0
        end_row = offset + len(page_workloads)

        stats = IllumioStatsService.get_summary()

        missing_note = (
            f"  |  Missing: {len(self._bulk_missing)}"
            if self._bulk_missing
            else ""
        )

        self.summary.setText(
            f"BULK MODE  —  Found: {total}  |  "
            f"Showing: {start_row}–{end_row}{missing_note}  |  "
            f"Total in DB: {stats['total']}  "
            f"Online: {stats['online']}  Offline: {stats['offline']}"
        )

        self.page_label.setText(
            f"Page {self.current_page + 1} of {self.total_pages}"
        )

        self.update_navigation()
        self._populate_table(page_workloads)

        if self._bulk_missing:
            # Show a non-blocking summary of unmatched terms the first time
            # (only when the user just ran a bulk search, not on page turns)
            pass  # optionally surface a tooltip / status bar message

    # ---------------------------------------------------------------------- #
    # Normal (single-term) search helpers                                    #
    # ---------------------------------------------------------------------- #

    def _current_online_filter(self):
        text = self.online_filter.currentText()
        if text == "Online":
            return True
        if text == "Offline":
            return False
        return None

    def _current_enforcement_filter(self):
        text = self.enforcement_filter.currentText()
        return text if text != "All" else None

    def reset_and_refresh(self):
        # Filter or search changed — filtered_count changes, stats stay same
        self.current_page = 0
        self._filtered_count_cache.clear()
        self.refresh(refresh_stats=False)

    def change_page_size(self):
        self.page_size = int(self.page_size_box.currentText())
        self.current_page = 0
        self.refresh(refresh_stats=False)

    # ---------------------------------------------------------------------- #
    # Navigation                                                              #
    # ---------------------------------------------------------------------- #

    def first_page(self):
        self.current_page = 0
        self.refresh()

    def last_page(self):
        self.current_page = max(0, self.total_pages - 1)
        self.refresh()

    def back_ten_pages(self):
        self.current_page = max(0, self.current_page - 10)
        self.refresh()

    def forward_ten_pages(self):
        self.current_page = min(self.total_pages - 1, self.current_page + 10)
        self.refresh()

    def previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh()

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.refresh()

    def jump_to_page(self):
        try:
            page = int(self.jump_page.text())
            page = max(1, min(page, self.total_pages))
            self.current_page = page - 1
            self.refresh()
        except ValueError:
            pass

    def update_navigation(self):

        first_page = self.current_page == 0
        last_page = self.current_page >= self.total_pages - 1

        self.first_button.setEnabled(not first_page)
        self.back_ten_button.setEnabled(self.current_page >= 10)
        self.prev_button.setEnabled(not first_page)
        self.next_button.setEnabled(not last_page)
        self.forward_ten_button.setEnabled(
            self.current_page + 10 < self.total_pages
        )
        self.last_button.setEnabled(not last_page)

    # ---------------------------------------------------------------------- #
    # Sync                                                                    #
    # ---------------------------------------------------------------------- #

    @staticmethod
    def _sync_button_label():
        return "Sync Illumio PCE (Read Only)" if IllumioService.using_real_client() else "Sync Mock Illumio"

    @staticmethod
    def _sync_button_tooltip():
        if IllumioService.using_real_client():
            return "Reads workloads from the configured PCE and stores a local snapshot; it never writes to PCE."
        return "Generates and stores the local mock Illumio dataset."

    def run_sync(self):
        self.sync_button.setEnabled(False)
        self.sync_button.setText(
            "Syncing PCE (Read Only)…" if IllumioService.using_real_client() else "Syncing Mock Data…"
        )
        self._sync_worker = _SyncWorker()
        self._sync_worker.finished.connect(self._sync_done)
        self._sync_worker.error.connect(self._sync_error)
        self._sync_worker.start()

    def test_pce_connection(self):
        self.pce_preflight_button.setEnabled(False)
        self._pce_preflight_worker = _PcePreflightWorker()
        self._pce_preflight_worker.finished.connect(self._pce_preflight_done)
        self._pce_preflight_worker.error.connect(self._pce_preflight_error)
        self._pce_preflight_worker.start()

    def _pce_preflight_done(self, result):
        self.pce_preflight_button.setEnabled(True)
        if result["status"] == "DISABLED":
            QMessageBox.information(self, "PCE Connection", result["message"])
            return
        count = result.get("workload_count")
        count_text = f"\nPCE workload count: {count:,}" if count is not None else ""
        QMessageBox.information(
            self,
            "PCE Connection",
            "Read-only PCE connection succeeded. No PCE data was changed." + count_text,
        )

    def _pce_preflight_error(self, message):
        self.pce_preflight_button.setEnabled(True)
        QMessageBox.critical(self, "PCE Connection Failed", message)

    def import_workloader_export(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Workloader Export", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        preview = WorkloaderCsvSourceAdapter.preview(path)
        dialog = WorkloaderImportPreviewDialog(preview, self)
        if dialog.exec() != WorkloaderImportPreviewDialog.DialogCode.Accepted:
            return

        self.import_workloader_button.setEnabled(False)
        self.import_workloader_button.setText("Importing…")
        self._workloader_import_worker = _WorkloaderImportWorker(path)
        self._workloader_import_worker.finished.connect(self._workloader_import_done)
        self._workloader_import_worker.error.connect(self._workloader_import_error)
        self._workloader_import_worker.start()

    def _sync_done(self, result):
        from app.ui.app_events import app_events
        self.sync_button.setEnabled(True)
        self.sync_button.setText(self._sync_button_label())
        elapsed = result.get("_elapsed", 0)
        inserted = result.get("inserted", 0)
        app_events.status_message.emit(
            f"Sync completed in {elapsed:.1f}s  —  "
            f"Inserted: {inserted:,}  |  "
            f"Received: {result.get('received', 0):,}"
        )
        # Sync changed the data — refresh stats too
        self._filtered_count_cache.clear()
        self.refresh(refresh_stats=True)
        self.refresh_source_metadata()

    def _sync_error(self, msg):
        from app.ui.app_events import app_events
        self.sync_button.setEnabled(True)
        self.sync_button.setText(self._sync_button_label())
        app_events.status_message.emit(f"Sync failed: {msg}")
        QMessageBox.critical(self, "Sync Failed", msg)

    def _workloader_import_done(self, result):
        self.import_workloader_button.setEnabled(True)
        self.import_workloader_button.setText("Import Workloader Export…")
        from app.ui.app_events import app_events
        app_events.status_message.emit(
            f"Workloader import complete — Received: {result['received']:,}  "
            f"Inserted: {result['inserted']:,}  Updated: {result['updated']:,}"
        )
        self.refresh(refresh_stats=True)
        self.refresh_source_metadata()

    def _workloader_import_error(self, message):
        self.import_workloader_button.setEnabled(True)
        self.import_workloader_button.setText("Import Workloader Export…")
        QMessageBox.critical(self, "Workloader Import Failed", message)

    def refresh_source_metadata(self):
        metadata = IllumioWorkloadRepository.latest_ingestion_metadata()
        if metadata is None:
            self.source_metadata.setText("Source: no completed ingestion yet")
            return
        source, run = metadata
        source_names = {
            "mock": "Mock Illumio",
            "illumio_api": "Illumio API",
            "workloader_csv": "Workloader CSV",
        }
        filename = f"  |  File: {source.source_filename}" if source.source_filename else ""
        completed = run.completed_at.strftime("%Y-%m-%d %H:%M:%S")
        self.source_metadata.setText(
            f"Source: {source_names.get(source.source_type, source.source_type)}{filename}  |  "
            f"Last completed: {completed}  |  Received: {run.records_received:,}  "
            f"Inserted: {run.records_inserted:,}  Updated: {run.records_updated:,}"
        )

    # ---------------------------------------------------------------------- #
    # Table population                                                        #
    # ---------------------------------------------------------------------- #

    def show_selected_workload(self):
        row = self.table.currentIndex().row()
        if row < 0:
            return
        if row >= len(self.workloads):
            return
        # workloads list contains lightweight rows — load full object for details
        lightweight = self.workloads[row]
        workload_id = lightweight.id
        full = IllumioWorkloadRepository.get_by_id(workload_id)
        self.details.load_workload(full)

    def _populate_table(self, workloads):
        with timed("workloads.ui.table_population"):
            blocker = QSignalBlocker(self.table)
            self.table.setUpdatesEnabled(False)
            try:
                self.table_model.set_rows(workloads)
            finally:
                self.table.setUpdatesEnabled(True)
                del blocker

    # ---------------------------------------------------------------------- #
    # Main refresh                                                            #
    # ---------------------------------------------------------------------- #

    def refresh(self, refresh_stats=False):
        """
        refresh_stats=True  → re-query total/online/offline (after sync or filter change)
        refresh_stats=False → use cached stats (page turns — saves 10-20ms per click)
        """

        # If bulk mode is active, re-paginate the cached results
        if self._bulk_results is not None:
            self._render_bulk()
            return

        # Only hit the DB for stats when something that changes them happened
        if refresh_stats:
            self._stats_cache = IllumioStatsService.get_summary()

        stats = self._stats_cache

        search_text = self.search_box.text().strip()
        online = self._current_online_filter()
        enforcement = self._current_enforcement_filter()

        filter_key = (search_text, online, enforcement)
        filtered_count = self._filtered_count_cache.get(filter_key)
        if filtered_count is None:
            filtered_count = IllumioWorkloadRepository.count(
                search_text=search_text,
                online=online,
                enforcement=enforcement,
            )
            self._filtered_count_cache[filter_key] = filtered_count

        self.total_pages = max(1, ceil(filtered_count / self.page_size))

        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1

        offset = self.current_page * self.page_size

        workloads = IllumioWorkloadRepository.search(
            search_text=search_text,
            online=online,
            enforcement=enforcement,
            limit=self.page_size,
            offset=offset,
        )

        self.workloads = workloads

        start_row = offset + 1 if filtered_count else 0
        end_row = min(offset + len(workloads), filtered_count)

        self.summary.setText(
            f"Total: {stats['total']}  |  "
            f"Filtered: {filtered_count}  |  "
            f"Showing: {start_row}–{end_row}  |  "
            f"Online: {stats['online']}  Offline: {stats['offline']}"
        )

        self.page_label.setText(
            f"Page {self.current_page + 1} of {self.total_pages}"
        )

        self.update_navigation()
        self._populate_table(workloads)
