import pytest

from app.ui.cmdb_widget import CmdbWidget
from app.ui.reconciliation_widget import ReconciliationWidget


@pytest.mark.parametrize("widget_class", [CmdbWidget, ReconciliationWidget])
def test_page_navigation_supports_one_and_ten_page_steps(widget_class):
    widget = widget_class.__new__(widget_class)
    widget.current_page = 15
    widget.total_pages = 24
    refreshes = []
    widget._refresh = lambda: refreshes.append(widget.current_page)

    widget._prev_page()
    widget._back_ten_pages()
    widget._next_page()
    widget._forward_ten_pages()
    widget._last_page()
    widget._first_page()

    assert refreshes == [14, 4, 5, 15, 23, 0]


@pytest.mark.parametrize("widget_class", [CmdbWidget, ReconciliationWidget])
def test_ten_page_navigation_stays_within_first_and_last_page(widget_class):
    widget = widget_class.__new__(widget_class)
    widget.current_page = 3
    widget.total_pages = 9
    refreshes = []
    widget._refresh = lambda: refreshes.append(widget.current_page)

    widget._back_ten_pages()
    widget._forward_ten_pages()

    assert refreshes == [0, 8]
