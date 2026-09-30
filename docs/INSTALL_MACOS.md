# macOS Installation and Quick-Start Guide (Terminal)

This guide walks you through setting up and running **Illumio Workload Explorer** on **macOS** (both Apple Silicon M1/M2/M3/M4 and Intel Macs) using **Terminal**, starting from a downloaded GitHub ZIP file.

---

## Prerequisites

### 1. Python 3.11 (Recommended)
Illumio Workload Explorer is designed for and tested with **Python 3.11** (Python 3.12+ also supported).

1. Open Terminal (press `Cmd + Space`, type `Terminal`, and press **Enter**).
2. Check your installed Python version:
   ```bash
   python3 --version
   ```
3. If Python is not installed or version is older than 3.11:
   - **Option A (Direct Installer):** Download **[Python 3.11 for macOS (Universal 64-bit)](https://www.python.org/downloads/release/python-3119/)**.
   - **Option B (Homebrew):** If you use Homebrew:
     ```bash
     brew install python@3.11
     ```

### 2. Local PostgreSQL Server
The application stores its workload snapshots and reconciliation records in local PostgreSQL.
1. Check if PostgreSQL is running or install via Homebrew / Postgres.app:
   ```bash
   # Via Homebrew:
   brew install postgresql@16
   brew services start postgresql@16
   ```
2. Create the application database:
   ```bash
   createdb illumio_workloads
   ```

---

## Step 1: Download & Extract the Project

1. On GitHub, click the green **Code** button and select **Download ZIP**.
2. Locate the `.zip` file in your `~/Downloads` folder.
3. Double-click the `.zip` to extract it.

---

## Step 2: Open Terminal in the Project Root

1. In Terminal, navigate into the extracted project folder:
   ```bash
   cd ~/Downloads/illumio-workload-explorer-*
   ```
2. Verify you are in the project root:
   ```bash
   ls -la
   ```
   *You should see `app/`, `tests/`, `requirements.txt`, and `alembic.ini`.*

---

## Step 3: Create & Activate Python Virtual Environment

1. Create a Python 3.11 virtual environment:
   ```bash
   python3 -m venv .venv
   ```
2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
   *Once activated, `(.venv)` will appear in your shell prompt.*

---

## Step 4: Install Dependencies

1. Upgrade `pip`:
   ```bash
   python -m pip install --upgrade pip
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt -r requirements-web.txt
   ```

---

## Step 5: Configure Environment (`.env`)

1. Create your local `.env` configuration file:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` in your text editor (e.g. `nano .env` or `open -e .env`) and set your PostgreSQL parameters:
   ```env
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=illumio_workloads
   DB_USER=your_mac_username
   DB_PASSWORD=
   ```

### Safety & Default Settings:
- `ILLUMIO_USE_REAL_CLIENT=false` (Mock / Demo mode by default; safe for exploration)
- `ILLUMIO_ALLOW_PCE_WRITEBACK=false` (Guards live PCE data from unintended modification)
- `WEB_DEPLOYMENT_MODE=local` (Safely binds local server to `127.0.0.1:8000`)

---

## Step 6: Initialize Database Schema

Run the database schema setup and migrations:
```bash
python -m database.create_schema
python -m app.scripts.create_illumio_tables
python -m alembic upgrade head
```

Run the readiness health check:
```bash
python -m app.scripts.health_check
```

---

## Step 7: Launch the Application

### Option A: Web Pilot (FastAPI / Browser UI)
```bash
python -m app.web.main
```
Open your browser to: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### Option B: Desktop GUI (PySide6 / Qt UI)
```bash
python -m app.main
```

---

## Demo Walkthrough (No Real PCE Required)

1. Open the UI (Web or Desktop).
2. **Workloads Tab**: Click **"Sync"** (Web) or **"Load Mock Workloads"** (Desktop).
3. **CMDB Tab**: Click **"Load Mock CMDB"**.
4. **Reconciliation Tab**: Click **"Run Reconciliation"**.
5. Explore discrepancies, label differences, and filter results.

---

## Apple Silicon Notes
- **PySide6** and **psycopg2-binary** provide native ARM64 wheels on macOS. No Rosetta or emulation is required.

---

## Stopping the App & Deactivating

- To stop the server or app: Press `Ctrl + C` in Terminal.
- To exit the virtual environment:
  ```bash
  deactivate
  ```
