"""Backward-compatible shortcut for the native macOS package build."""

from app.scripts.build_desktop_app import PROJECT_ROOT, build_command as _build_command
from app.scripts.build_desktop_app import main as _build_desktop_app


def build_command():
    """Return the macOS-specific build command used by older documentation."""
    return _build_command("Darwin")


def main():
    _build_desktop_app()


if __name__ == "__main__":
    main()
