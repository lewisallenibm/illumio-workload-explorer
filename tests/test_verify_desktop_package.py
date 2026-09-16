from pathlib import Path

import pytest

from app.release_info import APP_NAME
from app.scripts.verify_desktop_package import missing_package_paths, required_package_paths


@pytest.mark.parametrize("platform_name", ["Darwin", "Windows", "Linux"])
def test_native_package_verification_knows_executable_and_qt_plugin(platform_name, tmp_path):
    paths = required_package_paths(platform_name, tmp_path)

    expected_count = 2 if platform_name == "Linux" else (4 if platform_name == "Darwin" else 3)
    assert len(paths) == expected_count
    assert APP_NAME in str(paths[0])
    assert "platforms" in str(paths[1])
    if platform_name != "Linux":
        assert "runtime/postgresql" in str(paths[2])

    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    assert missing_package_paths(platform_name, tmp_path) == ()


def test_native_package_verification_reports_missing_files(tmp_path):
    missing = missing_package_paths("Windows", tmp_path)

    assert len(missing) == 3
    assert missing[0].name == f"{APP_NAME}.exe"


def test_native_package_verification_rejects_unknown_platform(tmp_path):
    with pytest.raises(ValueError, match="Unsupported package platform"):
        required_package_paths("Plan9", tmp_path)
