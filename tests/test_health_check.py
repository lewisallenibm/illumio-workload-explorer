import pytest

from app.scripts.health_check import collect_health, expected_qt_platform_plugin


def test_health_check_reports_local_schema_and_safe_pce_defaults():
    report = collect_health()
    assert report["missing_tables"] == []
    assert report["missing_indexes"] == []
    assert report["pce_writeback"] is False
    assert report["qt_platform_plugin_available"] is True


@pytest.mark.parametrize(
    ("platform_name", "plugin_name"),
    [
        ("Darwin", "libqcocoa.dylib"),
        ("Windows", "qwindows.dll"),
        ("Linux", "libqxcb.so"),
    ],
)
def test_health_check_knows_each_native_qt_platform_plugin(platform_name, plugin_name):
    assert expected_qt_platform_plugin(platform_name) == plugin_name
