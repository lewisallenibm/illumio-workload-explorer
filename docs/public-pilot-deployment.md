# Public team pilot deployment

This is a small-team pilot, not an approval to publish real CMDB or PCE data
without organizational authorization. The application defaults to `local` and
binds only to localhost. Public mode is fail-closed.

## Recommended pilot: Railway + Cloudflare Access

1. Create a Railway PostgreSQL service. Keep it private; only the Railway web
   service receives its `DATABASE_URL`.
2. Deploy this repository using `Dockerfile` / `railway.toml`. Run
   `python -m alembic upgrade head` once as a release step against the new
   empty Railway database, then start the service.
3. Set `WEB_DEPLOYMENT_MODE=public`,
   `WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN`, and
   `WEB_CLOUDFLARE_ACCESS_AUD`. Store `DATABASE_URL` and every PCE, Box, and
   email credential only in Railway variables, never in Git or a `.env` file.
4. Put a Cloudflare domain in front of the Railway service. Create a
   self-hosted Cloudflare Access application with an **allow policy containing
   exact pilot email addresses**. Do not select “everyone” or “all valid
   emails”. Email one-time PIN is suitable for a 3–5 person pilot.
5. Copy Cloudflare's Access team domain and the application AUD tag into the
   deployment variables. In public mode the app validates the signed
   `Cf-Access-Jwt-Assertion` header, including issuer, expiry, signature, and
   audience. A direct host URL cannot bypass this check.
6. Set `ILLUMIO_USE_REAL_CLIENT=false` initially. A real, approved non-prod
   PCE can later use read-only connection testing before any sync. Keep
   `ILLUMIO_ALLOW_PCE_WRITEBACK=false`.

## AWS-shaped equivalent

`deploy/aws/apprunner.yaml.example` shows how the same container can run on
AWS App Runner. In that model:

- **App Runner** runs this FastAPI web process.
- **RDS PostgreSQL** is the managed PostgreSQL database.
- **Secrets Manager** stores the database URL, Cloudflare AUD, PCE credentials,
  and future delivery credentials.
- **IAM** grants the App Runner service only `secretsmanager:GetSecretValue`
  for this app's named secrets; an example policy is included.
- **Cloudflare Access** remains the internet-facing authentication layer.

Create no AWS resources until an account, region, owner, and budget are
approved. The example contains placeholders and cannot deploy as-is.

## Required pilot checks

- Confirm Cloudflare Access rejects an unlisted email and allows each tester.
- Confirm direct Railway/App Runner URL returns `403` for normal pages.
- Confirm `/health` returns only service health, never data.
- Restore a PostgreSQL backup into a separate test database before importing
  non-mock data.
- Test real PCE connectivity read-only with a least-privilege API account.
