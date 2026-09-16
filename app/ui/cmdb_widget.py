import time
from math import ceil

from PySide6.QtCore import Qt, QSignalBlocker, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
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

from app.repositories.cmdb_repository import CmdbRepository
from app.services.cmdb_import_service import CmdbImportService
from app.services.performance import timed
from app.ui.bulk_search_dialog import BulkSearchDialog
from app.ui.cmdb_import_preview_dialog import CmdbImportPreviewDialog
from app.ui.paged_table_model import PagedTableModel


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _ImportWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, path):
        super().__init__()
        self._path = path

    def run(self):
        try:
            result = CmdbImportService.import_file(self._path)
            self.finished.emit(result)
        except Exception as ex:
            self.error.emit(str(ex))


class _PreviewWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path):
        super().__init__()
        self._path = path

    def run(self):
        try:
            self.finished.emit(CmdbImportService.preview(self._path))
        except Exception as ex:
            self.error.emit(str(ex))


class _MockCmdbWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            t0 = time.time()
            from app.services.mock_cmdb_sync_service import MockCmdbSyncService
            result = MockCmdbSyncService.sync(
                count=300_000,
                progress_callback=lambda done, total: self.progress.emit(done, total),
            )
            result["_elapsed"] = time.time() - t0
            self.finished.emit(result)
        except Exception as ex:
            self.error.emit(str(ex))


class _PageWorker(QThread):
    """Fetches a page off the UI thread, reusing stable filter counts."""
    finished = Signal(object, object, list)   # total, db_total, rows
    error = Signal(str)

    def __init__(self, search_text, app, region, limit, offset, cached_total=None, cached_db_total=None):
        super().__init__()
        self._search_text = search_text
        self._app = app
        self._region = region
        self._limit = limit
        self._offset = offset
        self._cached_total = cached_total
        self._cached_db_total = cached_db_total

    def run(self):
        try:
            total = self._cached_total
            if total is None:
                total = CmdbRepository.count(
                    search_text=self._search_text,
                    app=self._app,
                    region=self._region,
                )
            db_total = self._cached_db_total
            if db_total is None:
                db_total = CmdbRepository.total_count()
            rows = CmdbRepository.search(
                search_text=self._search_text,
                app=self._app,
                region=self._region,
                limit=self._limit,
                offset=self._offset,
            )
            self.finished.emit(total, db_total, rows)
        except Exception as ex:
            self.error.emit(str(ex))


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class CmdbWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.current_page = 0
        self.page_size = 500
        self.total_pages = 1
        self._page_worker = None  # keep reference to prevent GC
        self._request_filter_key = None
        self._filtered_count_cache = {}
        self._db_total_cache = None
        self._bulk_results = None
        self._bulk_missing = []

        # Debounce timer — fires _reset_refresh 250 ms after last keystroke
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._reset_refresh)

        # ---- Controls ----
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search hostname, CI ID, labels, IP, or inventory values…")

        self.bulk_button = QPushButton("Bulk Search…")
        self.bulk_button.setToolTip(
            "Paste up to 10 000 hostnames, CI identifiers, labels, IPs, or inventory values"
        )
        self.clear_bulk_button = QPushButton("Clear Bulk Search")
        self.clear_bulk_button.setVisible(False)

        self.app_box = QLineEdit()
        self.app_box.setPlaceholderText("Filter by application…")

        self.region_box = QLineEdit()
        self.region_box.setPlaceholderText("Filter by region…")

        self.import_button = QPushButton("Import CMDB / Inventory…")
        self.import_button.setToolTip("Import a CSV or XLSX CMDB export")

        self.mock_button = QPushButton("Load 300k Mock CMDB")
        self.mock_button.setToolTip(
            "Generate and load 300 000 mock CMDB records "
            "(uses existing Illumio hostnames for overlap)"
        )

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)

        self.summary = QLabel("Loading…")
        self.source_metadata = QLabel("Source: no completed CMDB import yet")

        # ---- Table ----
        self.table = QTableView()
        self.table_model = PagedTableModel(
            ["Hostname", "App", "Role", "Env", "Loc", "Region", "VEN Installed"],
            ["hostname", "cmdb_app", "cmdb_role", "cmdb_env", "cmdb_loc", "region", "ven_installed"],
            self.table,
        )
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
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
        self.import_button.clicked.connect(self._import_file)
        self.mock_button.clicked.connect(self._load_mock)
        self.bulk_button.clicked.connect(self.open_bulk_search)
        self.clear_bulk_button.clicked.connect(self.clear_bulk_search)
        self.search_box.textChanged.connect(self._debounce.start)
        self.app_box.textChanged.connect(self._debounce.start)
        self.region_box.textChanged.connect(self._debounce.start)
        self.first_btn.clicked.connect(self._first_page)
        self.back_ten_btn.clicked.connect(self._back_ten_pages)
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        self.forward_ten_btn.clicked.connect(self._forward_ten_pages)
        self.last_btn.clicked.connect(self._last_page)
        self.jump_btn.clicked.connect(self._jump_to_page)

        # ---- Layout ----
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search"))
        filter_row.addWidget(self.search_box, 2)
        filter_row.addWidget(QLabel("App"))
        filter_row.addWidget(self.app_box, 1)
        filter_row.addWidget(QLabel("Region"))
        filter_row.addWidget(self.region_box, 1)

        action_row = QHBoxLayout()
        action_row.addWidget(self.import_button)
        action_row.addWidget(self.mock_button)
        action_row.addWidget(self.bulk_button)
        action_row.addWidget(self.clear_bulk_button)
        action_row.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(filter_row)
        layout.addLayout(action_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.summary)
        layout.addWidget(self.source_metadata)
        layout.addLayout(nav_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self._refresh()
        self.refresh_source_metadata()

    # ------------------------------------------------------------------ #
    # Bulk search                                                          #
    # ------------------------------------------------------------------ #

    def open_bulk_search(self):
        dialog = BulkSearchDialog(
            self,
            "hostnames, CI identifiers, labels, IP addresses, or inventory values",
        )
        if dialog.exec() != BulkSearchDialog.DialogCode.Accepted:
            return
        if not dialog.terms:
            return

        _search_text, app, region = self._filter_key()
        result = CmdbRepository.bulk_search(dialog.terms, app=app, region=region)
        self._bulk_results = result["found"]
        self._bulk_missing = result["missing"]
        self.current_page = 0
        self.search_box.setEnabled(False)
        self.app_box.setEnabled(False)
        self.region_box.setEnabled(False)
        self.bulk_button.setEnabled(False)
        self.clear_bulk_button.setVisible(True)
        self._render_bulk()

    def clear_bulk_search(self):
        self._bulk_results = None
        self._bulk_missing = []
        self.search_box.setEnabled(True)
        self.app_box.setEnabled(True)
        self.region_box.setEnabled(True)
        self.bulk_button.setEnabled(True)
        self.clear_bulk_button.setVisible(False)
        self._reset_refresh()

    def _render_bulk(self):
        rows = self._bulk_results or []
        total = len(rows)
        self.total_pages = max(1, ceil(total / self.page_size))
        self.current_page = min(self.current_page, self.total_pages - 1)
        offset = self.current_page * self.page_size
        page_rows = rows[offset:offset + self.page_size]
        start = offset + 1 if total else 0
        end = offset + len(page_rows)
        missing = f"  |  Missing: {len(self._bulk_missing):,}" if self._bulk_missing else ""
        self.summary.setText(
            f"Bulk CMDB results: {total:,}  |  Showing: {start}–{end}{missing}"
        )
        self._update_navigation()
        with timed("cmdb.ui.table_population"):
            blocker = QSignalBlocker(self.table)
            self.table.setUpdatesEnabled(False)
            try:
                self.table_model.set_rows(page_rows)
            finally:
                self.table.setUpdatesEnabled(True)
                del blocker

        if self._bulk_missing:
            QMessageBox.information(
                self,
                "Bulk Search Complete",
                f"Found {total:,} CMDB record(s).\n"
                f"No matching record for {len(self._bulk_missing):,} pasted value(s).",
            )

    # ------------------------------------------------------------------ #
    # Import                                                               #
    # ------------------------------------------------------------------ #

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import CMDB File", "",
            "Data Files (*.csv *.xlsx *.xls)"
        )
        if not path:
            return

        self.import_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate

        self._preview_worker = _PreviewWorker(path)
        self._preview_worker.finished.connect(lambda preview: self._preview_done(path, preview))
        self._preview_worker.error.connect(self._import_error)
        self._preview_worker.start()

    def _preview_done(self, path, preview):
        self.progress.setVisible(False)
        dialog = CmdbImportPreviewDialog(preview, self)
        if dialog.exec() != CmdbImportPreviewDialog.DialogCode.Accepted:
            self.import_button.setEnabled(True)
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._worker = _ImportWorker(path)
        self._worker.finished.connect(self._import_done)
        self._worker.error.connect(self._import_error)
        self._worker.start()

    def _import_done(self, result):
        from app.ui.app_events import app_events
        self.import_button.setEnabled(True)
        self.progress.setVisible(False)
        elapsed = result.get("duration_seconds", 0)
        app_events.status_message.emit(
            f"CMDB import completed in {elapsed:.1f}s  —  "
            f"Inserted: {result['inserted']:,}  Rejected: {result['rejected']:,}"
        )
        QMessageBox.information(
            self, "Import Complete",
            f"Inserted: {result['inserted']:,}\n"
            f"Rejected: {result['rejected']:,}\n"
            f"Duplicates retained: {result['duplicates']:,}\n"
            f"Duration: {elapsed:.1f}s"
        )
        self._invalidate_counts()
        self._reset_refresh()
        self.refresh_source_metadata()

    def _import_error(self, msg):
        self.import_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Import Failed", msg)

    def _load_mock(self):
        self.mock_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 300_000)

        self._mock_worker = _MockCmdbWorker()
        self._mock_worker.progress.connect(
            lambda done, total: self.progress.setValue(done)
        )
        self._mock_worker.finished.connect(self._mock_done)
        self._mock_worker.error.connect(self._mock_error)
        self._mock_worker.start()

    def _mock_done(self, result):
        from app.ui.app_events import app_events
        self.mock_button.setEnabled(True)
        self.progress.setVisible(False)
        elapsed = result.get("_elapsed", result.get("duration_seconds", 0))
        app_events.status_message.emit(
            f"Mock CMDB loaded in {elapsed:.1f}s  —  "
            f"Inserted: {result['inserted']:,}"
        )
        QMessageBox.information(
            self, "Mock CMDB Loaded",
            f"Inserted: {result['inserted']:,}\n"
            f"Duration: {elapsed:.1f}s"
        )
        self._invalidate_counts()
        self._reset_refresh()
        self.refresh_source_metadata()

    def _mock_error(self, msg):
        self.mock_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Mock Load Failed", msg)

    def refresh_source_metadata(self):
        run = CmdbRepository.latest_import_metadata()
        if run is None:
            self.source_metadata.setText("Source: no completed CMDB import yet")
            return
        names = {
            "inventory_csv": "Inventory CSV",
            "inventory_xlsx": "Inventory XLSX",
            "inventory_xls": "Inventory XLS",
            "mock_cmdb": "Mock CMDB",
        }
        filename = f"  |  File: {run.source_filename}" if run.source_filename else ""
        completed = run.completed_at.strftime("%Y-%m-%d %H:%M:%S")
        self.source_metadata.setText(
            f"Source: {names.get(run.source_type, run.source_type)}{filename}  |  "
            f"Imported: {completed}  |  Records: {run.records_inserted:,}"
        )

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _reset_refresh(self):
        self.current_page = 0
        self._filtered_count_cache.clear()
        self._refresh()

    def _invalidate_counts(self):
        self._filtered_count_cache.clear()
        self._db_total_cache = None

    def _filter_key(self):
        return (
            self.search_box.text().strip() or None,
            self.app_box.text().strip() or None,
            self.region_box.text().strip() or None,
        )

    def _first_page(self):
        self.current_page = 0
        self._refresh_or_render_bulk()

    def _last_page(self):
        self.current_page = max(0, self.total_pages - 1)
        self._refresh_or_render_bulk()

    def _back_ten_pages(self):
        if self.current_page > 0:
            self.current_page = max(0, self.current_page - 10)
            self._refresh_or_render_bulk()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._refresh_or_render_bulk()

    def _next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._refresh_or_render_bulk()

    def _forward_ten_pages(self):
        if self.current_page < self.total_pages - 1:
            self.current_page = min(self.total_pages - 1, self.current_page + 10)
            self._refresh_or_render_bulk()

    def _jump_to_page(self):
        page = self.jump_spin.value() - 1  # spin is 1-based
        page = max(0, min(page, self.total_pages - 1))
        self.current_page = page
        self._refresh_or_render_bulk()

    def _refresh_or_render_bulk(self):
        if getattr(self, "_bulk_results", None) is not None:
            self._render_bulk()
        else:
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
        # If a previous fetch is still running, let it finish — ignore
        if self._page_worker and self._page_worker.isRunning():
            return

        search_text, app, region = self._filter_key()
        filter_key = (search_text, app, region)
        offset = self.current_page * self.page_size

        self._set_nav_enabled(False)
        self.summary.setText("Loading…")
        self._request_filter_key = filter_key

        self._page_worker = _PageWorker(
            search_text, app, region, self.page_size, offset,
            cached_total=self._filtered_count_cache.get(filter_key),
            cached_db_total=self._db_total_cache,
        )
        self._page_worker.finished.connect(self._on_page_loaded)
        self._page_worker.error.connect(self._on_page_error)
        self._page_worker.start()

    def _on_page_loaded(self, total, db_total, rows):
        self._set_nav_enabled(True)
        if self._filter_key() != self._request_filter_key:
            # A debounced filter changed while the old page was in flight.
            # Never render or cache those stale results under the new filter.
            self._page_worker = None
            self._refresh()
            return
        self._filtered_count_cache[self._request_filter_key] = total
        self._db_total_cache = db_total

        self.total_pages = max(1, ceil(total / self.page_size))
        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1

        offset = self.current_page * self.page_size
        start = offset + 1 if total else 0
        end = offset + len(rows)

        self.summary.setText(
            f"Total CMDB: {db_total:,}  |  Filtered: {total:,}  |  Showing: {start}–{end}"
        )
        self._update_navigation()

        with timed("cmdb.ui.table_population"):
            blocker = QSignalBlocker(self.table)
            self.table.setUpdatesEnabled(False)
            try:
                self.table_model.set_rows(rows)
            finally:
                self.table.setUpdatesEnabled(True)
                del blocker

    def _update_navigation(self):
        self.page_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
        self.first_btn.setEnabled(self.current_page > 0)
        self.back_ten_btn.setEnabled(self.current_page > 0)
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.forward_ten_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.last_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.jump_spin.setMaximum(max(1, self.total_pages))
        self.jump_spin.setValue(self.current_page + 1)

    def _on_page_error(self, msg):
        self._set_nav_enabled(True)
        self.summary.setText(f"Error: {msg}")
