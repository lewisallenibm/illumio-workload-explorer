from app.release_info import APP_NAME, APP_VERSION
from app.scripts.build_desktop_app import artifact_message


def test_release_identity_is_shared_by_the_native_package_builder():
    assert APP_NAME in artifact_message("Linux")
    assert APP_VERSION in artifact_message("Linux")


def test_release_version_uses_simple_release_format():
    assert APP_VERSION.count(".") == 2
    assert all(part.isdigit() for part in APP_VERSION.split("."))
