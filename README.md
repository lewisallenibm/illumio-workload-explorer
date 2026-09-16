# Illumio Workload Explorer

Desktop PostgreSQL application for locally reviewing Illumio workloads, CMDB snapshots, and immutable reconciliation runs.

## Local web pilot (in progress)

The repository now also contains a browser-based pilot that reads the **same
PostgreSQL-backed data model** as the desktop app. It defaults to localhost
only. A public team pilot must use the documented Cloudflare Access JWT
validation and protected deployment configuration.

```bash
source .venv/bin/activate
python -m alembic upgrade head
python -m app.web.main
```

Open `http://127.0.0.1:8000`. The Web Pilot includes an Automations area with
two disabled-by-default tasks: workload export and compatibility report.
Manual test runs generate files only in `var/automation-outbox`; they do not
email or upload data to Box. Ten recipient slots and individual delivery
cadence settings are persisted in PostgreSQL for future approved delivery.

The security boundary and required work before hosting real data are documented
in [docs/web-security-foundation.md](docs/web-security-foundation.md). The
Railway/Cloudflare pilot and AWS App Runner reference deployment paths are in
[docs/public-pilot-deployment.md](docs/public-pilot-deployment.md).

## Everyday use

```bash
source .venv/bin/activate
ILLUMIO_PERF_TIMING=true python -m app.main
```

The default configuration uses mock data. Real PCE access and PCE write-back are separate, default-off permissions in `.env`:

```env
ILLUMIO_USE_REAL_CLIENT=false
ILLUMIO_ALLOW_PCE_WRITEBACK=false
```

Set only `ILLUMIO_USE_REAL_CLIENT=true` to allow read-only PCE connectivity checks and read-only syncs. Both values must be `true`, followed by a restart and in-app confirmation, before an approved label can be written to PCE.

On a new installation, the app checks its local PostgreSQL schema, performance
indexes, and Qt runtime before opening its tabs. If it cannot start, run the
Local Health Check, then create the schema and apply upgrades if needed.

## Local health check

This makes no PCE request and does not modify the database:

```bash
python -m app.scripts.health_check
```

## Read-only performance smoke check

This measures the database paging/filtering paths behind the three active
browser tabs. It reads local PostgreSQL data only and makes no PCE request.

```bash
python -m app.scripts.performance_smoke --page-size 500
```

For a controlled future release check, an optional threshold can fail the
command when a measured operation exceeds it:

```bash
python -m app.scripts.performance_smoke --page-size 1000 --max-seconds 1.0
```

## Tests

```bash
python -m pytest -q
```

## Pilot desktop package

The pilot package is built separately on macOS and Windows. Do not
cross-build from a different operating system; its display components and
private PostgreSQL runtime must be native to the recipient's platform.

The packaged app starts an app-owned PostgreSQL server only for that app and
only on `127.0.0.1`. Testers do not install PostgreSQL, create a database, or
need administrator access. Its database is stored in their private local
application-data folder and remains on their machine until they choose to
remove it. The Welcome tab includes the exact removal command.

To create a pilot package, provide a complete native PostgreSQL runtime
directory (with `bin/initdb`, `bin/pg_ctl`, `bin/createdb`, and `bin/psql`) to
the builder. The runtime is deliberately supplied outside source control.

```bash
python -m pip install -r requirements-build.txt
export ILLUMIO_POSTGRES_RUNTIME_DIR="/path/to/native/postgresql-runtime"
python -m app.scripts.build_desktop_app
```

The build checks for the native executable and Qt display plugin before it
reports success. You can repeat that check after copying a package elsewhere:

```bash
python -m app.scripts.verify_desktop_package
```

The platform-by-platform test steps are kept in
`docs/native-build-checklist.md` for the future Windows and Linux machines.

The result stays local in the ignored `dist/` folder. It contains no PCE
credentials, bundled source `.env`, or existing developer database; every
tester gets a new private local database on first launch. PCE writes remain
guarded and disabled unless separately configured and confirmed. Signing,
notarization, installers, and release publishing remain deliberate later
release steps. The package builder includes only the Qt modules used by the
application, rather than optional Qt development tools.

The current package version is maintained in `app/release_info.py`, so the
application and package build output always use the same version number.

## Database upgrades (later release step)

For a new local installation, create the schema first, then apply the tracked,
non-destructive database upgrades. Current upgrades only add performance
indexes; they never reset, import, or contact PCE.

```bash
python database/create_schema.py
python -m alembic upgrade head
```

## Before resetting local mock data

Run the health check and create a local backup first. A reset permanently removes local snapshots and reconciliation history; it never changes PCE data.

```bash
python -m app.scripts.backup_database
python -m app.scripts.reset_local_data --yes
```

Keep real PCE validation and representative exports as the final validation gate.
