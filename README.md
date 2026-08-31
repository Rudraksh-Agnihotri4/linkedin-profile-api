# Tross LinkedIn Profile API

This repository contains the reviewed scaffold plus the current production
vertical slice: API-key authentication, strict LinkedIn URL canonicalization,
the Spike-0B-proven three-query LinkedIn flow, conservative response
classification, sanitized fixture-backed parsing, and a strict v1 response.

## Setup

Prerequisites:

- Python 3.12 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- Redis when dependency-backed implementation begins.

Create the local environment from the lockfile:

```bash
uv sync --locked
cp .env.example .env
```

Replace placeholders only in the local `.env` or deployment environment. Never
commit API keys, LinkedIn session material, or Redis credentials.

Load the local file into the process environment, then run the ASGI entry point:

```bash
set -a
source .env
set +a
uv run uvicorn --app-dir src tross_linkedin_api.main:app --host 0.0.0.0 --port 8000
```

## API

The canonical contract is documented in [`docs/API.md`](docs/API.md). The
current vertical slice implements:

- `GET /health/live`
- `POST /v1/profiles:resolve`
- `GET /openapi.json` and `GET /docs`

`GET /health/ready` remains deferred with the Redis-backed safety envelope.

## Approach

The architectural source of truth is under [`docs/`](docs/). The current slice
strictly canonicalizes a LinkedIn profile URL, passes only the canonical profile
id to a controlled provider, maps tolerant upstream data into a canonical
domain model, and emits a strict versioned response. Redis coordination and its
associated protective controls are the next implementation milestone.

The design intentionally excludes an L1 cache, Postgres, queues, a custom
circuit breaker, proxy rotation, TLS fingerprint evasion, and CAPTCHA bypass.

## Deployment

The Dockerfile installs locked dependencies with `uv` and starts one Uvicorn
worker on Railway's `PORT` with a graceful shutdown timeout.

Configure Railway through its dashboard or CLI:

- Create one web service from this repository and one Redis service.
- Inject application and secret values as environment variables; use the Redis
  service reference for `REDIS_URL`.
- Enable a public HTTPS domain for the web service.
- Set the deployment healthcheck path to `/health/ready` after health routes are
  implemented.
- Keep one replica and one Uvicorn worker for the challenge submission.

No `railway.json` or `railway.toml` is used.

## Known Limitations

- Redis cache, single-flight, inbound/upstream rate limits, cooldown state,
  readiness checks, and the process bulkhead are not implemented yet. This
  slice must not be treated as deployment-ready until those protections land.
- Fresh responses therefore use `x-cache: miss`, `cache-control: no-store`, and
  a zero-lifetime cache envelope (`stored_at == expires_at`).
- The three proven queries safely map identity and images. About was not
  observed; experience, education, skills, certifications, and languages expose
  only unconfirmed structural signals, so the API returns empty arrays with
  explicit `unavailable` statuses and warnings rather than inventing values.
- Retries are intentionally absent in this slice. Classifications retain
  retryability metadata for the later bounded retry layer, while `429`, login,
  redirect, and challenge signals stop immediately.
- Query hashes are reverse-engineered upstream contracts and can drift. They
  require a separately authorized bounded re-verification if LinkedIn changes.
- Negative caching remains disabled because no deterministic not-found signal
  has been proven.
