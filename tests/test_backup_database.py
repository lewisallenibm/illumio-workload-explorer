from pathlib import Path
from types import SimpleNamespace

from app.scripts.backup_database import backup_command


def test_backup_command_uses_portable_pg_dump_without_password_in_arguments():
    command = backup_command(
        Path("backups/test.dump"),
        SimpleNamespace(
            drivername="postgresql+psycopg2", host="localhost", port=5432,
            username="operator", database="illumio_workloads",
        ),
    )
    assert command[:4] == ["pg_dump", "--format=custom", "--no-owner", "--no-privileges"]
    assert "backups/test.dump" in command
    assert not any("password" in value.casefold() for value in command)
