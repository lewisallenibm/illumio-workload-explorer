from threading import Event

from app.services.web_operation_service import WebOperationService


def test_web_operation_runs_outside_the_request_thread():
    service = WebOperationService()
    finished = Event()

    def work(progress):
        progress(25, 100, "Staging")
        finished.set()

    operation = service.start("Test operation", work)
    assert finished.wait(timeout=2)

    result = service.get(operation.id)
    assert result["status"] == "SUCCESS"
    assert result["progress_current"] == 25
    assert result["progress_total"] == 100
