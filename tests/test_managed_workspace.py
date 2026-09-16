import json

import pytest

import app.managed_workspace as workspace_module
from app.managed_workspace import (
    DATABASE_NAME,
    DATABASE_USER,
    ManagedWorkspace,
    ManagedWorkspaceError,
    managed_workspace_enabled,
    prepare_managed_workspace_from_environment,
    removal_guidance,
    stop_managed_workspace,
)


def _workspace(tmp_path):
    return ManagedWorkspace(
        root=tmp_path / "workspace",
        runtime_bin=tmp_path / "runtime" / "bin",
        data_directory=tmp_path / "workspace" / "postgres-data",
        log_path=tmp_path / "workspace" / "postgres.log",
        state_path=tmp_path / "workspace" / "workspace.json",
    )


def test_managed_workspace_url_is_private_local_postgres(tmp_path):
    workspace = _workspace(tmp_path)

    assert workspace.database_url(55432) == (
        f"postgresql+psycopg2://{DATABASE_USER}@127.0.0.1:55432/{DATABASE_NAME}"
    )


def test_managed_workspace_reads_its_persisted_port(tmp_path):
    workspace = _workspace(tmp_path)
    workspace.root.mkdir(parents=True)
    workspace.state_path.write_text(json.dumps({"port": 55437}), encoding="utf-8")

    assert workspace._read_port() == 55437


def test_managed_workspace_restarts_an_old_package_runtime_without_losing_data(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    workspace.root.mkdir(parents=True)
    workspace.data_directory.mkdir()
    (workspace.data_directory / "postmaster.pid").write_text("12345", encoding="utf-8")
    workspace.state_path.write_text(json.dumps({"port": 55432}), encoding="utf-8")
    workspace.runtime_bin.mkdir(parents=True)
    for executable in ("initdb", "pg_ctl", "createdb", "psql"):
        (workspace.runtime_bin / executable).touch()

    commands = []
    monkeypatch.setattr(ManagedWorkspace, "_is_running", lambda self, port: True)
    monkeypatch.setattr(ManagedWorkspace, "_database_exists", lambda self, port: True)
    monkeypatch.setattr(ManagedWorkspace, "_run", lambda self, command, *args: commands.append((command, args)) or "")

    workspace.prepare()

    assert [command for command, _ in commands] == ["pg_ctl", "pg_ctl"]
    assert commands[0][1][0] == "stop"
    assert commands[1][1][0] == "start"
    saved_state = json.loads(workspace.state_path.read_text(encoding="utf-8"))
    assert saved_state["runtime_bin"] == str(workspace.runtime_bin.resolve())


def test_managed_workspace_keeps_current_runtime_running(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    workspace.root.mkdir(parents=True)
    workspace.data_directory.mkdir()
    workspace.runtime_bin.mkdir(parents=True)
    for executable in ("initdb", "pg_ctl", "createdb", "psql"):
        (workspace.runtime_bin / executable).touch()
    workspace.state_path.write_text(
        json.dumps({"port": 55432, "runtime_bin": str(workspace.runtime_bin.resolve())}),
        encoding="utf-8",
    )

    monkeypatch.setattr(ManagedWorkspace, "_is_running", lambda self, port: True)
    monkeypatch.setattr(ManagedWorkspace, "_database_exists", lambda self, port: True)
    monkeypatch.setattr(ManagedWorkspace, "_run", lambda *args: pytest.fail("current runtime should not restart"))

    workspace.prepare()


def test_managed_workspace_requires_bundled_runtime(tmp_path):
    workspace = _workspace(tmp_path)

    with pytest.raises(ManagedWorkspaceError, match="private local database component is missing"):
        workspace.prepare()


def test_managed_workspace_opt_in_sets_database_url(monkeypatch):
    monkeypatch.setenv("ILLUMIO_MANAGED_WORKSPACE", "true")

    class FakeWorkspace:
        def prepare(self):
            return "postgresql+psycopg2://illumio_local@127.0.0.1:55432/illumio_workloads"

    monkeypatch.setattr(
        workspace_module.ManagedWorkspace,
        "for_current_user",
        classmethod(lambda cls: FakeWorkspace()),
    )

    assert prepare_managed_workspace_from_environment().endswith("/illumio_workloads")
    assert workspace_module.os.environ["DATABASE_URL"].endswith("/illumio_workloads")


def test_managed_workspace_is_off_for_development_launch(monkeypatch):
    monkeypatch.delenv("ILLUMIO_MANAGED_WORKSPACE", raising=False)
    monkeypatch.setattr(workspace_module.sys, "frozen", False, raising=False)

    assert prepare_managed_workspace_from_environment() is None


def test_frozen_pilot_package_automatically_uses_its_private_workspace(monkeypatch):
    monkeypatch.delenv("ILLUMIO_MANAGED_WORKSPACE", raising=False)
    monkeypatch.setattr(workspace_module.sys, "frozen", True, raising=False)

    assert managed_workspace_enabled() is True


def test_explicit_false_disables_managed_workspace_for_package_diagnostics(monkeypatch):
    monkeypatch.setenv("ILLUMIO_MANAGED_WORKSPACE", "false")
    monkeypatch.setattr(workspace_module.sys, "frozen", True, raising=False)

    assert managed_workspace_enabled() is False


def test_removal_guidance_targets_only_the_app_owned_workspace(monkeypatch):
    monkeypatch.setattr(workspace_module.platform, "system", lambda: "Darwin")

    assert "Illumio Workload Explorer" in removal_guidance()
    assert "Quit the app first" in removal_guidance()


def test_managed_workspace_stop_is_safe_when_no_pilot_workspace_started(monkeypatch):
    monkeypatch.setattr(workspace_module, "_active_workspace", None)

    assert stop_managed_workspace() is None
