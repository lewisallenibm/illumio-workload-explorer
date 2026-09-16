"""Create a local, portable PostgreSQL backup without uploading data."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from app.database import engine


def backup_command(target: Path, url=None):
    """Build pg_dump arguments without exposing a database password in argv."""
    url = url or engine.url
    if not url.drivername.startswith("postgresql"):
        raise ValueError("Local backups require a PostgreSQL DATABASE_URL")
    return [
        "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
        "--host", url.host or "localhost", "--port", str(url.port or 5432),
        "--username", url.username or "", "--file", str(target), url.database or "",
    ]


def create_backup(directory="backups"):
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"illumio-workloads-{datetime.now():%Y%m%d-%H%M%S}.dump"
    environment = os.environ.copy()
    if engine.url.password:
        environment["PGPASSWORD"] = engine.url.password
    subprocess.run(backup_command(target), check=True, env=environment)
    return target.resolve()


def main():
    target = create_backup()
    print(f"Local backup created: {target}")
    print("Keep this file private. Restores should be performed manually into a confirmed target database.")


if __name__ == "__main__":
    main()
