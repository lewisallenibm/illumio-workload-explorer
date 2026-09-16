"""
AppEvents — a simple application-wide event bus.

Any widget can post a status message to the main window's status bar
without needing a direct reference to it.

Usage:
    from app.ui.app_events import app_events
    app_events.status_message.emit("Sync completed in 38.4s")
"""

from PySide6.QtCore import QObject, Signal


class _AppEvents(QObject):
    status_message = Signal(str)


app_events = _AppEvents()
