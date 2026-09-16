import logging
import os
import re
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

import PySide6


def configure_qt_platform_plugin_path(plugin_root=None):
    """Point Qt at bundled native platform plugins before any Qt import.

    Conda shells can leave Qt plugin variables empty or point to a different
    Qt installation. PySide must receive this setting before its Qt modules
    initialize their plugin search paths.
    """
    root = Path(plugin_root) if plugin_root is not None else (
        Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
    )
    platform_directory = root / "platforms"
    plugin_directory = platform_directory

    # On some macOS 26 installations Qt's automatic loader can skip the
    # PySide package directory even though it can load libqcocoa.dylib by its
    # absolute path. A stable symbolic link in the system temporary directory gives
    # the loader a clean discovery directory without copying or altering Qt.
    cocoa_plugin = platform_directory / "libqcocoa.dylib"
    if sys.platform == "darwin" and cocoa_plugin.is_file():
        alias_directory = (
            Path(tempfile.gettempdir())
            / f"illumio-workload-explorer-qt-{PySide6.__version__}"
            / "platforms"
        )
        alias_plugin = alias_directory / cocoa_plugin.name
        try:
            alias_directory.mkdir(parents=True, exist_ok=True)
            # This is our own generated file in a versioned temp directory,
            # so replacing it is safe when the runtime changes.
            if alias_plugin.exists() or alias_plugin.is_symlink():
                alias_plugin.unlink()
            alias_plugin.symlink_to(cocoa_plugin)
            if alias_plugin.is_symlink():
                plugin_directory = alias_directory
        except OSError:
            # Leave the normal bundled directory in place if temp storage is
            # unavailable; this keeps the startup path safe and predictable.
            pass

    if plugin_directory.is_dir():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_directory)

    # Qt 6.10 ships the native macOS widget style separately from the Cocoa
    # platform plugin. Expose the complete bundled plugin root before Qt
    # initializes so dark mode retains macOS controls rather than falling
    # back to Qt's square Fusion widgets.
    if sys.platform == "darwin" and root.is_dir():
        os.environ["QT_PLUGIN_PATH"] = str(root)
        os.environ["QT_STYLE_OVERRIDE"] = "macOS"
    return plugin_directory


# Must run before importing PySide6.QtCore, QtGui, or QtWidgets.
configure_qt_platform_plugin_path()

# Packaged pilot builds opt in to an app-owned PostgreSQL workspace before
# app.config and app.database construct their connection engine. Development
# launches keep using the existing developer DATABASE_URL unchanged.
from app.managed_workspace import (
    managed_workspace_enabled,
    prepare_managed_workspace_from_environment,
    stop_managed_workspace,
)

prepare_managed_workspace_from_environment()


from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyleFactory,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Active imports — files that exist and are used by live tabs
# ---------------------------------------------------------------------------
from app.ui.illumio_workloads_widget import IllumioWorkloadsWidget
from app.ui.cmdb_widget import CmdbWidget
from app.ui.reconciliation_widget import ReconciliationWidget
from app.ui.admin_widget import AdminWidget
from app.ui.welcome_widget import WelcomeWidget
from app.ui.app_events import app_events
from app.database import ensure_performance_indexes
from app.database import engine
from app.models.base import Base
# A fresh packaged pilot database starts empty. Import every persistent model
# before calling Base.metadata.create_all() so first launch creates the full
# PostgreSQL schema rather than only whichever models a visible tab happened
# to import first.
import app.models.cmdb_ci
import app.models.cmdb_import_run
import app.models.cmdb_staging_ci
import app.models.import_run
import app.models.reconciliation_result
import app.models.reconciliation_run
import app.models.workload
import app.models.workload_change
import app.models.workload_ip
from app.release_info import APP_NAME, APP_VERSION
from app.scripts.health_check import collect_health
from app.startup_readiness import startup_recovery_message, validate_local_startup


def configure_native_macos_style(application):
    """Apply the bundled Cocoa widget style after Qt has initialized."""
    if sys.platform != "darwin":
        return

    plugin_root = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
    if not plugin_root.is_dir():
        return

    # QT_PLUGIN_PATH is read early by Qt, but explicitly adding the path here
    # ensures the separately shipped libqmacstyle.dylib is discoverable.
    QCoreApplication.addLibraryPath(str(plugin_root))
    native_style = QStyleFactory.create("macOS")
    if native_style is not None:
        application.setStyle(native_style)


def configure_dark_macos_appearance(application):
    """Smooth out Qt 6.10's non-native-looking dark widget chrome on macOS."""
    if sys.platform != "darwin":
        return

    application.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #1c1c1e;
            color: #f5f5f7;
        }
        QLabel#welcomeTitle { font-size: 24px; font-weight: 700; }
        QLabel#welcomeHeading { color: #0a84ff; font-size: 16px; font-weight: 700; }
        QTabWidget::pane { border: 0; }
        QTabBar::tab {
            background: transparent;
            border: 0;
            border-radius: 7px;
            color: #aeaeb2;
            margin: 4px 2px;
            padding: 6px 12px;
        }
        QTabBar::tab:selected {
            background: #3a3a3c;
            color: #ffffff;
        }
        QTabBar::tab:hover:!selected { background: #2c2c2e; }
        QPushButton {
            background: #3a3a3c;
            border: 0;
            border-radius: 6px;
            color: #ffffff;
            min-height: 22px;
            padding: 3px 10px;
        }
        QPushButton:hover { background: #48484a; }
        QPushButton:pressed { background: #636366; }
        QPushButton:disabled { background: #2c2c2e; color: #636366; }
        QLineEdit, QComboBox, QSpinBox, QTextEdit {
            background: #2c2c2e;
            border: 1px solid #48484a;
            border-radius: 6px;
            color: #f5f5f7;
            min-height: 22px;
            padding: 2px 6px;
            selection-background-color: #0a84ff;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
            border: 1px solid #0a84ff;
        }
        QComboBox::drop-down { border: 0; width: 20px; }
        QTableView {
            background: #1c1c1e;
            alternate-background-color: #202023;
            border: 0;
            gridline-color: #2c2c2e;
            selection-background-color: #0a84ff;
            selection-color: #ffffff;
        }
        QHeaderView::section {
            background: #2c2c2e;
            border: 0;
            border-bottom: 1px solid #48484a;
            color: #aeaeb2;
            padding: 5px 7px;
        }
        QScrollBar:vertical {
            background: transparent;
            border: 0;
            margin: 4px;
            width: 10px;
        }
        QScrollBar::handle:vertical {
            background: #636366;
            border-radius: 5px;
            min-height: 28px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { height: 0; background: transparent; }
        """
    )


class RedactingFormatter(logging.Formatter):
    """Prevent credential-shaped values from being persisted in local logs."""

    _assignment = re.compile(
        r"(?i)\b(authorization|password|secret|api[_-]?key(?:[_-]?(?:id|secret))?)\b"
        r"(\s*[:=]\s*)([^\s,;]+)"
    )
    _url_credentials = re.compile(r"(\w+://[^:/\s]+:)([^@\s]+)(@)")

    @classmethod
    def redact(cls, message: str) -> str:
        message = cls._url_credentials.sub(r"\1***\3", message)
        return cls._assignment.sub(r"\1\2***", message)

    def format(self, record):
        return self.redact(super().format(record))


def configure_logging(log_directory="logs"):
    """Keep private rolling app logs and show opt-in timings in Terminal."""
    directory = Path(log_directory)
    directory.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers = [RotatingFileHandler(
        directory / "illumio-workload-explorer.log", maxBytes=2_000_000, backupCount=3,
    )]
    if os.getenv("ILLUMIO_PERF_TIMING", "false").casefold() == "true":
        handlers.append(logging.StreamHandler())
        logging.getLogger("illumio.performance").setLevel(logging.INFO)
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        force=True,
    )


def unexpected_error_message() -> str:
    return (
        f"{APP_NAME} encountered an unexpected problem. Your local data was not "
        "changed by this error. You can close this message and try again. "
        "Technical details were saved in the private application log."
    )


def unexpected_exception_hook(exception_type, value, traceback):
    """Log unexpected failures and show a safe message when Qt is available."""
    logging.getLogger("illumio.application").critical(
        "Unexpected application error", exc_info=(exception_type, value, traceback)
    )
    if QApplication.instance() is None:
        sys.__excepthook__(exception_type, value, traceback)
        return
    try:
        QMessageBox.critical(None, f"{APP_NAME} Error", unexpected_error_message())
    except Exception:
        # Avoid masking the original failure if Qt itself cannot show a dialog.
        logging.getLogger("illumio.application").exception("Unable to show unexpected-error dialog")


def install_exception_hook():
    sys.excepthook = unexpected_exception_hook

# ---------------------------------------------------------------------------
# Legacy imports — used by SearchWidget (currently commented-out tab).
# Files still exist on disk; kept so the tab can be re-enabled without edits.
# ---------------------------------------------------------------------------
from app.services.export_service import ExportService
from app.services.search_service import SearchService
from app.ui.results_table import ResultsTable
from app.ui.workload_details_widget import WorkloadDetailsWidget

# ---------------------------------------------------------------------------
# Commented-out tab widgets — uncomment import + addTab call when ready.
# Files exist but tabs are not yet wired into the main window.
# ---------------------------------------------------------------------------
# from app.ui.dashboard_widget import DashboardWidget
# from app.ui.audit_history_widget import AuditHistoryWidget
# from app.ui.duplicates_widget import DuplicatesWidget
# from app.ui.import_data_widget import ImportDataWidget
# from app.ui.import_history_widget import ImportHistoryWidget
# from app.ui.operations_console_widget import OperationsConsoleWidget
# from app.ui.automation_widget import AutomationWidget  # not yet created
# from app.ui.reports_widget import ReportsWidget        # not yet created


class SearchWidget(QWidget):
    """Legacy search widget — tab currently disabled."""

    def __init__(self):
        super().__init__()

        self.current_results = []

        self.search_box = QLineEdit()

        self.search_button = QPushButton("Search")
        self.export_button = QPushButton("Export Results")

        self.results = ResultsTable()
        self.details = WorkloadDetailsWidget()

        self.search_button.clicked.connect(self.search)
        self.export_button.clicked.connect(self.export_results)
        self.results.itemSelectionChanged.connect(self.show_selected_workload)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Search Value"))
        left_layout.addWidget(self.search_box)
        left_layout.addWidget(self.search_button)
        left_layout.addWidget(self.export_button)
        left_layout.addWidget(self.results)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(self.details)

        layout = QHBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

    def export_results(self):
        if not self.current_results:
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Export Results", "workloads.csv", "CSV Files (*.csv)"
        )
        if not file_name:
            return
        ExportService.export_workloads(self.current_results, file_name)

    def display_results(self, workloads):
        self.current_results = workloads
        self.results.load_workloads(workloads)
        self.details.clear()

    def show_selected_workload(self):
        row = self.results.currentRow()
        if row < 0:
            return
        workload = self.results.workloads[row]
        self.details.load_workload(workload)

    def search(self):
        workloads = SearchService.smart_search(self.search_box.text())
        self.display_results(workloads)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(1400, 800)

        tabs = QTabWidget()

        # Status bar — timing messages from any widget via app_events bus
        self.statusBar().showMessage("Ready")
        app_events.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg)
        )

        # ---- Active tabs ----
        welcome = WelcomeWidget()
        tabs.addTab(welcome, "Welcome")
        tabs.addTab(IllumioWorkloadsWidget(), "Workloads")
        tabs.addTab(CmdbWidget(), "CMDB")
        tabs.addTab(ReconciliationWidget(), "Reconciliation")

        # ---- Disabled tabs (uncomment + restore import to re-enable) ----
        # tabs.addTab(DashboardWidget(), "Dashboard")
        # tabs.addTab(SearchWidget(), "Search")
        # tabs.addTab(ImportHistoryWidget(), "Import History")
        # tabs.addTab(ImportDataWidget(), "Import Data")
        # tabs.addTab(DuplicatesWidget(), "Duplicates")
        tabs.addTab(AdminWidget(), "Admin")
        # tabs.addTab(AuditHistoryWidget(), "Audit History")
        # tabs.addTab(OperationsConsoleWidget(), "Operations Console")
        # tabs.addTab(AutomationWidget(), "Automation")
        # tabs.addTab(ReportsWidget(), "Reports")

        def open_tab(tab_name):
            for index in range(tabs.count()):
                if tabs.tabText(index) == tab_name:
                    tabs.setCurrentIndex(index)
                    return

        welcome.requested_tab.connect(open_tab)

        self.setCentralWidget(tabs)


def main():
    configure_logging()
    logging.getLogger("illumio.application").info("Starting %s version %s", APP_NAME, APP_VERSION)
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(stop_managed_workspace)
    configure_native_macos_style(app)
    configure_dark_macos_appearance(app)
    install_exception_hook()
    try:
        # A frozen pilot package enables its managed workspace automatically;
        # initialize its blank private database before the normal readiness
        # checks run. Development stays on its configured database unless the
        # opt-in environment flag is set.
        if managed_workspace_enabled():
            Base.metadata.create_all(engine)
        validate_local_startup(ensure_performance_indexes, collect_health)
        window = MainWindow()
    except Exception:
        logging.getLogger("illumio.application").exception("Local startup readiness check failed")
        QMessageBox.critical(None, f"{APP_NAME} Startup Check", startup_recovery_message())
        return 1
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
