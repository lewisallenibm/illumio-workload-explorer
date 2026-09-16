# Web Pilot Security Foundation

## Current status

The browser pilot is intentionally **localhost-only** and has no login.
`LocalPilotOnlyMiddleware` rejects non-loopback requests, and the development
entry point binds Uvicorn to `127.0.0.1`. Do not deploy this version to Railway,
Box-hosted pages, or any public/internal network.

The browser views use the same PostgreSQL data model as the desktop app. They
are read-only in this initial web phase except for automation configuration and
safe local-outbox test runs.

## Delivery safety

The default automation channel is `LOCAL_OUTBOX`:

- generated workload exports and compatibility reports stay in
  `var/automation-outbox/`;
- recipient data is recorded in a manifest, but no email is sent;
- each run is retained in `automation_runs` with status and artifact path.

SMTP and Box code paths require both a selected channel and
`AUTOMATION_ENABLE_EXTERNAL_DELIVERY=true`. Credentials are read only from
environment variables and are never written to PostgreSQL, imports, manifests,
or application logs.

## Required before hosting real data

1. Company SSO/OIDC and server-side session management.
2. RBAC: Viewer, Importer, Reconciler, Automation Admin, and a separately
   approved PCE Write role.
3. CSRF protection and authenticated audit identity on every configuration,
   import, approval, and delivery action.
4. Secret manager integration for Illumio, SMTP, Box, and session secrets.
5. Private database networking, encrypted transport, backup/restore testing,
   retention policy, and production monitoring.
6. File upload scanning, type/size limits, and object storage with restricted
   access for original imports and generated exports.
7. A dedicated single scheduler worker. Web replicas must never each trigger
   the same scheduled delivery.

## Railway position

Railway remains suitable for a sanitized-data pilot after authentication is
implemented: the API and PostgreSQL service should communicate on Railway's
private network, not via a public database endpoint. It is not authorization to
host UPS CMDB/PCE data before the requirements above are reviewed and approved.

## Later scheduler deployment

The worker entry point is:

```bash
python -m app.scripts.run_due_automations
```

Run it from one cron job or one worker process. It evaluates both task-default
cadence and recipient-level daily/weekly overrides. Tasks and external delivery
are disabled by default.
