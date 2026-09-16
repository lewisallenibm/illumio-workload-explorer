import pytest

from app.scripts.build_desktop_app import (
    APP_NAME, PROJECT_ROOT, artifact_message, build_command,
    repair_macos_postgres_sharedir, resolve_postgres_runtime_dir,
)


@pytest.mark.parametrize(
    ("platform_name", "expected_option"),
    [("Darwin", "--osx-bundle-identifier"), ("Windows", "--windowed"), ("Linux", "--windowed")],
)
def test_native_build_command_targets_the_desktop_entrypoint(platform_name, expected_option):
    command = build_command(platform_name)

    assert "PyInstaller" in command
    assert expected_option in command
    assert "--collect-all" not in command
    assert "PySide6" not in command
    assert str(PROJECT_ROOT / "app" / "main.py") == command[-1]


@pytest.mark.parametrize("platform_name", ["Darwin", "Windows", "Linux"])
def test_native_build_message_names_the_expected_artifact(platform_name):
    message = artifact_message(platform_name)

    assert "dist/" in message
    assert APP_NAME in message


def test_build_command_rejects_unknown_platform():
    with pytest.raises(ValueError, match="Unsupported build platform"):
        build_command("Plan9")


def test_build_command_includes_the_managed_postgres_runtime(tmp_path):
    command = build_command("Darwin", tmp_path / "postgresql")

    assert "--add-data" in command
    assert any("runtime/postgresql" in value for value in command)


def test_runtime_resolution_requires_an_explicit_complete_runtime(monkeypatch, tmp_path):
    monkeypatch.delenv("ILLUMIO_POSTGRES_RUNTIME_DIR", raising=False)
    with pytest.raises(RuntimeError, match="ILLUMIO_POSTGRES_RUNTIME_DIR"):
        resolve_postgres_runtime_dir("Darwin")

    runtime = tmp_path / "postgresql"
    (runtime / "bin").mkdir(parents=True)
    monkeypatch.setenv("ILLUMIO_POSTGRES_RUNTIME_DIR", str(runtime))
    with pytest.raises(RuntimeError, match="incomplete"):
        resolve_postgres_runtime_dir("Darwin")


def test_windows_build_on_windows_explicitly_includes_the_native_qt_plugin(monkeypatch, tmp_path):
    plugin = tmp_path / "PySide6" / "Qt" / "plugins" / "platforms" / "qwindows.dll"
    plugin.parent.mkdir(parents=True)
    plugin.touch()
    monkeypatch.setattr("app.scripts.build_desktop_app.platform.system", lambda: "Windows")
    monkeypatch.setattr("app.scripts.build_desktop_app.PySide6.__file__", str(tmp_path / "PySide6" / "__init__.py"))

    command = build_command("Windows")

    assert "--add-binary" in command
    assert any("qwindows.dll" in value for value in command)


def test_macos_runtime_repair_makes_postgres_share_a_real_framework_directory(tmp_path):
    contents = tmp_path / f"{APP_NAME}.app" / "Contents"
    resource_share = contents / "Resources" / "runtime" / "postgresql" / "share"
    timezone_default = resource_share / "postgresql" / "timezonesets" / "Default"
    timezone_default.parent.mkdir(parents=True)
    timezone_default.write_text("Default", encoding="utf-8")

    framework_runtime = contents / "Frameworks" / "runtime" / "postgresql"
    framework_runtime.mkdir(parents=True)
    framework_share = framework_runtime / "share"
    framework_share.symlink_to("../../../Resources/runtime/postgresql/share")

    repair_macos_postgres_sharedir(tmp_path)

    assert framework_share.is_dir()
    assert not framework_share.is_symlink()
    assert (framework_share / "postgresql" / "timezonesets" / "Default").read_text() == "Default"
