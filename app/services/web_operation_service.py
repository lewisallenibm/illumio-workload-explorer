"""Small in-process operation runner for the single-instance web pilot.

Long imports must not occupy a browser request.  This runner is deliberately
limited to the local/single-instance pilot; a horizontally scaled production
deployment will replace it with a durable worker queue.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Callable
from uuid import uuid4


@dataclass
class WebOperation:
    id: str
    label: str
    status: str = "QUEUED"
    progress_current: int = 0
    progress_total: int = 0
    message: str = "Queued"
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class WebOperationService:
    def __init__(self):
        self._operations: dict[str, WebOperation] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="web-operation")

    def start(self, label: str, operation: Callable[[Callable[[int, int, str | None], None]], None]) -> WebOperation:
        item = WebOperation(id=uuid4().hex, label=label)
        with self._lock:
            self._operations[item.id] = item

        def progress(current: int, total: int, message: str | None = None):
            with self._lock:
                item.progress_current = current
                item.progress_total = total
                if message:
                    item.message = message

        def run():
            with self._lock:
                item.status = "RUNNING"
                item.message = "Running"
                item.started_at = datetime.now(UTC).isoformat()
            try:
                operation(progress)
            except Exception as exc:
                with self._lock:
                    item.status = "FAILED"
                    item.error = str(exc)
                    item.message = "Failed"
                    item.completed_at = datetime.now(UTC).isoformat()
                return
            with self._lock:
                item.status = "SUCCESS"
                item.message = "Completed"
                item.completed_at = datetime.now(UTC).isoformat()

        self._executor.submit(run)
        return item

    def get(self, operation_id: str) -> dict | None:
        with self._lock:
            item = self._operations.get(operation_id)
            return asdict(item) if item else None
