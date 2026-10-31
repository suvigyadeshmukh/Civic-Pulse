# Civic Pulse — Repair Session Record

**Workspace:** `C:\Users\suvig\OneDrive\Desktop\projects\civic-pulse-workspace`
**Scope:** Seven sequential repairs (Fix 1 → Fix 7) applied across configuration, domain packages, application bootstrap, Docker infrastructure, and the pytest core-infrastructure suite.
**Status:** All fixes implemented and all previously open environment issues closed. The suite passes **26/26 with live PostgreSQL, Redis, and S3**, unit tests pass fully offline (23 passed, 3 skipped), and `uvicorn app.main:app` boots both online (healthy) and completely offline (degraded, local-disk storage). All changes remain **uncommitted**.

---

## Table of Contents

1. [Fix 1 — `.env` Resolution, CORS Parsing, AES Key Normalisation, Safe Decryption Errors](#fix-1)
2. [Fix 2 — setuptools / pytest Configuration](#fix-2)
3. [Fix 3 — Missing `__init__.py`, `tasks.py`, and Empty Routers](#fix-3)
4. [Fix 4 — Safe Domain Router Mounting](#fix-4)
5. [Fix 5 — Hardened Database Extension Checks](#fix-5)
6. [Fix 6 — PostgreSQL 16 + PostGIS + pgvector Docker Configuration](#fix-6)
7. [Fix 7 — Pytest Fixtures and Core Infrastructure Tests](#fix-7)
8. [Master File Inventory](#master-file-inventory)
9. [Verification Summary](#verification-summary)
10. [Environment Closure (Post-Fix-7)](#environment-closure)
11. [Remaining Risks and Open Issues](#remaining-risks)

---

<a id="fix-1"></a>
## Fix 1 — `.env` Resolution, CORS Parsing, AES Key Normalisation, Safe Decryption Errors

**Target files:** `server/app/core/settings.py`, `server/app/core/security.py`

### Problem

- The `env_file` path `("../.env", ".env")` was resolved relative to the process working directory, so the canonical workspace-root `.env` was not reliably loaded when the server was started from a different directory.
- `CORS_ORIGINS` accepted only a JSON array string or a Python list; a valid-JSON non-array (e.g. a bare quoted string) or an empty string produced an invalid value.
- `PII_ENCRYPTION_KEY` was passed straight to `base64.b64decode()`, which raised on malformed input or produced a non-32-byte key that later failed inside `AESGCM()`.
- `decrypt_pii_dict()` leaked raw `InvalidTag` / JSON decode errors to callers instead of a controlled application error.

### Implementation

`server/app/core/settings.py`:

- Added `_WORKSPACE_DIR = Path(__file__).resolve().parents[2]` and `_SERVER_DIR = Path(__file__).resolve().parents[1]`.
- Replaced the relative `env_file` tuple with an ordered absolute list: workspace `.env`, workspace `.env.example`, then `server/.env`.
- Extended `_parse_cors_origins` to handle: empty/whitespace string → `[]`, JSON array → list of strings, valid JSON non-array → CSV split, comma-separated string → stripped list, and native `list`/`tuple`/`set` → list of strings.

`server/app/core/security.py`:

- Added `_decode_pii_key(raw_key)` which validates Base64 with `validate=True`, accepts a 32-byte key directly, and otherwise falls back to a deterministic `hashlib.sha256(raw_key.encode()).digest()` with a logged warning — guaranteeing exactly 32 bytes so `AESGCM` never fails at construction.
- Added a length/type guard in `decrypt_pii_dict()`: non-`bytes` or blobs shorter than 28 bytes (12-byte nonce + 16-byte tag minimum) raise `AppException(400, "DECIPHER_ERROR", "Invalid encrypted payload")`.
- Wrapped decryption and JSON parsing in `try/except (InvalidTag, ValueError, UnicodeDecodeError, json.JSONDecodeError)` and re-raised as the same controlled `AppException`, preserving the original exception via `from exc`.

### Result

Settings load deterministically regardless of CWD; CORS parsing tolerates every realistic input shape; a misconfigured PII key degrades with a warning instead of crashing startup; ciphertext failures surface as a uniform 400 envelope.

---

<a id="fix-2"></a>
## Fix 2 — setuptools / pytest Configuration

**Target file:** `server/pyproject.toml`

### Problem

- `setuptools>=61.0.0` was too old for the installed packaging toolchain, so `pip install -e .` did not behave as expected.
- Pytest configuration used `minversion = "7.0"` (invalid against the installed pytest 9.x) and `addopts = "-ra -q --asyncio-mode=auto"`, mixing CLI-style flags into `addopts` and clashing with the installed `pytest-asyncio 1.4.x`.

### Implementation

- Raised the build requirement to `requires = ["setuptools>=68.0", "wheel"]`.
- Rewrote `[tool.pytest.ini_options]` to modern pytest-asyncio keys:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["."]
python_files = ["test_*.py", "*_test.py"]
```

(The `integration` marker was added later under Fix 7.)

### Result

`pip install -e .` succeeded. The suite collected cleanly with `configfile: pyproject.toml` and `asyncio: mode=Mode.AUTO`.

---

<a id="fix-3"></a>
## Fix 3 — Missing `__init__.py`, `tasks.py`, and Empty Routers

**Created files:**

| File |
|---|
| `server/app/domains/__init__.py` |
| `server/app/domains/identity/__init__.py` |
| `server/app/domains/policy_explainer/__init__.py` |
| `server/app/domains/grievance_triage/__init__.py` |
| `server/app/domains/bureaucracy_agent/__init__.py` |
| `server/app/domains/fact_verification/__init__.py` |
| `server/app/domains/grievance_triage/tasks.py` |

**Modified files:** the five `router.py` modules (`identity`, `policy_explainer`, `grievance_triage`, `bureaucracy_agent`, `fact_verification`), each previously 0 bytes.

### Problem

Domain directories lacked package markers, `grievance_triage` had no `tasks.py` despite the worker expecting one, and every `router.py` was empty — so `_mount_domain_routers()` could not find a `router` attribute and no domain routes were ever exposed.

### Implementation

- Each `__init__.py` carries a one-line package docstring (e.g. `"""Identity & authentication domain."""`).
- `grievance_triage/tasks.py` registers a real Celery task:

```python
from app.worker import celery_app

@celery_app.task(name="grievance_triage.health_check")
def health_check() -> str:
    """Trivial worker task used to confirm Celery wiring is functional."""
    return "ok"
```

- Each `router.py` was populated with the minimal valid router:

```python
from fastapi import APIRouter

router = APIRouter()
```

### Result

All domain packages import cleanly, `grievance_triage` exposes a callable Celery task, and every configured router is now discoverable by the bootstrap logic in Fix 4.

---

<a id="fix-4"></a>
## Fix 4 — Safe Domain Router Mounting

**Target file:** `server/app/main.py`

### Problem

`_mount_domain_routers()` used a single broad `try/except ImportError` around both import *and* `include_router()`. Three specific defects:

1. Any import-time exception other than `ImportError` was logged at WARNING with `exc_info=True` and swallowed without `continue`, allowing inconsistent control flow.
2. A present-but-invalid `router` attribute (e.g. a non-`APIRouter` object) reached `include_router()` and could crash the whole application.
3. An exception thrown by `include_router()` itself was caught by the same handler as an import failure, conflating the two and risking partial router state.

### Implementation

Split into three isolated stages, each with its own handler and a guaranteed `continue`:

```python
try:
    mod = importlib.import_module(module_path)
except ModuleNotFoundError as exc:
    logger.warning("Skipping router %s: module not found (%s).", module_path, exc)
    continue
except Exception:
    logger.exception("Skipping router %s during application bootstrap.", module_path)
    continue

domain_router = getattr(mod, attr_name, None)
if not isinstance(domain_router, APIRouter):
    logger.warning(
        "Skipping router %s: missing or invalid APIRouter instance (attribute '%s').",
        module_path, attr_name,
    )
    continue

try:
    application.include_router(domain_router, prefix=prefix, tags=tags)
except Exception:
    logger.exception("Skipping router %s during application bootstrap.", module_path)
    continue
```

The existing `_DOMAIN_ROUTER_CONFIG` (including the `/mock-gov-portal` entry) was preserved unchanged rather than renamed, to avoid altering existing routing behaviour.

### Result

A single broken domain is logged at WARNING and skipped; the remaining domains still mount and the application boots.

---

<a id="fix-5"></a>
## Fix 5 — Hardened Database Extension Checks

**Target files:** `server/app/core/database.py`, `server/app/main.py`

### Problem

`verify_db_connection_and_extensions()`:

- Ran `CREATE EXTENSION` implicitly absent — it only *read* `pg_extension` and **raised `RuntimeError`** if anything was missing, aborting startup.
- Any single failed statement inside the transaction aborted the outer transaction, so subsequent extensions could not be checked.
- Returned a different result shape (`connected` / `extensions_found` / `missing`) than the health endpoint expected.
- Returned full exception messages that could contain usernames/hosts.

### Implementation

`server/app/core/database.py`:

- `_REQUIRED_EXTENSIONS` changed from a 3-element set to an ordered list including **`uuid-ossp`**: `["pgcrypto", "postgis", "uuid-ossp", "vector"]`.
- Added `_classify_extension_error(exc)` mapping SQLSTATE `42501` → `"insufficient database privileges"` and `58P01` → `"extension not available on the server"`, falling back to the exception class name. All output is credential-safe.
- Extension creation now runs inside `conn.begin_nested()` **savepoints**, so a failed `CREATE EXTENSION` rolls back only to its savepoint and the remaining extensions plus the final catalog query still run.
- Executes `text('CREATE EXTENSION IF NOT EXISTS "…")` via `text()` (no raw string interpolation into an execute path that could mis-bind).
- Replaced `raise RuntimeError(...)` with a degraded return:

```python
{"database": "connected", "extensions": installed}          # success
{"database": f"degraded ({type(exc).__name__})", "extensions": []}  # failure
```

`server/app/main.py`:

- `lifespan` now branches on `db_info.get("database") == "connected"` — INFO when connected, WARNING when degraded — instead of treating every result as success.
- `/health` derives DB status from `db_info["database"]`:

```python
db_status = {
    "status": "ok" if db_info.get("database") == "connected" else "error",
    **db_info,
}
```

  A degraded database can therefore never be reported as healthy.
- The DB probe failure path reports only `type(exc).__name__`, never `str(exc)`.
- Added `await engine.dispose()` on shutdown alongside `redis_client.aclose()`.

### Result

A missing extension or an account without `CREATE EXTENSION` privileges leaves the app in a degraded-but-usable state instead of crashing startup; the health endpoint reflects that degradation truthfully; the engine is cleanly disposed on shutdown.

---

<a id="fix-6"></a>
## Fix 6 — PostgreSQL 16 + PostGIS + pgvector Docker Configuration

**Target files:** `infra/postgres/Dockerfile`, `docker-compose.yml`
**Unchanged:** `infra/postgres/init-extensions.sql` (already correct)

### Problem

- `docker-compose.yml` used an inline `dockerfile_inline:` block duplicating (and drifting from) the real Dockerfile.
- The reference `RUN apt-get install postgresql-16-pgvector` against `postgis/postgis:16-3.4` **fails today**: that image is Debian 11 (bullseye), and PostgreSQL's live PGDG mirror no longer publishes the `bullseye-pgdg` suite (HTTP 404).

### Implementation (updated during environment closure)

`infra/postgres/Dockerfile` — upgraded to the `16-3.5` base. **Note:** despite the
version name, `postgis/postgis:16-3.5` is published on Debian 11 (bullseye) and there
is no bookworm variant of that tag, so the archive retarget is still required:

```dockerfile
FROM postgis/postgis:16-3.5
RUN sed -i \
        's|http://apt.postgresql.org/pub/repos/apt/|https://apt-archive.postgresql.org/pub/repos/apt/|' \
        /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-16-pgvector && \
    rm -rf /var/lib/apt/lists/*
```

`docker-compose.yml` — uses the custom Dockerfile and publishes PostgreSQL on host
port **5433** (see “Environment Closure” below):

```yaml
postgres:
  image: civicpulse-postgres:16-postgis-pgvector
  build:
    context: .
    dockerfile: infra/postgres/Dockerfile
  ports:
    - "5433:5432"
```

Preserved unchanged: image name, all `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
env vars, health check, `postgres_data` named volume, init-script mount at
`/docker-entrypoint-initdb.d/01-init-extensions.sql`, and the `civicpulse-network`
plus all service dependencies.

`infra/postgres/init-extensions.sql` already created `uuid-ossp`, `pgcrypto`, `vector`, `postgis` — no edit needed.

### Verification results (final)

| Check | Result |
|---|---|
| `docker compose config` | **VALID** — custom Dockerfile, `5433:5432`, init mount, env/volume intact |
| `docker compose build postgres` | **SUCCESS** — PostgreSQL `16.9`, pgvector `0.8.6-1.pgdg11+1`, PostGIS `3.5.2` |
| Container health | `Up (healthy)` |
| Existing volume compatibility | Started cleanly on the volume created by the previous image |
| PostGIS upgrade | `ALTER EXTENSION postgis/postgis_topology/postgis_tiger_geocoder UPDATE` → `3.5.2` |
| Installed extensions | `fuzzystrmatch 1.2`, `pgcrypto 1.3`, `plpgsql 1.0`, `postgis 3.5.2`, `postgis_tiger_geocoder 3.5.2`, `postgis_topology 3.5.2`, `uuid-ossp 1.1`, `vector 0.8.6` |
| pgvector | `SELECT '[1,2,3]'::vector` → `[1,2,3]` ✅ |
| PostGIS | `SELECT PostGIS_Version()` → `3.5 USE_GEOS=1 USE_PROJ=1 USE_STATS=1` ✅ |
| `SHOW server_version` | `16.9 (Debian 16.9-1.pgdg110+1)` |

Containers remain running after verification; volume `civicpulse_postgres_data` preserved.

---

<a id="fix-7"></a>
## Fix 7 — Pytest Fixtures and Core Infrastructure Tests

**Target files:** `server/tests/conftest.py`, `server/tests/test_core_infrastructure.py`
**Related:** `server/pyproject.toml`, `server/app/core/storage.py`, `server/app/main.py`

### Problem

- `conftest.py` was **0 bytes** — no `client` fixture existed.
- The suite lacked the modern HTTPX `ASGITransport` approach and relied on external services being up.
- Two **verified production defects** were found while writing health tests:
  1. `StorageService.health_check()` only caught `ClientError`; a MinIO-down `EndpointConnectionError` (a `BotoCoreError`) escaped and made `/health` return 500.
  2. `/health` awaited the Redis and S3 probes unguarded, so any raised exception bypassed envelope handling.

### Implementation

**`server/tests/conftest.py`** (created, 23 lines) — single async fixture, no lifespan execution:

```python
@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client
```

`raise_app_exceptions=False` is required so the 500-handler test can assert on the response rather than receive the raw exception.

**`server/tests/test_core_infrastructure.py`** — expanded from 17 to **26 tests**, structured into four clearly separated groups:

| Group | Tests |
|---|---|
| Settings & DB metadata | `test_settings_singleton_and_defaults`, `test_settings_cors_parsing_variants`, `test_database_naming_convention` |
| Password | `test_security_argon2_password` |
| JWT | `test_security_jwt_token_flow`, `…_rejects_expired_token`, `…_rejects_malformed_token`, `…_rejects_wrong_or_missing_signing_configuration` |
| PII | `test_security_pii_vault_aes_gcm`, `test_security_pii_rejects_truncated_and_tampered_ciphertext`, `test_security_pii_key_has_controlled_fallback` |
| Envelope / exceptions | `test_api_envelope_serialisation_and_optional_fields`, `test_pagination_params`, `test_exception_classes`, `test_app_exception_handler_envelope`, `test_unexpected_exception_handler_hides_internals` |
| Mocked API | `test_api_request_id_middleware`, `test_api_custom_404_envelope`, `test_health_endpoint_reports_healthy_services`, `test_health_endpoint_never_reports_degraded_database_as_healthy`, `test_health_endpoint_survives_raising_dependency_probes`, `test_storage_health_check_handles_connection_errors`, `test_rbac_require_roles_dependency` |
| **Integration** (`@pytest.mark.integration`) | `test_live_postgres_connection_and_extensions`, `test_live_redis_read_write`, `test_live_minio_bucket_accessibility` |

**`server/pyproject.toml`** — registered the marker:

```toml
markers = [
    "integration: requires live PostgreSQL, Redis, or MinIO services",
]
```

**`server/app/core/storage.py`** (defect fix):

```python
from botocore.exceptions import BotoCoreError, ClientError
...
except (ClientError, BotoCoreError) as exc:
    logger.warning("S3 bucket health check failed for '%s' (%s).", self._bucket, type(exc).__name__)
    return {"status": "error", "bucket": self._bucket, "detail": type(exc).__name__}
```

(`detail` also changed from `str(exc)` to `type(exc).__name__` to stay credential-safe.)

**`server/app/main.py`** (defect fix) — each health probe individually wrapped:

```python
try:
    redis_status = await redis_health_check()
except Exception as exc:
    logger.warning("Redis health check raised %s.", type(exc).__name__)
    redis_status = {"status": "error", "detail": type(exc).__name__}
# identical pattern for s3_status
```

### Test results

**Without Docker** (`pytest -q`, services stopped):

```text
23 passed, 3 skipped in 6.84s
```

The 3 skips are exactly the `integration` tests, each with an explicit reason.

**With live PostgreSQL (5433) + Redis + MinIO/S3:**

```text
26 passed in 0.64s
```

| Integration test | Result |
|---|---|
| `test_live_postgres_connection_and_extensions` | PASSED — extensions `{pgcrypto, postgis, uuid-ossp, vector}` |
| `test_live_redis_read_write` | PASSED — real PING / SET with TTL / GET / DELETE |
| `test_live_minio_bucket_accessibility` | PASSED — real bucket creation + `backend == "s3"` |

### Coverage confirmation

| Required area | Result |
|---|---|
| Password hashing / verification | ✅ PASSED |
| JWT create / decode / expiry / tamper / wrong secret | ✅ 4 tests PASSED |
| PII encrypt / decrypt / tampered blob / key fallback | ✅ 3 tests PASSED |
| ApiEnvelope + PaginatedMeta | ✅ PASSED |
| AppException + handlers (incl. stack-trace hiding) | ✅ PASSED |
| `/health` healthy / degraded / raising probes | ✅ 3 tests PASSED |

### Final cache state

`server/.pytest_cache/v/cache/lastfailed` = `{}`. Read for diagnosis only; **never modified or deleted**.

---

<a id="master-file-inventory"></a>
## Master File Inventory

### Modified (tracked)

| File | Fix / purpose |
|---|---|
| `.env.example` | Environment closure — PostgreSQL host port 5433 |
| `.gitignore` | Environment closure — ignore `server/.local_storage/` |
| `docker-compose.yml` | 6 + closure — `5433:5432`, working MinIO image, `minio-init` removed |
| `infra/postgres/Dockerfile` | 6 + closure — `postgis/postgis:16-3.5` |
| `server/app/core/database.py` | 5 + closure — bounded asyncpg connect timeout |
| `server/app/core/redis_bus.py` | Closure — bounded Redis socket timeouts + health ping timeout |
| `server/app/core/security.py` | 1 |
| `server/app/core/settings.py` | 1 + closure — default DB URLs on port 5433 |
| `server/app/core/storage.py` | 7 + closure — non-fatal S3 bootstrap + local-disk fallback |
| `server/app/domains/bureaucracy_agent/router.py` | 3 |
| `server/app/domains/fact_verification/router.py` | 3 |
| `server/app/domains/grievance_triage/router.py` | 3 |
| `server/app/domains/identity/router.py` | 3 |
| `server/app/domains/policy_explainer/router.py` | 3 |
| `server/app/main.py` | 4, 5, 7 + closure — StaticFiles mount at `/local-media` |
| `server/pyproject.toml` | 2, 7 |
| `server/tests/conftest.py` | 7 |
| `server/tests/test_core_infrastructure.py` | 7 + closure — live S3 assertion / fallback skip |

### Created (untracked)

| File | Fix |
|---|---|
| `server/app/domains/__init__.py` | 3 |
| `server/app/domains/bureaucracy_agent/__init__.py` | 3 |
| `server/app/domains/fact_verification/__init__.py` | 3 |
| `server/app/domains/grievance_triage/__init__.py` | 3 |
| `server/app/domains/grievance_triage/tasks.py` | 3 |
| `server/app/domains/identity/__init__.py` | 3 |
| `server/app/domains/policy_explainer/__init__.py` | 3 |
| `FIXES-IMPLEMENTATION-REPORT.md` | This document |

### Modified but git-ignored

| File | Note |
|---|---|
| `.env` | PostgreSQL host port changed to 5433 (ignored by `.gitignore`) |

### Verified unchanged (correct as found)

| File | Note |
|---|---|
| `infra/postgres/init-extensions.sql` | Already created all four required extensions |

**Diff stat:** 18 files changed, **929 insertions(+), 171 deletions(−)**, plus 8 new files.

---

<a id="verification-summary"></a>
## Verification Summary

| Check | Outcome |
|---|---|
| `pip install -e .` | ✅ Success |
| `pytest -q` (offline, no Docker) | ✅ 23 passed, 3 skipped |
| `pytest -v` (live PostgreSQL 5433 + Redis + MinIO) | ✅ **26 passed, 0 skipped** |
| `docker compose config` | ✅ VALID |
| `docker compose up -d postgres redis minio` | ✅ All three `Up (healthy)` |
| `docker compose build postgres` | ✅ Success (PG 16.9, PostGIS 3.5.2, pgvector 0.8.6) |
| Container health | ✅ All healthy |
| pgvector type cast | ✅ `[1,2,3]` |
| `PostGIS_Version()` | ✅ `3.5 USE_GEOS=1 USE_PROJ=1 USE_STATS=1` |
| Live S3 bucket bootstrap | ✅ `ensure_bucket_exists()` → `backend: s3` |
| `uvicorn app.main:app` (online) | ✅ Boots in ~1.7s; `/health` → `healthy` |
| `uvicorn app.main:app` (offline) | ✅ Boots with local fallback; `/health` → `degraded` (HTTP 200) |
| Local fallback upload + serving | ✅ `upload_bytes()` writes to disk; `GET /local-media/...` → 200 |
| `.pytest_cache/…/lastfailed` | ✅ `{}` (untouched) |
| Credentials / volumes / app init | ✅ All preserved |

**Environment used:** Python 3.11.9 (`.venv`), httpx 0.28.1, pytest 9.2.0, pytest-asyncio 1.4.1, Docker Desktop on Windows.

---

<a id="environment-closure"></a>
## Environment Closure (Post-Fix-7)

The four items below were applied to close the previously open environment issues.

### 1. Host PostgreSQL remapped to 5433

- `docker-compose.yml`: `postgres.ports` → `"5433:5432"` (container internals unchanged).
- `.env`, `.env.example`, and `server/app/core/settings.py` defaults now use `localhost:5433` for both `DATABASE_URL` and `SYNC_DATABASE_URL`.
- Inside the Compose network, `api` and `worker` still override to `@postgres:5432` via their `environment:` blocks (which take precedence over `env_file`).
- Result: the container binds successfully while the native Windows PostgreSQL 18 service keeps port 5432.

### 2. Working MinIO image + non-fatal local fallback

- Upstream `minio/minio` and `minio/mc` Docker Hub repositories are gone; `quay.io/minio/minio` returns 401 and `localstack/localstack:s3-latest` was discontinued in March 2026.
- `docker-compose.yml` now uses `pgsty/minio:RELEASE.2026-08-04T00-00-00Z`, an actively maintained MinIO rebuild that ships `minio`, `mc`, and `curl`. The original server command, credentials, ports 9000/9001, volume, and a `curl` health check are preserved.
- The `minio-init` (`minio/mc`) container was **removed**; `StorageService.ensure_bucket_exists()` creates the bucket and applies the public-read policy via boto3.
- `server/app/core/storage.py`:
  - `ensure_bucket_exists()` never raises — on `ClientError`, `BotoCoreError`, or any other exception it logs a warning and activates the fallback.
  - Local disk root: `server/.local_storage/<bucket>/` (git-ignored).
  - `upload_bytes()` writes via `pathlib` when in fallback (or when an S3 upload fails) and returns `/local-media/<key>`.
  - `download_bytes()`, `delete_object()`, `generate_presigned_url()`, and `health_check()` understand fallback mode.
  - Short botocore timeouts (`connect_timeout=2`, `read_timeout=4`, `max_attempts=1`) keep offline startup fast.
- `server/app/main.py` mounts `storage_service.local_root` at `/local-media` with FastAPI `StaticFiles`.
- Verified: offline `upload_bytes()` wrote to disk and `GET /local-media/receipts/<file>` returned 200 with the exact bytes.

### 3. Dockerfile upgraded to `postgis/postgis:16-3.5`

- Base image is now `16-3.5` (PostGIS 3.5.2, pgvector 0.8.6).
- The `apt-archive` retarget is **still required**: `16-3.5` is published on Debian 11 (bullseye), not bookworm, and no bookworm variant of the tag exists. The live `bullseye-pgdg` suite returns 404.
- The existing `civicpulse_postgres_data` volume started cleanly; PostGIS extensions were upgraded in place with `ALTER EXTENSION … UPDATE` to 3.5.2.

### 4. Test and boot verification

- `docker compose up -d --build postgres redis minio` → all three healthy.
- `cd server && pytest -v` → **26 passed, 0 skipped**.
- `uvicorn app.main:app` → `/health` returns `healthy` with `database.ok` (4 extensions), `redis.ok`, `s3.ok/backend=s3`.
- Offline (services stopped) → boot succeeds and `/health` returns HTTP 200 `degraded` with `s3.ok/backend=local`.

---

<a id="remaining-risks"></a>
## Remaining Risks and Open Issues

### 1. MinIO image is a community rebuild — **supply-chain note**

- `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` is a maintained rebuild because the official images are unavailable/unauthenticated from this network. It is pinned by release tag, but it is not published by MinIO, Inc.
- Mitigation: if official access is restored, switch the image back to `quay.io/minio/minio` (same CLI, no other change needed).

### 2. Init SQL does not re-run on existing volumes — **operational risk**

- PostgreSQL's entrypoint executes `/docker-entrypoint-initdb.d/*.sql` **only** on first initialization.
- The existing volume was created earlier, so the script did not re-run; the required extensions were already present and PostGIS was updated manually.
- Any fresh or pre-existing volume without extensions still needs manual `CREATE EXTENSION` or a reinitialization after backup.

### 3. PGDG archive dependency in the Dockerfile — **build fragility (documented)**

- The `bullseye-pgdg` suite is no longer on the live PGDG mirror, so the build depends on `https://apt-archive.postgresql.org/pub/repos/apt/`.
- The `16-3.5` base is still bullseye; no bookworm variant exists for that tag. If the archive is retired, the image build will fail and the base/tag strategy must be revisited.

### 4. Offline degraded boot is bounded, not instant — **expected behaviour**

- With all containers stopped, Docker Desktop's port proxy accepts TCP connections and stalls the handshake. Timeouts were added (asyncpg `timeout=3`, Redis `socket_timeout=3`, botocore 2s/4s) so startup completes and `/health` returns within a bounded time instead of hanging.
- Online boot is ~1.7s; offline degraded boot is roughly 15–20s.

### 5. Benign pre-existing router warning — **cosmetic**

- `server/app/domains/bureaucracy_agent/mock_legacy_portal.py` is still a 0-byte file, so `_mount_domain_routers()` logs `missing or invalid APIRouter instance (attribute 'mock_portal_router')` and skips the `/mock-gov-portal` mount.
- Startup is unaffected. Populating that file with a minimal `APIRouter` would silence the warning.

### 6. All changes uncommitted

- Working tree contains modifications from all seven fixes, the environment closure, and the new domain package files. Nothing has been committed; a commit was not requested.

---

## Appendix — Key Facts

| Item | Value |
|---|---|
| Base image | `postgis/postgis:16-3.5` |
| Built image | `civicpulse-postgres:16-postgis-pgvector` |
| PostgreSQL | 16.9 |
| PostGIS | 3.5.2 |
| pgvector | 0.8.6 |
| S3 image | `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` |
| Required extensions | `pgcrypto`, `postgis`, `uuid-ossp`, `vector` |
| Host PostgreSQL port | 5433 |
| Test count | 26 (23 unit/mocked + 3 integration) |
| Offline result | 23 passed, 3 skipped |
| Online result | **26 passed, 0 skipped** |
| Uvicorn online | `healthy` |
| Uvicorn offline | `degraded` (HTTP 200, local fallback) |
