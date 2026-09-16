"""Verify that a native PyInstaller package contains its required Qt plugin."""

import argparse
import platform
from pathlib import Path

from app.release_info import APP_NAME


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_LAYOUT = {
    "Darwin": (
        (f"{APP_NAME}.app", "Contents", "MacOS", APP_NAME),
        (f"{APP_NAME}.app", "Contents", "Frameworks", "PySide6", "Qt", "plugins", "platforms", "libqcocoa.dylib"),
        (f"{APP_NAME}.app", "Contents", "Frameworks", "runtime", "postgresql", "bin", "initdb"),
        (f"{APP_NAME}.app", "Contents", "Frameworks", "runtime", "postgresql", "share", "postgresql", "timezonesets", "Default"),
    ),
    "Windows": (
        (APP_NAME, f"{APP_NAME}.exe"),
        (APP_NAME, "_internal", "PySide6", "Qt", "plugins", "platforms", "qwindows.dll"),
        (APP_NAME, "_internal", "runtime", "postgresql", "bin", "initdb.exe"),
    ),
    "Linux": (
        (APP_NAME, APP_NAME),
        (APP_NAME, "_internal", "PySide6", "Qt", "plugins", "platforms", "libqxcb.so"),
    ),
}


def required_package_paths(platform_name: str | None = None, dist_directory: Path | None = None):
    """Return the expected executable, Qt plugin, and database runtime paths."""
    platform_name = platform_name or platform.system()
    if platform_name not in _PACKAGE_LAYOUT:
        raise ValueError(f"Unsupported package platform: {platform_name}")
    dist_directory = dist_directory or PROJECT_ROOT / "dist"
    return tuple(dist_directory.joinpath(*parts) for parts in _PACKAGE_LAYOUT[platform_name])


def missing_package_paths(platform_name: str | None = None, dist_directory: Path | None = None):
    return tuple(path for path in required_package_paths(platform_name, dist_directory) if not path.is_file())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("Darwin", "Windows", "Linux"))
    parser.add_argument("--dist-directory", type=Path, default=PROJECT_ROOT / "dist")
    args = parser.parse_args(argv)

    platform_name = args.platform or platform.system()
    missing = missing_package_paths(platform_name, args.dist_directory)
    if missing:
        print("Package verification failed. Missing:")
        for path in missing:
            print(f"- {path}")
        raise SystemExit(1)
    print(f"{platform_name} package verification passed.")


if __name__ == "__main__":
    main()
