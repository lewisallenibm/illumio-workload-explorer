"""Private PostgreSQL workspace support for the packaged pilot application.

The development app continues to use the developer's existing DATABASE_URL.
Pilot launchers opt in with ILLUMIO_MANAGED_WORKSPACE=true, which starts an
app-owned PostgreSQL instance in the current user's private application-data
directory.  No system service, shared database, or PCE credential is used.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


APP_DIRECTORY_NAME = "Illumio Workload Explorer"
DATABASE_NAME = "illumio_workloads"
DATABASE_USER = "illumio_local"
PORT_RANGE = range(55432, 55443)
_active_workspace: "ManagedWorkspace | None" = None


class ManagedWorkspaceError(RuntimeError):
    """The packaged pilot could not prepare its private local database."""


@dataclass(frozen=True)
class ManagedWorkspace:
    root: Path
    runtime_bin: Path
    data_directory: Path
    log_path: Path
    state_path: Path

    @classmethod
    def for_current_user(cls, runtime_bin: Path | None = None) -> "ManagedWorkspace":
        if platform.system() == "Darwin":
            root = Path.home() / "Library" / "Application Support" / APP_DIRECTORY_NAME
        elif platform.system() == "Windows":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_DIRECTORY_NAME
        else:
            root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_DIRECTORY_NAME

        return cls(
            root=root,
            runtime_bin=runtime_bin or packaged_postgres_bin(),
            data_directory=root / "postgres-data",
            log_path=root / "postgres.log",
            state_path=root / "workspace.json",
        )

    def database_url(self, port: int) -> str:
        return (
            f"postgresql+psycopg2://{DATABASE_USER}@127.0.0.1:{port}/"
            f"{DATABASE_NAME}"
        )

    def prepare(self) -> str:
        """Start the app-owned database and return its PostgreSQL URL."""
        self._require_runtime()
        self.root.mkdir(parents=True, exist_ok=True)
        state = self._read_state()
        port = self._port_from_state(state) or self._find_available_port()

        if not self.data_directory.exists():
            self._run("initdb", "-D", str(self.data_directory), "-U", DATABASE_USER, "-A", "trust", "--no-locale", "-E", "UTF8")

        if self._is_running(port) and self._runtime_changed(state):
            self._restart_for_current_runtime(port)
        elif not self._is_running(port):
            self._run(
                "pg_ctl", "start", "-D", str(self.data_directory), "-l", str(self.log_path),
                "-o", f"-p {port} -h 127.0.0.1", "-w", "-t", "30",
            )

        if not self._database_exists(port):
            self._run("createdb", "-h", "127.0.0.1", "-p", str(port), "-U", DATABASE_USER, DATABASE_NAME)

        self.state_path.write_text(
            json.dumps({"port": port, "runtime_bin": self._runtime_identity()}, indent=2),
            encoding="utf-8",
        )
        return self.database_url(port)

    def _require_runtime(self) -> None:
        required = ("initdb", "pg_ctl", "createdb", "psql")
        missing = [name for name in required if not self._executable(name).is_file()]
        if missing:
            raise ManagedWorkspaceError(
                "The private local database component is missing from this app package. "
                "Reinstall the pilot package. Missing: " + ", ".join(missing)
            )

    def _executable(self, name: str) -> Path:
        suffix = ".exe" if platform.system() == "Windows" else ""
        return self.runtime_bin / f"{name}{suffix}"

    def _run(self, command: str, *args: str) -> str:
        try:
            result = subprocess.run(
                [str(self._executable(command)), *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "unknown database error").strip()
            raise ManagedWorkspaceError(f"Private PostgreSQL setup failed while running {command}: {detail}") from exc
        return result.stdout

    def _read_state(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {}
        except (FileNotFoundError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _port_from_state(state: dict) -> int | None:
        try:
            return int(state["port"])
        except (KeyError, TypeError, ValueError):
            return None

    def _read_port(self) -> int | None:
        return self._port_from_state(self._read_state())

    def _runtime_identity(self) -> str:
        return str(self.runtime_bin.resolve())

    def _runtime_changed(self, state: dict) -> bool:
        """Whether an old packaged executable started this local server.

        A pilot can be replaced in place or launched from another folder.  The
        database data remains valid, but PostgreSQL must be restarted from the
        current package so it uses this package's own shared files.
        """
        return state.get("runtime_bin") != self._runtime_identity()

    def _restart_for_current_runtime(self, port: int) -> None:
        pid_file = self.data_directory / "postmaster.pid"
        if not pid_file.is_file():
            raise ManagedWorkspaceError(
                f"Port {port} is already in use and is not a verifiable app-owned PostgreSQL server. "
                "Close the conflicting local service, then reopen the app."
            )
        self._run("pg_ctl", "stop", "-D", str(self.data_directory), "-m", "fast", "-w", "-t", "30")
        self._run(
            "pg_ctl", "start", "-D", str(self.data_directory), "-l", str(self.log_path),
            "-o", f"-p {port} -h 127.0.0.1", "-w", "-t", "30",
        )

    def _find_available_port(self) -> int:
        for port in PORT_RANGE:
            if not self._port_in_use(port):
                return port
        raise ManagedWorkspaceError("No private local PostgreSQL port is available for the pilot app.")

    @staticmethod
    def _port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            return probe.connect_ex(("127.0.0.1", port)) == 0

    def _is_running(self, port: int) -> bool:
        return self._port_in_use(port)

    def _database_exists(self, port: int) -> bool:
        result = self._run(
            "psql", "-h", "127.0.0.1", "-p", str(port), "-U", DATABASE_USER,
            "-d", "postgres", "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{DATABASE_NAME}'",
        )
        return result.strip() == "1"

    def stop(self) -> None:
        """Stop the private server so its app-owned folder can be removed safely."""
        if self.data_directory.is_dir() and (self.data_directory / "postmaster.pid").exists():
            self._run("pg_ctl", "stop", "-D", str(self.data_directory), "-m", "fast", "-w", "-t", "30")


def packaged_postgres_bin() -> Path:
    """Location where the native Mac/Windows package will carry PostgreSQL."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS"))
    else:
        base = Path(__file__).resolve().parents[1]
    return base / "runtime" / "postgresql" / "bin"


def managed_workspace_enabled() -> bool:
    """Whether this launch should use the app-owned PostgreSQL workspace.

    A frozen desktop package is a pilot build and therefore starts its private
    data workspace automatically. Source/development launches stay connected
    to their configured database unless the flag is explicitly enabled.
    Setting the flag to ``false`` is retained as an escape hatch for package
    diagnostics; it is not exposed as ordinary application functionality.
    """
    configured = os.getenv("ILLUMIO_MANAGED_WORKSPACE")
    if configured is not None:
        return configured.lower() == "true"
    return bool(getattr(sys, "frozen", False))


def prepare_managed_workspace_from_environment() -> str | None:
    """Set DATABASE_URL before app.config/app.database are imported in a pilot build."""
    if not managed_workspace_enabled():
        return None
    global _active_workspace
    _active_workspace = ManagedWorkspace.for_current_user()
    database_url = _active_workspace.prepare()
    os.environ["DATABASE_URL"] = database_url
    return database_url


def stop_managed_workspace() -> None:
    """Best-effort shutdown used when a packaged pilot app exits."""
    if _active_workspace is None:
        return
    try:
        _active_workspace.stop()
    except ManagedWorkspaceError:
        # Closing the GUI remains more important than surfacing a shutdown
        # failure. The app-owned workspace can be stopped on the next launch.
        pass


def removal_guidance() -> str:
    """Return the platform-specific, package-owned workspace removal command."""
    if platform.system() == "Windows":
        return (
            "Quit the app first. In PowerShell, run:\n"
            'Remove-Item -LiteralPath "$env:LOCALAPPDATA\\Illumio Workload Explorer" '
            "-Recurse -Force"
        )
    return (
        "Quit the app first. In Terminal, run:\n"
        'rm -rf "$HOME/Library/Application Support/Illumio Workload Explorer"'
    )
