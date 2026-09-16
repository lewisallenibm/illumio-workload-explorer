from app.scripts.build_macos_app import PROJECT_ROOT, build_command


def test_macos_build_command_targets_the_desktop_entrypoint():
    command = build_command()
    assert "PyInstaller" in command
    assert "--windowed" in command
    assert str(PROJECT_ROOT / "app" / "main.py") == command[-1]
