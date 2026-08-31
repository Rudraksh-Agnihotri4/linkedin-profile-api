# Tross LinkedIn Profile API

This repository is currently at Milestone 1: scaffold only. It contains the
design-approved package layout and deployment shell, but no LinkedIn retrieval
or other application business logic.

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

Once routes are implemented, the ASGI entry point will run with:

```bash
uv run uvicorn --app-dir src tross_linkedin_api.main:app --host 0.0.0.0 --port 8000
```

## API

The canonical contract is documented in [`docs/API.md`](docs/API.md). The
planned endpoints are:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/profiles:resolve`

These routes are not implemented in the scaffold milestone.

## Approach

The architectural source of truth is under [`docs/`](docs/). The service will
strictly canonicalize a LinkedIn profile URL, pass only the canonical profile id
to a controlled provider, coordinate cache and safety controls through Redis,
map tolerant upstream data into a canonical domain model, and emit a strict
versioned response.

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

- This milestone contains no profile resolution, authentication, caching, rate
  limiting, health-route, provider, parser, or response-model implementation.
- Spike 0 has not been run, so LinkedIn endpoint, session, and payload-shape
  assumptions remain deliberately unfrozen.
- Negative caching remains disabled until Spike 0 proves a deterministic
  not-found signal.
- A process-local upstream concurrency limit is suitable only for the planned
  single-replica, single-worker challenge deployment.
