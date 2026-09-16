"""Small, read-only models for the paged browser tables.

``QTableWidget`` creates a Python ``QTableWidgetItem`` for every cell.  At
500--1,000 row page sizes that turns a simple page change into thousands of
allocations and repeated header-size calculations.  A ``QTableView`` asks this
model only for visible cells, so pagination remains independent of page size.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class PagedTableModel(QAbstractTableModel):
    """Read-only table model over lightweight SQLAlchemy row projections."""

    def __init__(self, headers, columns, parent=None, formatter=None):
        super().__init__(parent)
        self._headers = tuple(headers)
        self._columns = tuple(columns)
        self._formatter = formatter
        self._rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_object(self, row):
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        column = self._columns[index.column()]
        value = getattr(self._rows[index.row()], column)
        if self._formatter is not None:
            value = self._formatter(column, value, self._rows[index.row()])
        elif column == "online":
            value = "Yes" if value else "No"
        elif column == "ven_installed":
            value = "Yes" if value else "No" if value is False else "—"
        return "" if value is None else str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return super().headerData(section, orientation, role)
