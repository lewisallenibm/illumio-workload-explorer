# Native Build Checklist

Build each package on the operating system where it will run. Do not
cross-build a Windows or Linux release from macOS.

## Windows

1. Install PostgreSQL, Python 3.11, and the project dependencies.
2. Run `python -m pip install -r requirements-build.txt`.
3. Run `python -m app.scripts.build_desktop_app`.
4. Run `python -m app.scripts.verify_desktop_package`.
5. Start `dist/Illumio Workload Explorer/Illumio Workload Explorer.exe` and
   test Workloads, CMDB, Reconciliation, and Admin Health Check.

## Linux

1. Install PostgreSQL, Python 3.11, and the required native Qt/X11 libraries.
2. Run `python -m pip install -r requirements-build.txt`.
3. Run `python -m app.scripts.build_desktop_app`.
4. Run `python -m app.scripts.verify_desktop_package`.
5. Start `dist/Illumio Workload Explorer/Illumio Workload Explorer` and test
   Workloads, CMDB, Reconciliation, and Admin Health Check.

## Every platform

- Run `python -m app.scripts.health_check` before testing.
- Keep `.env`, backups, logs, exports, and uploaded data private.
- Do not enable real PCE modes for a packaging test.
