import logging
import os
import sys
from pathlib import Path

import app.main as main_module
from app.main import (
    APP_NAME,
    RedactingFormatter,
    configure_logging,
    configure_qt_platform_plugin_path,
    install_exception_hook,
    unexpected_error_message,
)


def test_performance_logging_enables_the_dedicated_logger(monkeypatch, tmp_path):
    monkeypatch.setenv("ILLUMIO_PERF_TIMING", "true")
    logger = logging.getLogger("illumio.performance")
    previous = logger.level
    try:
        configure_logging(tmp_path)
        assert logger.level == logging.INFO
        assert (tmp_path / "illumio-workload-explorer.log").exists()
    finally:
        logger.setLevel(previous)


def test_qt_platform_plugin_path_uses_bundled_platform_directory(monkeypatch, tmp_path):
    plugin_root = tmp_path / "plugins"
    platform_directory = plugin_root / "platforms"
    platform_directory.mkdir(parents=True)
    monkeypatch.delenv("QT_QPA_PLATFORM_PLUGIN_PATH", raising=False)

    result = configure_qt_platform_plugin_path(plugin_root)

    assert result == platform_directory
    assert os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] == str(platform_directory)


def test_qt_platform_plugin_path_skips_missing_candidate(monkeypatch, tmp_path):
    monkeypatch.delenv("QT_QPA_PLATFORM_PLUGIN_PATH", raising=False)

    result = configure_qt_platform_plugin_path(tmp_path / "missing")

    assert result == tmp_path / "missing" / "platforms"
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" not in os.environ


def test_qt_platform_plugin_path_uses_macos_alias_when_cocoa_plugin_exists(monkeypatch, tmp_path):
    plugin_root = tmp_path / "plugins"
    platform_directory = plugin_root / "platforms"
    platform_directory.mkdir(parents=True)
    cocoa_plugin = platform_directory / "libqcocoa.dylib"
    cocoa_plugin.touch()
    temporary_directory = tmp_path / "temporary"

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.tempfile, "gettempdir", lambda: str(temporary_directory))
    monkeypatch.delenv("QT_QPA_PLATFORM_PLUGIN_PATH", raising=False)
    monkeypatch.delenv("QT_PLUGIN_PATH", raising=False)
    monkeypatch.delenv("QT_STYLE_OVERRIDE", raising=False)

    result = configure_qt_platform_plugin_path(plugin_root)

    assert result == temporary_directory / f"illumio-workload-explorer-qt-{main_module.PySide6.__version__}" / "platforms"
    assert Path(os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"]) == result
    assert os.environ["QT_PLUGIN_PATH"] == str(plugin_root)
    assert os.environ["QT_STYLE_OVERRIDE"] == "macOS"
    assert (result / "libqcocoa.dylib").is_symlink()
    assert (result / "libqcocoa.dylib").resolve() == cocoa_plugin


def test_log_formatter_redacts_credential_shaped_values():
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        "illumio", logging.ERROR, __file__, 1,
        "password=not-for-logs api_key: also-not-for-logs https://operator:db-password@example.test",
        (), None,
    )

    formatted = formatter.format(record)

    assert "not-for-logs" not in formatted
    assert "also-not-for-logs" not in formatted
    assert "db-password" not in formatted
    assert "password=***" in formatted
    assert "api_key: ***" in formatted
    assert "operator:***@example.test" in formatted


def test_unexpected_error_message_is_plain_language_and_data_safe():
    message = unexpected_error_message()

    assert APP_NAME in message
    assert "local data was not changed" in message
    assert "private application log" in message


def test_install_exception_hook_registers_application_handler():
    original = sys.excepthook
    try:
        install_exception_hook()
        assert sys.excepthook.__name__ == "unexpected_exception_hook"
    finally:
        sys.excepthook = original
