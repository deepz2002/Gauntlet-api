# Mini Gauntlet API

[![CI](https://github.com/deepz2002/Gauntlet-api/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/deepz2002/Gauntlet-api/actions/workflows/ci.yml?query=branch%3Amain)

FastAPI backend for an inventory-based cloud security scanner. It runs ten checks
across AWS, Azure and Google Cloud, stores scan results in PostgreSQL, and serves
them to the React frontend. No live cloud account or credentials are required.

## Prerequisites

- Docker Desktop with Docker Compose. Install Docker Desktop for your OS; on macOS,
  open the Docker application and wait until its engine is running.
- Python 3.12 for local development. Python is not needed on the host if the API
  runs entirely inside Docker.
- Node.js 22 and npm only for local frontend development. Docker builds the frontend
  itself; see [frontend setup](https://github.com/deepz2002/Gauntlet-ui).

On macOS with Homebrew, install Python if needed:

```sh
brew install python@3.12
python3.12 --version
```

Start Docker Desktop and confirm that Docker is ready:

```sh
open -a Docker
docker info
docker compose version
```

Keep Docker Desktop running while using PostgreSQL. Run the following setup commands
from the API repository root (`Gauntlet-api` in this workspace). The frontend is
maintained separately in [Gauntlet-ui](https://github.com/deepz2002/Gauntlet-ui).
There is no frontend folder or Git submodule in this API repository.

```sh
git clone https://github.com/deepz2002/Gauntlet-api.git
cd Gauntlet-api
```

Choose **one** execution mode below.

## Option A: run the backend in Docker

No local Python installation or manual migration command is required for this
option. Stop any local API process using port 8000 first.

```sh
docker compose up --build -d --wait
docker compose ps
curl http://localhost:8000/api/health
```

Compose starts PostgreSQL, the API and Adminer. The API waits for PostgreSQL,
applies pending migrations, then starts Uvicorn. API health returns `{"status":"ok"}`.
Run the frontend separately and configure its backend URL in the supplied frontend
environment file. The API's CORS origins must include the frontend's browser origin.

| Service | Pinned image | Runtime user |
| --- | --- | --- |
| API | `python:3.12.12-slim-bookworm` | `gauntlet` |
| PostgreSQL | `postgres:16.16-alpine` | Managed by the PostgreSQL image |
| Adminer | `adminer:5.5.1` | Managed by the Adminer image |

The backend has a `.dockerignore` file, health checks and a persistent PostgreSQL
volume. Image rebuilds do not reset database data.

```sh
docker compose ps
docker compose logs --tail=100 api
docker compose exec api id
```

## Option B: run Python locally and PostgreSQL in Docker

### 1. Start the database

Stop the API container if you previously used Option A; this frees port 8000
for local Uvicorn. PostgreSQL itself still runs in Docker.

```sh
docker compose stop api
docker compose up -d --wait db adminer
docker compose ps
docker compose exec db pg_isready -U gauntlet -d gauntlet
```

### 2. Create the Python environment and install dependencies

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Activate `.venv` again whenever you open a new terminal. `requirements-dev.txt`
includes the application dependencies, Alembic, Pytest and Ruff.

### 3. Configure the environment

Save the environment file provided separately by email as `.env` in the repository
root. Preserve any existing local configuration. Environment values are not included
in this README; do not commit the supplied file to Git.

- Use `localhost` for a Python process on your Mac. Compose sets `db` as the
  hostname for the API container, because containers communicate by service name.
- Environment variables exported in your shell override `.env` values.
- `.env` is ignored by Git and Docker.
- `INVENTORY_PATH` selects the input file; do not change the assignment inventory.
- `SCAN_WORKER_LIMIT` accepts 1–64 workers and defaults to four.

### 4. Verify PostgreSQL and create the tables

```sh
python -m app.db.check
alembic upgrade head
alembic current
```

The connection check should succeed and the current migration should be `0001 (head)`.
Migrations create `scans`, `findings` and `alembic_version`; they do not insert sample
scan results. Repeating `alembic upgrade head` safely skips applied revisions.

### 5. Run FastAPI

```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this terminal running. In another terminal:

```sh
curl http://127.0.0.1:8000/api/health
```

Use a single API process. Its background jobs run in-process; startup marks scans
left RUNNING after a previous process stopped as FAILED. Do not run the local and
container APIs simultaneously.

## Open the application and database

| Service | Address |
| --- | --- |
| API Swagger documentation | http://localhost:8000/docs |
| API health | http://localhost:8000/api/health |
| OpenAPI schema | http://localhost:8000/openapi.json |
| Adminer database viewer | http://localhost:8080 |
| Frontend (run separately) | http://127.0.0.1:3000 |

For Adminer, select **PostgreSQL**, not MySQL/MariaDB, and use `db` as the server.
Use the database name, username and password supplied separately with the environment
configuration.

Choose the `public` schema to see the tables. Adminer uses `db` because it is a
container. Desktop database clients use host `localhost`, port `5432`, and the same
credentials. You do not need a separate Postgres.app server.

To inspect the database from a terminal:

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Inside `psql`:

```sql
\dt
SELECT id, status, started_at, finished_at FROM scans ORDER BY started_at DESC;
SELECT status, count(*) FROM findings GROUP BY status;
\q
```

## Database schema

```mermaid
erDiagram
    scans ||--o{ findings : contains

    scans {
        uuid id PK "NOT NULL; default gen_random_uuid()"
        varchar status "NOT NULL; length 16; default RUNNING"
        jsonb account_ids "NOT NULL; nonempty array of selected account IDs"
        timestamptz started_at "NOT NULL; default now()"
        timestamptz finished_at "Nullable while RUNNING"
        text error_message "Nullable failure explanation"
    }

    findings {
        uuid id PK "NOT NULL; default gen_random_uuid()"
        uuid scan_id FK "NOT NULL; references scans.id; ON DELETE CASCADE"
        varchar check_id "NOT NULL; length 64"
        text title "NOT NULL"
        varchar provider "NOT NULL; length 16; aws, azure or gcp"
        text account_id "NOT NULL"
        text region "Nullable"
        text resource_id "Nullable only for CANNOT_SCAN"
        varchar status "NOT NULL; length 16; PASS, FAIL or CANNOT_SCAN"
        varchar severity "NOT NULL; length 16; CRITICAL, HIGH, MEDIUM or LOW"
        text details "NOT NULL; result explanation"
    }

    alembic_version {
        varchar version_num PK "NOT NULL; length 32; current revision 0001"
    }
```

One scan has zero or more findings; every finding belongs to exactly one scan.
`alembic_version` is migration bookkeeping and has no relationship to application
rows. Deleting a scan cascades to its findings.

Database constraints enforce:

- Scan status: RUNNING, COMPLETED or FAILED. RUNNING has no finish time;
  COMPLETED/FAILED require a finish time at or after the start.
- A nonempty `account_ids` JSON array. The service validates its account IDs against
  the inventory; there is no separate accounts table.
- Finding provider, status and severity values. A missing resource ID is permitted
  only for CANNOT_SCAN, including collection permission errors and malformed resources.

Indexes cover scan start time and scan-scoped status/severity, provider, account and
check filters. Lifecycle transition order and scan membership are service rules.

The original input stays in [data/inventory.json](data/inventory.json). Only scan
metadata and generated findings are persisted. Check definitions live in the Python
registry; scores and counts are derived from findings rather than duplicated in tables.

The [complete SQL schema](artifacts/schema.sql) provides the initial DDL for a
**fresh** database. For an existing database, apply Alembic migrations instead of
pasting this script.

## The ten security checks

The rule functions contain short English comments explaining their logic. Metadata
and evaluator references are registered in [registry.py](app/scanner/registry.py).
Add a rule by writing an evaluator and registering it; the engine does not change.

| Check ID | Severity | Collection | Logic |
| --- | --- | --- | --- |
| AWS-S3-01 | HIGH | `s3_buckets` | PASS only when `block_public_acls`, `ignore_public_acls`, `block_public_policy` and `restrict_public_buckets` are all true. Any false flag fails; a null/unreadable configuration cannot be scanned. |
| AWS-EC2-01 | CRITICAL | `security_groups` | FAIL when an ingress TCP/all-protocol rule permits port 22 or 3389 from a public source, including a range containing either port. |
| AWS-IAM-01 | HIGH | `iam_users` | Users without console access pass. Console users pass only with MFA enabled; disabled MFA fails. |
| AWS-IAM-02 | MEDIUM | `iam_users` | FAIL when an active key is strictly older than 90 days at `snapshot_taken_at`. Inactive keys are ignored; exactly 90 days passes. |
| AWS-RDS-01 | HIGH | `rds_instances` | FAIL when `publicly_accessible` is true; false passes. |
| AZ-STG-01 | HIGH | `storage_accounts` | FAIL when `allow_blob_public_access` is true; false passes. |
| AZ-NSG-01 | CRITICAL | `network_security_groups` | FAIL when an inbound Allow TCP/all rule exposes port 22 or 3389 publicly. Ignore Deny and Outbound rules. |
| GCP-GCS-01 | HIGH | `gcs_buckets` | FAIL when an IAM binding includes `allUsers` or `allAuthenticatedUsers`; otherwise pass. |
| GCP-GCS-02 | LOW | `gcs_buckets` | PASS when `uniform_bucket_level_access` is true; false fails. |
| GCP-VPC-01 | CRITICAL | `firewall_rules` | Disabled and EGRESS rules pass. Enabled ingress rules fail if their TCP/all allowances expose port 22 or 3389 publicly. |

Source files: [AWS](app/scanner/checks/aws.py), [Azure](app/scanner/checks/azure.py),
[GCP](app/scanner/checks/gcp.py), and [shared validation](app/scanner/checks/common.py).

Common behavior and assumptions:

- Public sources are `0.0.0.0/0`, `::/0`, and Azure's `Internet`/`*`. Restricted CIDRs
  are not worldwide exposure. Effective routing and NSG priority precedence are not
  simulated because the input does not provide sufficient information.
- Port ranges are inclusive. All-protocol rules cover every port; TCP protocol `6`
  is recognized. Azure wildcard ports and GCP omitted/empty port lists cover all ports.
- Missing fields, wrong types, invalid ports/ranges/CIDRs and future key timestamps
  produce CANNOT_SCAN when they prevent evaluation. A proven violation takes priority
  over unrelated malformed data. Warnings are logged and other records continue.
- A collection listed in `errors` produces one account-level CANNOT_SCAN per applicable
  check, including the original error code and no resource ID. A collection absent
  from both `resources` and `errors` produces no findings.
- Snapshot strings are untrusted. React renders them as text, never HTML. The PDF's
  deliberate HTML string remains unchanged in the inventory.

The score is `100 * PASS / (PASS + FAIL)`, rounded to one decimal. CANNOT_SCAN is
excluded. An empty denominator returns null, shown as N/A. Overall score uses all
findings, not an average of account scores.

Verified full-inventory output: **49 findings: 27 PASS, 17 FAIL, 5 CANNOT_SCAN; score
61.4**. With four workers it takes about three seconds. These are calculated results,
not hardcoded output.

## API endpoints and execution

| Method | Endpoint | Result |
| --- | --- | --- |
| GET | `/api/health` | Liveness response `{"status":"ok"}` |
| GET | `/api/checks` | Ten-check catalog |
| POST | `/api/scans` | HTTP 202 with a persisted RUNNING scan; background execution |
| GET | `/api/scans` | All saved scans, newest first |
| GET | `/api/scans/{id}` | Summary, counts and overall/per-account scores; unknown UUID returns 404 |
| GET | `/api/scans/{id}/findings` | Stored, filtered, ordered and paginated findings |

The frontend scans all accounts with `{}`. The API also accepts
`{"account_ids":["123456789012"]}` for a subset. No body, `{}`, or null `account_ids`
means all accounts; empty/unknown selections return 422. Duplicate IDs are removed.

```sh
curl -X POST http://localhost:8000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{}'
curl http://localhost:8000/api/scans
```

Use the returned `id` in Swagger to view the summary and findings. Findings support
combined case-insensitive `status`, `severity`, `provider`, `account_id` and `check_id`
filters. `page` defaults to 1; `page_size` defaults to 25 and accepts 1–100. Response:
`{items,total,page,page_size}`. Total is counted before pagination.

Order: FAIL → CANNOT_SCAN → PASS, then CRITICAL → HIGH → MEDIUM → LOW, check ID,
resource ID (NULL first), and UUID as a stable tie-breaker. Invalid pagination or
malformed UUIDs return 422. Filtering reads saved results and never starts a scan.

```text
Request → API route → scan service → validate inventory/accounts → commit RUNNING
        → HTTP 202 → background task → engine → registered rule functions
        → commit findings and COMPLETED together

Summary request → SQL aggregations → scoring service → response
Findings request → SQL filters/order/pagination → response
```

The background job owns its database sessions. Accounts run concurrently, with
nonblocking simulated latency inside the worker limit. Unrecoverable background
errors mark the scan FAILED; findings/completion are committed atomically. An input
file already unreadable at request validation returns 503 without creating a scan.

## Migrations and tests

After changing a database model, generate a new revision, review it, and apply it:

```sh
source .venv/bin/activate
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
alembic current
alembic check
```

For the container API, replace `alembic ...` with `docker compose exec api alembic ...`.
To create migrations, use the local development environment so the new revision is
saved in your checkout. `alembic check` detects model/migration drift.

```sh
ruff check .
ruff format --check .
python -m pytest -q
docker compose config --quiet
```

To include PostgreSQL integration tests, keep the database running and set
`TEST_DATABASE_URL` to the database connection supplied separately before running
Pytest. Without it, those integration tests are skipped.

Tests cover all ten checks, malformed input, network edge cases, key-age boundaries,
concurrency, scoring, schema constraints/migrations, API validation/filtering/pagination,
background failures and restart recovery. Integration tests clean up their temporary
schemas and do not insert test fixtures into the application's public tables.

## Stop, restart and troubleshoot

```sh
# Inspect container logs:
docker compose logs --tail=100 api db
# Stop the container stack without deleting database data:
docker compose down
# Restart the container stack later:
docker compose up --build -d --wait
```

For local Uvicorn, stop it with Ctrl+C; start the DB and reactivate `.venv` before
running Uvicorn again. The `postgres_data` volume survives `down` and container
replacement. `docker compose down -v` deletes database data. Changing initialization
credentials does not update users/passwords in an existing volume.

| Symptom | Check |
| --- | --- |
| Cannot connect to Docker daemon | Open Docker Desktop and wait for `docker info` to succeed. |
| FastAPI database startup failure | Start `db`, run `python -m app.db.check`, and verify the local URL uses `localhost`; check for a shell `DATABASE_URL` override. |
| Port 5432 already in use | Stop the separate local PostgreSQL/Postgres.app server if Docker should own this port. |
| Port 8000 already in use | Run either the local API or the container API, not both. |
| Adminer connection refused | Select PostgreSQL, server `db`, and the separately supplied credentials; confirm `db` is healthy. |
| Tables missing | Run `alembic upgrade head` locally, or rebuild/start the API container. |
| Browser cannot reach API | Start FastAPI on 8000 and confirm the frontend origin is in `CORS_ORIGINS`. |

## Current scope

The scanner, six backend endpoints, persistence, migrations, frontend scan/history
flow and local Docker setup are implemented. Authentication and live cloud collection
are not included. CI is configured in `.github/workflows/ci.yml`; production deployment
is described in `DEPLOY.md`.
Production multi-worker execution needs durable jobs and coordination; this version
uses one API process. AI coding assistance is disclosed below.

## Continuous integration and GitHub submission

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull
request, and can be started manually with workflow_dispatch. It uses read-only
repository permissions and requires no cloud secrets:

1. Backend: install dependencies, run Ruff/format checks and all Pytest tests against
   PostgreSQL, then apply migrations and check for schema drift.
2. Containers: build the API image, start the backend stack with a fresh runner
   volume, and run `scripts/smoke_stack.py` directly against FastAPI.

Frontend lint, type checks, tests and image builds run in the separate frontend
repository's workflow. Container logs are printed on failure; the runner's temporary
stack is cleaned up.

The workflow uses the official [checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) actions. It uses Python 3.12,
matching the API image.

The API repository tracks `origin/main`; the frontend has its own `origin/main`.
Both repositories are public. The implementation commit has a verified successful
GitHub Actions run; the badge above links to the latest main-branch runs.

| Submission field | Value |
| --- | --- |
| GitHub repository URL | https://github.com/deepz2002/Gauntlet-api |
| Verified CI run (implementation commit `99cbdf5`) | [Successful run](https://github.com/deepz2002/Gauntlet-api/actions/runs/45463038051) |
| Latest main-branch CI | [Current runs](https://github.com/deepz2002/Gauntlet-api/actions/workflows/ci.yml?query=branch%3Amain) |
| Frontend repository | https://github.com/deepz2002/Gauntlet-ui |

To publish further API changes, commit them on `main` and run `git push`.
For frontend changes, commit and push in the separate `Gauntlet-ui` directory.
Open the API Actions tab and wait for both backend jobs
to pass. If anything fails, inspect the failed step, fix it, and push again. Verify
that the green run belongs to the latest commit before adding its link above.

## AI coding assistance

The ten security rules and inventory are defined by the assignment. I supplied
those requirements together with my development approach, technology choices and
intended application behavior. I used **OpenAI Codex as a coding tool** to translate
that specification into the scanner, API, database models/migrations and React UI,
and to assist with tests, debugging, Docker and CI configuration.

I directed the interface through iterative requirements, including scanning all
cloud accounts automatically, skeleton loading, collapsible history and the API
activity drawer. AI assisted with implementation across these modules. Verification included
automated tests, lint/type checks, real PostgreSQL operations, Docker builds and
browser/API smoke scans.

[DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md) records the supplied direction, coding
assistance by area, verification evidence and per-phase time estimates. I estimate
approximately one hour per phase, seven hours in total. [DEPLOY.md](DEPLOY.md) contains the
AWS production deployment design; no cloud deployment was performed.

## Documentation and submission status

| Item | Status / evidence |
| --- | --- |
| README | Setup, Mermaid schema, ten rules, architecture, tests and limitations documented |
| DEPLOY.md | AWS design, OIDC, operations and read-only scanner permissions documented |
| AI usage | Disclosed above and in DEVELOPMENT_NOTES.md |
| Time spent by phase | Developer-reported estimate: approximately 1 hour per phase, 7 hours total; see DEVELOPMENT_NOTES.md |
| Successful CI linked | Verified implementation run and latest-main workflow linked above |
| Secrets and generated files | Local env/dependency/build files ignored; staged-file credential-pattern review completed |
| Reviewer access | API and frontend repositories verified public |
| Email submission | Not performed |
