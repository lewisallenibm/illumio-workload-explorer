# Illumio Workload Explorer

PostgreSQL-backed application for reviewing Illumio workloads, CMDB inventory snapshots, and running immutable reconciliation diffs.

Available as both a **FastAPI Browser Application (Web Pilot)** and a **PySide6 Desktop Application (Qt GUI)**.

---

## Installation & Setup Guides

For detailed, step-by-step setup guides starting from a downloaded GitHub ZIP file:

- 🪟 **[Windows 10/11 PowerShell Guide](docs/INSTALL_WINDOWS.md)**
- 🍎 **[macOS Terminal Guide](docs/INSTALL_MACOS.md)**

---

## Quick Starts

### 🪟 Windows (PowerShell)
```powershell
# 1. Create and activate venv
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies & configure env
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-web.txt
Copy-Item .env.example .env

# 3. Setup database schema & migrations
python -m database.create_schema
python -m app.scripts.create_illumio_tables
python -m alembic upgrade head

# 4. Run the Web Pilot (or python -m app.main for Desktop GUI)
python -m app.web.main
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

### 🍎 macOS (Terminal)
```bash
# 1. Create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies & configure env
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-web.txt
cp .env.example .env

# 3. Setup database schema & migrations
python -m database.create_schema
python -m app.scripts.create_illumio_tables
python -m alembic upgrade head

# 4. Run the Web Pilot (or python -m app.main for Desktop GUI)
python -m app.web.main
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## Everyday Use & Modes

### 1. Mock / Demo Mode (Default)
By default, the application runs fully isolated with mock data generators. No PCE connection or credentials are required.
- `.env` settings:
  ```env
  ILLUMIO_USE_REAL_CLIENT=false
  ILLUMIO_ALLOW_PCE_WRITEBACK=false
  ```
- Workflow:
  1. Go to **Workloads** -> click **Sync** (or **Load Mock Workloads** in desktop GUI).
  2. Go to **CMDB** -> click **Load Mock CMDB**.
  3. Go to **Reconciliation** -> click **Run Reconciliation** to view matched and mismatched workloads.

### 2. Live PCE Read-Only Mode
To inspect live workloads from an Illumio Policy Compute Engine (PCE):
1. Configure credentials in `.env`:
   ```env
   ILLUMIO_USE_REAL_CLIENT=true
   ILLUMIO_ALLOW_PCE_WRITEBACK=false
   ILLUMIO_PCE_HOST=your-pce.example.com
   ILLUMIO_PCE_PORT=8443
   ILLUMIO_ORG_ID=1
   ILLUMIO_API_KEY_ID=api_xxxxxxxxxxxxxxxx
   ILLUMIO_API_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
2. Run health preflight:
   ```bash
   python -m app.scripts.health_check
   ```

### 3. PCE Write-Back Protection
PCE write-back is strictly guarded by dual safeguards:
1. Environment variable `ILLUMIO_ALLOW_PCE_WRITEBACK=true` must be set.
2. In-app confirmation checkbox must be checked by the operator prior to applying changes.

---

## Testing & Quality Validation

Run the full test suite locally:
```bash
pytest -v tests/
```

Run SAST and dependency audits:
```bash
bandit -r app/ -ll -ii --exclude app/ui/
pip-audit -r requirements-web.txt
```

---

## Troubleshooting & FAQ

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| `running scripts is disabled` on Windows | PowerShell execution policy | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` |
| `ModuleNotFoundError: No module named 'app'` | `PYTHONPATH` not set | Ensure virtualenv is active and run commands from the project root |
| `database tables are missing` | Database not initialized | Run `python -m database.create_schema` and `python -m alembic upgrade head` |
| `Cannot connect to server on port 5432` | PostgreSQL service not running | Start PostgreSQL service (Windows: Services -> postgresql; macOS: `brew services start postgresql@16`) |

---

## Security Best Practices
- Never commit `.env` or files containing live credentials to version control.
- Keep `ILLUMIO_ALLOW_PCE_WRITEBACK=false` for all read-only and exploratory testing.
- The local web pilot is bound strictly to `127.0.0.1:8000` to prevent unauthorized external access.
