# Windows Installation and Quick-Start Guide (PowerShell)

This guide walks you through setting up and running **Illumio Workload Explorer** on **Windows 10 or Windows 11** using **PowerShell**, starting from a downloaded GitHub ZIP file.

---

## Prerequisites

### 1. Python 3.11 (Recommended)
Illumio Workload Explorer is designed for and tested with **Python 3.11** (Python 3.12+ also supported).

1. Open PowerShell and check if Python is installed:
   ```powershell
   python --version
   ```
   *or using the Python Launcher:*
   ```powershell
   py --version
   ```
2. If Python is not installed or version is older than 3.11:
   - Download the official installer: **[Python 3.11 for Windows (64-bit)](https://www.python.org/downloads/release/python-3119/)**.
   - **CRITICAL STEP DURING INSTALLATION:** On the first screen of the installer, check the box **"Add python.exe to PATH"** before clicking Install.

### 2. Local PostgreSQL Server
The application saves its data locally in PostgreSQL.
1. If you already have PostgreSQL installed, ensure the service is running.
2. If installing for the first time, download and run the **[PostgreSQL Windows Installer (v15 or v16)](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads)**.
3. Open `psql` or pgAdmin and create the application database:
   ```sql
   CREATE DATABASE illumio_workloads;
   ```

---

## Step 1: Download & Extract the Project

1. On GitHub, click the green **Code** button and select **Download ZIP**.
2. Locate the downloaded file in your `Downloads` folder (e.g., `illumio-workload-explorer-illumioexplorer_v1.zip`).
3. Right-click the `.zip` file and select **Extract All...**. Choose an extraction folder.
4. Open the extracted folder until you see the project root files (`README.md`, `requirements.txt`, `app`, `tests`, etc.).

---

## Step 2: Open PowerShell in the Project Root

1. In Windows File Explorer, click inside the address bar at the top of the project folder, type `powershell`, and press **Enter**.
2. Alternatively, open PowerShell and navigate using `cd`:
   ```powershell
   cd "$HOME\Downloads\illumio-workload-explorer-*"
   ```
3. Verify you are in the correct root directory:
   ```powershell
   Get-ChildItem
   ```
   *You should see `app`, `tests`, `requirements.txt`, and `alembic.ini`.*

---

## Step 3: Create & Activate Python Virtual Environment

1. Create a dedicated virtual environment named `.venv`:
   ```powershell
   py -3.11 -m venv .venv
   ```
   *(Or `python -m venv .venv` if using standard python alias)*

2. Activate the virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

> **Note on PowerShell Execution Policy:**
> If PowerShell displays an error stating *"running scripts is disabled on this system"*, enable script execution for your current session only (safe and non-invasive):
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
> .\.venv\Scripts\Activate.ps1
> ```
> *Once activated, `(.venv)` will appear at the start of your PowerShell prompt.*

---

## Step 4: Install Dependencies

1. Upgrade `pip`:
   ```powershell
   python -m pip install --upgrade pip
   ```
2. Install the application dependencies:
   ```powershell
   pip install -r requirements.txt -r requirements-web.txt
   ```

---

## Step 5: Configure Environment (`.env`)

1. Copy the example configuration template:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` in Notepad or VS Code:
   ```powershell
   notepad .env
   ```
3. Update your local PostgreSQL credentials:
   ```env
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=illumio_workloads
   DB_USER=postgres
   DB_PASSWORD=your_actual_postgres_password
   ```

### Safety & Default Settings:
- `ILLUMIO_USE_REAL_CLIENT=false` (Keep `false` for Demo / Mock mode; no PCE connection needed)
- `ILLUMIO_ALLOW_PCE_WRITEBACK=false` (Always keep `false` to prevent unwanted live PCE modifications)
- `WEB_DEPLOYMENT_MODE=local` (Keeps web pilot safely bound to `127.0.0.1`)

---

## Step 6: Initialize Database Schema

Run the database schema setup and migrations:
```powershell
python -m database.create_schema
python -m app.scripts.create_illumio_tables
python -m alembic upgrade head
```

Optional health check to verify database and runtime readiness:
```powershell
python -m app.scripts.health_check
```

---

## Step 7: Launch the Application

You can launch either the **Web Pilot (Browser UI)** or the **Desktop App (Qt GUI)**:

### Option A: Web Pilot (FastAPI Browser UI)
```powershell
python -m app.web.main
```
Open your browser to: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### Option B: Desktop GUI (PySide6 / Qt UI)
```powershell
python -m app.main
```

---

## Demo Walkthrough (No Real PCE Required)

1. Open the application (Web or Desktop).
2. **Workloads Tab**: Click **"Load Mock Workloads"** (or in Web: click **"Sync"** in mock mode). Workloads will populate with synthetic hosts and labels.
3. **CMDB Tab**: Click **"Load Mock CMDB"** (loads simulated CMDB inventory dataset).
4. **Reconciliation Tab**: Click **"Run Reconciliation"**.
5. Review matched records, mismatched labels, and orphaned systems in the table.

---

## Stopping the App & Deactivating

- To stop the server or app: Press `Ctrl + C` in PowerShell.
- To exit the virtual environment:
  ```powershell
  deactivate
  ```
