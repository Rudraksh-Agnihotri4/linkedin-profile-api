# Codex Execution Guide - Tross LinkedIn Profile API

This repository is for the Tross LinkedIn Profile API hiring challenge.

Read this file first. Then read every file under `docs/`. Treat these documents
as the architectural source of truth unless the user explicitly approves a
change.

## Current Phase

Milestone 1 - Scaffold is reviewed and complete.

The next explicitly approved milestone is Milestone 2 - the bounded LinkedIn
retrieval Spike 0 described below.

Do not implement production business logic during Spike 0. Use only one test
account/session and one known profile, preserve every Spike 0 safety constraint,
save only sanitized fixtures, and stop for review when the bounded spike report
is complete.

## Non-Negotiable Constraints

- Never fetch the user-supplied LinkedIn URL directly.
- Strictly validate and canonicalize LinkedIn profile URLs first.
- Provider code may receive only the canonical profile id and controlled base
  config.
- No L1 cache.
- No Postgres.
- No custom circuit breaker.
- No proxy rotation.
- No TLS fingerprint evasion.
- No CAPTCHA bypass.
- No fake LinkedIn quota numbers.
- No fake session lifetime claims.
- No committed credentials or secrets.
- No raw LinkedIn cookies, CSRF tokens, API keys, or Redis passwords in logs.
- No implementation drift from `docs/` without explaining and getting approval.

## Canonical Architecture

One FastAPI service:

- API key authentication.
- LinkedIn URL canonicalizer.
- Redis-backed profile cache.
- Cache stores only request-independent `CachedProfileSnapshotV1` data, never
  whole `ProfileResponseV1` objects, `request_id`, or request cache status.
- Redis single-flight lock per canonical profile.
- Redis Lua atomic token-bucket limiter.
- Redis upstream cooldown key for explicit upstream throttling/challenge signals.
- Process-local `asyncio.Semaphore` upstream bulkhead.
- Long-lived `httpx.AsyncClient` created during FastAPI lifespan.
- Tolerant LinkedIn upstream parser.
- Canonical domain model.
- Strict versioned `ProfileResponseV1`.
- RFC 9457 Problem Details errors.
- `/health/live` and `/health/ready`.
- Docker/Railway deployment.

## Completed Milestone 1 Scaffold Prompt (Reference)

Milestone 1 is complete. This prompt is retained only as the reviewed scope
record; do not rerun it unless the user explicitly asks.

```text
Read AGENTS.md and every file under docs/. Treat them as the architectural source of truth.

Do not implement LinkedIn retrieval business logic yet.

First scaffold the repository exactly according to docs/LLD.md:
- create the Python uv project files,
- create the src/tross_linkedin_api package structure,
- create empty modules with docstrings or minimal placeholders only,
- create tests/unit, tests/integration, tests/concurrency, and tests/fixtures/linkedin,
- create .env.example with placeholder values only,
- create Dockerfile and document Railway dashboard/CLI deployment settings only,
- create a README skeleton with setup/API/approach/limitations headings.

Do not create railway.json or railway.toml.
Generate a high-entropy evaluator API key outside the repo and store only a SHA-256 or HMAC digest in environment variables.
Deliver the evaluator API key privately; never commit it.

Do not add Postgres, L1 cache, queues, custom circuit breaker, proxy/TLS evasion, or CAPTCHA bypass logic.
Do not add dependencies or architectural components not specified in the design without asking first.

After scaffolding, report what was created and stop.
```

## Next Approved Prompt: Milestone 2 (Spike 0)

The scaffold review is complete. Use this prompt for the next bounded milestone:

```text
Run Spike 0 for LinkedIn retrieval only.

Goal:
Prove that one controlled canonical LinkedIn profile id can be used with the current backend LinkedIn session to retrieve usable profile data.

Rules:
- Use one test LinkedIn account/session only.
- Use one known profile only.
- Never fetch the raw user-supplied URL.
- Build a controlled upstream request from canonical profile id.
- Do not implement the full production provider yet.
- Do not bypass CAPTCHA/checkpoint/access-control signals.
- Do not use proxies or TLS fingerprint evasion.
- Do not commit secrets or raw personal data.
- Save only sanitized fixtures.
- Update docs/LLD.md if endpoint shape or parser assumptions change.
- Stop for review after reporting exact status/content-type/high-level payload shape and which sections are available.
```

## Milestone Plan

Milestone 0 - Design package (reviewed and complete):

- Create canonical docs and this execution guide.
- Stop for review.

Milestone 1 - Scaffold (reviewed and complete):

- Create project structure only.
- Add placeholder modules and config files.
- Add README skeleton.
- Add repository hygiene and sentinels for intentionally empty test directories.
- No LinkedIn retrieval logic.
- Stop for review.

Milestone 2 - LinkedIn retrieval spike (next approved bounded milestone):

- Verify current endpoint/request/session behavior.
- Create sanitized fixtures.
- Update provider/parser LLD.
- Stop for review.

Milestone 3 - Core service:

- Implement settings, logging, auth, URL canonicalization, Redis cache,
  single-flight, atomic limiter, health endpoints, error mapping, and public
  schemas.

Milestone 4 - Provider/parser:

- Implement LinkedIn adapter based on Spike 0.
- Implement tolerant parser to canonical domain model.
- Implement strict public response builder.

Milestone 5 - Hardening and deployment:

- Add full tests.
- Add Docker/Railway deployment.
- Add final README.
- Run local Docker smoke tests and one controlled real hosted Railway smoke test
  before submission.

## Verification Before Any Final Implementation Response

Before claiming a milestone is done:

- Check that files match the docs.
- Run the relevant tests or explain why they could not run.
- Check for secrets in committed files.
- Check that no code path fetches a user-supplied URL directly.
- Check that Redis failure behavior is fail-closed.
- Check that logs redact sensitive data.
- Check that public API response remains strict and versioned.
- Check that cached values are request-independent snapshots, not request
  envelopes.
- Check that no railway.json, railway.toml, secrets, raw API keys, or evaluator
  keys are committed.
