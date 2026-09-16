"""Build a native desktop package on the operating system currently in use.

PyInstaller packages must be created on the target operating system.  This
helper deliberately does not try to cross-build a Windows or Linux release
from macOS (or the reverse), which would produce an unreliable artifact.
"""

import platform
import shutil
import subprocess
import sys
import os
from pathlib import Path

import PySide6

from app.release_info import APP_NAME, APP_VERSION
from app.scripts.verify_desktop_package import missing_package_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_PLATFORMS = {"Darwin", "Windows", "Linux"}


def repair_macos_postgres_sharedir(dist_directory: Path | None = None) -> None:
    """Keep PostgreSQL's compiled shared-data path inside ``Frameworks``.

    On macOS, PyInstaller places regular data in ``Contents/Resources`` and
    creates a relative link from ``Contents/Frameworks``.  PostgreSQL resolves
    its compiled shared-data directory from its executable path, and macOS
    App Translocation can reject that cross-directory link for an unsigned app.
    Put a real copy of the small PostgreSQL shared-data directory beside the
    executable so the packaged database works both before and after Gatekeeper
    translocates a pilot app.
    """
    dist_directory = dist_directory or PROJECT_ROOT / "dist"
    contents = dist_directory / f"{APP_NAME}.app" / "Contents"
    framework_share = contents / "Frameworks" / "runtime" / "postgresql" / "share"
    resource_share = contents / "Resources" / "runtime" / "postgresql" / "share"
    required = resource_share / "postgresql" / "timezonesets" / "Default"

    if not required.is_file():
        raise RuntimeError(
            "The macOS PostgreSQL runtime is missing required time-zone data: "
            f"{required}"
        )
    if framework_share.exists() and not framework_share.is_symlink():
        return
    if framework_share.is_symlink():
        framework_share.unlink()
    elif framework_share.exists():
        shutil.rmtree(framework_share)

    shutil.copytree(resource_share, framework_share, symlinks=False)
    if not (framework_share / "postgresql" / "timezonesets" / "Default").is_file():
        raise RuntimeError("Could not place PostgreSQL time-zone data beside the macOS executable.")


def resolve_postgres_runtime_dir(platform_name: str | None = None) -> Path:
    """Locate the native PostgreSQL runtime that will ship with a pilot build."""
    platform_name = platform_name or platform.system()
    configured = os.getenv("ILLUMIO_POSTGRES_RUNTIME_DIR")
    if not configured:
        raise RuntimeError(
            "Set ILLUMIO_POSTGRES_RUNTIME_DIR to a native PostgreSQL runtime "
            "before creating a pilot package."
        )

    runtime = Path(configured).expanduser().resolve()
    executable_suffix = ".exe" if platform_name == "Windows" else ""
    required = ("initdb", "pg_ctl", "createdb", "psql")
    missing = [name for name in required if not (runtime / "bin" / f"{name}{executable_suffix}").is_file()]
    if missing:
        raise RuntimeError(
            f"PostgreSQL runtime {runtime} is incomplete for {platform_name}. "
            "Missing: " + ", ".join(missing)
        )
    return runtime


def build_command(
    platform_name: str | None = None,
    postgres_runtime_dir: Path | None = None,
) -> list[str]:
    """Return the native PyInstaller command for a supported desktop OS."""
    platform_name = platform_name or platform.system()
    if platform_name not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported build platform: {platform_name}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--paths",
        str(PROJECT_ROOT),
    ]
    if platform_name == "Darwin":
        command.extend([
            "--osx-bundle-identifier",
            "com.lewisallen.illumio-workload-explorer",
        ])
    if postgres_runtime_dir is not None:
        command.extend(["--add-data", f"{postgres_runtime_dir}{os.pathsep}runtime/postgresql"])
    # PyInstaller's PySide hook did not consistently retain qwindows.dll on
    # the Windows runner. Include the native platform plugin explicitly so a
    # pilot opens with the same Qt display layer it was built and verified on.
    if platform_name == "Windows" and platform.system() == "Windows":
        package_root = Path(PySide6.__file__).resolve().parent
        qwindows = next(package_root.rglob("qwindows.dll"), None)
        if qwindows is None:
            raise RuntimeError(f"Required Windows Qt platform plugin is missing under: {package_root}")
        command.extend(["--add-binary", f"{qwindows}{os.pathsep}PySide6/Qt/plugins/platforms"])
    command.append(str(PROJECT_ROOT / "app" / "main.py"))
    return command


def artifact_message(platform_name: str | None = None) -> str:
    platform_name = platform_name or platform.system()
    if platform_name == "Darwin":
        return f"Native app bundle created in dist/{APP_NAME}.app (version {APP_VERSION})"
    if platform_name == "Windows":
        return f"Native Windows app created in dist/{APP_NAME}/ (version {APP_VERSION})"
    if platform_name == "Linux":
        return f"Native Linux app created in dist/{APP_NAME}/ (version {APP_VERSION})"
    return "Native app created in dist/"


def main() -> None:
    platform_name = platform.system()
    try:
        postgres_runtime = resolve_postgres_runtime_dir(platform_name)
        command = build_command(platform_name, postgres_runtime)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc

    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except FileNotFoundError as exc:
        raise SystemExit(
            "PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt"
        ) from exc
    if platform_name == "Darwin":
        try:
            repair_macos_postgres_sharedir(PROJECT_ROOT / "dist")
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    missing = missing_package_paths(platform_name, PROJECT_ROOT / "dist")
    if missing:
        raise SystemExit("Package build completed but verification failed: " + ", ".join(map(str, missing)))
    print(artifact_message(platform_name))


if __name__ == "__main__":
    main()
