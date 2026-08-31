# Tross LinkedIn Profile API - Test Plan

Status: canonical test plan; implementation in progress
Last verified: 2026-08-31

This plan focuses on correctness, safety, and defendability. Live LinkedIn
behavior is validated only in an explicit local Spike 0, not in CI.

## Test Strategy

```mermaid
flowchart LR
    Unit[Unit tests]
    Integration[Redis/API integration tests]
    Concurrency[Concurrency tests]
    Fixtures[Sanitized upstream fixtures]
    Smoke[Docker/Railway smoke tests]

    Unit --> Integration --> Concurrency --> Smoke
    Fixtures --> Unit
    Fixtures --> Integration
```

Test layers:

- Unit tests for deterministic pure logic.
- Integration tests for FastAPI routes and Redis behavior.
- Concurrency tests for single-flight and atomic limiter semantics.
- Provider tests against sanitized fixtures and mocked HTTPX transport.
- Manual/local Spike 0 against real LinkedIn session.
- Deployment smoke tests, including one controlled real hosted Railway request
  before submission.

## CI Policy

CI should run:

- Formatting check.
- Linting.
- Type checking where configured.
- Unit tests.
- Integration tests with test Redis if available.
- No live LinkedIn tests.
- No tests requiring real credentials.

Live LinkedIn tests:

- Manual only.
- Use a test account/session.
- Never commit cookies, raw personal data, or unsanitized payloads.

## Unit Tests

### URL Canonicalizer

Valid cases:

- `https://www.linkedin.com/in/john-smith`
- `https://linkedin.com/in/john-smith/`
- `http://www.linkedin.com/in/john-smith`
- `http://ca.linkedin.com/in/john-smith`
- `https://www.linkedin.com/in/JohnSmith`
- `https://www.linkedin.com/in/john-smith?trk=profile`
- `https://www.linkedin.com/in/john-smith#about`
- `https://www.linkedin.com/in/john-smith/es`

Invalid cases:

- Empty string.
- URL longer than max.
- `ftp://www.linkedin.com/in/john-smith`
- `https://evil.com/in/john-smith`
- `https://linkedin.com.evil.com/in/john-smith`
- `https://evil.linkedin.com/in/john-smith`
- `https://www.linkedin.com:443/in/john-smith`
- `https://user:pass@www.linkedin.com/in/john-smith`
- `https://www.linkedin.com/company/example`
- `https://www.linkedin.com/in/ab`
- `https://www.linkedin.com/in/name_with_underscore`
- `https://www.linkedin.com/in/name%2Fother`
- URL containing newline/tab/control characters.

Assertions:

- Canonical profile id is lowercase.
- Canonical URL uses `https://www.linkedin.com/in/{slug}`.
- Query and fragment are discarded.
- No canonicalizer output contains the original raw URL for fetching.

### API Key Auth

Cases:

- Missing key -> 401.
- Invalid key -> 401.
- 403 is reserved for future valid-but-insufficient authorization.
- Valid key -> dependency returns authenticated principal.
- Timing-safe comparison helper is used.
- Raw keys are not logged.
- High-entropy API keys are verified through SHA-256 or HMAC digests.
- Evaluator API key is delivered privately and never appears in committed files.

### Settings

Cases:

- Required env missing fails startup validation.
- Invalid numeric limits fail startup validation.
- Redis URL is accepted as supplied.
- Production mode requires necessary secrets.
- `.env.example` contains placeholders, not real values.

### Rate Limiter Lua

Cases:

- First request with full bucket allowed.
- Repeated requests decrement tokens.
- Denied when tokens exhausted.
- Tokens refill over time.
- Expiry is set.
- Concurrent calls cannot exceed available capacity.
- Return shape includes `allowed`, `remaining`, `reset_at`, and `retry_after`.

### Cache

Cases:

- Cache hit returns validated `CachedProfileSnapshotV1` and builds a fresh
  request response envelope.
- Cache miss returns none.
- Cache write sets TTL.
- Corrupt JSON is treated as miss and deleted.
- Schema-invalid cached snapshot is treated as miss and deleted.
- Negative cache tests run only after Spike 0 proves a deterministic not-found
  signal; generic upstream `404` is not treated as safely cacheable before that.

### Single-Flight

Cases:

- Winner acquires lock.
- Follower waits and returns cache after winner stores result.
- Follower returns 503 when wait timeout expires and cache remains empty.
- Winner re-reads cache after acquiring lock.
- Timeout path re-reads cache exactly once.
- No separate simultaneous cache polling loop is used while lock acquire blocks.
- Lock release only releases owned lock.
- Lock TTL configuration is checked against operation budget.

### Upstream Classifier

Cases:

- `200 application/json` -> `success_json`.
- `200 text/html` with login marker -> `auth_required`.
- `200 text/html` with challenge marker -> `challenge_or_checkpoint`.
- `401`/`403` -> auth/access error.
- `404` -> possible not-found/visibility classification, but not cacheable
  before Spike-0-verified deterministic not-found.
- `429` with `Retry-After` -> bounded cooldown and immediate 503, without
  another LinkedIn attempt.
- `5xx` -> transient failure.
- Unexpected content type -> malformed payload.

### Parser and Mapper

Fixture-backed cases:

- Full profile fixture maps all public sections.
- Missing optional sections produce `empty` or `unavailable`.
- Section shape drift produces section-level warning.
- Missing or empty core identity fails profile response generation.
- Unknown upstream fields are ignored.
- Public model forbids extra fields.
- Public model rejects wrong scalar types in strict mode.
- Profile dates accept only `PartialDate` shapes: `YYYY`, `YYYY-MM`, or
  `YYYY-MM-DD`.
- Operational timestamps use RFC 3339 datetimes.
- Section statuses use the fixed typed response model with all expected keys.

### Error Mapping

Cases:

- Every internal exception maps to intended HTTP status and problem code.
- Problem Details includes `type`, `title`, `status`, `detail`, `instance`,
  `request_id`, and `code`.
- No problem response leaks secrets or raw upstream payloads.

### Logging Redaction

Cases:

- `x-api-key` is redacted.
- `authorization` is redacted.
- `cookie` and `set-cookie` are redacted.
- `li_at`, `JSESSIONID`, CSRF token names/values are redacted.
- Redis URL password is redacted.
- Log injection characters in user input are sanitized or omitted.
- Profile id hash is logged instead of full raw URL where possible.

## Integration Tests

### FastAPI Routes

Use HTTPX ASGI transport or FastAPI TestClient with lifespan enabled.

Cases:

- `/health/live` returns 200 without Redis.
- `/health/ready` returns 200 with Redis.
- `/health/ready` returns 503 when Redis is unavailable.
- `POST /v1/profiles:resolve` rejects unauthenticated requests.
- `POST /v1/profiles:resolve` rejects invalid URLs.
- Valid request with mocked provider returns `ProfileResponseV1`.
- Valid request cache hit does not call provider.
- Provider partial response returns 200 with warnings.

### Redis Integration

Use local Redis or test container.

Cases:

- Lua limiter executes atomically and reloads on `NOSCRIPT` without storing
  Redis helper keys for script state.
- Rate limiter works under real Redis.
- Single-flight lock works under real Redis.
- Cache TTL expires.
- Cooldown key blocks upstream attempts.
- Redis command failure causes fail-closed profile response.

## Concurrency Tests

### Same Profile Stampede

Setup:

- Empty cache.
- 20 concurrent requests for the same canonical profile.
- Mock provider with controlled delay.

Expected:

- Provider called once.
- One winner role in logs.
- Followers return cached response or bounded 503 depending configured wait.
- No duplicate upstream calls by default.
- Single-flight uses one blocking acquire path, not a polling loop.

### Different Profile Burst

Setup:

- Empty cache.
- Many concurrent requests for different canonical profiles.
- Mock provider records concurrent executions.

Expected:

- Active provider calls never exceed `MAX_UPSTREAM_CONCURRENCY`.
- Semaphore acquisition is bounded per physical HTTP attempt.
- The semaphore is released before retry backoff.
- Each physical LinkedIn HTTP attempt consumes one upstream-budget token.
- Upstream budget exhaustion returns 503 with `Retry-After`.
- Inbound limiter behavior remains atomic.

### Inbound Limiter Race

Setup:

- Token bucket capacity `N`.
- Launch more than `N` simultaneous allowed-attempt requests.

Expected:

- At most `N` allowed.
- Remaining inbound requests denied with 429.
- No token double-spend.

### Upstream Budget Race

Setup:

- Global upstream token bucket capacity `N`.
- Launch more than `N` simultaneous physical-attempt requests with cache misses
  and cooldown clear.

Expected:

- At most `N` physical LinkedIn HTTP attempts are allowed.
- Denied upstream attempts return 503 with `Retry-After`.
- No token double-spend.

## Spike 0 Test Plan

Purpose:

- Prove the current LinkedIn retrieval path before implementing full provider
  logic.

Inputs:

- One test LinkedIn account/session.
- One known profile URL.
- One local-only spike script or notebook under `work/`, not committed if it
  contains secrets.

Steps:

1. Canonicalize the known LinkedIn URL.
2. Construct a controlled upstream request from canonical id, not from raw URL.
3. Send request using normal HTTPX client and session material.
4. Record:
   - status code,
   - content type,
   - redirect behavior,
   - required cookies/headers,
   - high-level top-level JSON keys or HTML data source,
   - which target sections are available.
5. If a not-found case is deliberately tested later, record whether the signal is
   deterministic enough for short negative cache. Do not treat generic `404` as
   safely cacheable by default.
6. Remove or redact all personal/session data.
7. Create sanitized fixture files under `tests/fixtures/linkedin/`.
8. Update `docs/LLD.md` provider/parser details if the actual shape differs.

Success criteria:

- At least one controlled authenticated request returns usable profile data.
- The response contains enough data to map core identity and at least some
  required sections.
- Required headers/session assumptions are documented.
- Any negative-cache behavior is documented only if Spike 0 proves deterministic
  not-found.

Stop criteria:

- Login, checkpoint, CAPTCHA, or account-protection challenge appears.
- Repeated 429 or throttling appears.
- Session appears invalid.
- Upstream shape cannot produce core profile identity.

Do not do during Spike 0:

- No proxy rotation.
- No TLS/client fingerprint evasion.
- No CAPTCHA bypass.
- No automated account creation.
- No bulk profile fetching.

## Deployment Smoke Tests

Local Docker:

- Build image without secrets.
- Run with local `.env` placeholders and Redis.
- `GET /health/live` -> 200.
- `GET /health/ready` -> 200 when Redis reachable.
- Protected endpoint rejects missing key.
- Protected endpoint handles mocked provider in test mode if supported.

Railway:

- Deployment becomes active with `/health/ready`.
- Public HTTPS URL serves health endpoints.
- Redis private URL works.
- Profile endpoint rejects missing/invalid key.
- With valid key and mocked/safe provider mode, API contract is correct.
- Run one controlled real hosted profile-resolution smoke test before submission
  using the privately delivered evaluator key and a safe known profile. Do not
  commit the key, session material, or raw response.

## Acceptance Criteria

The implementation is ready for final review when:

- All unit tests pass.
- Redis integration tests pass.
- Concurrency tests prove single-flight and limiter behavior.
- Parser tests cover full, missing, partial, and drift fixtures.
- No live credentials are committed.
- No logs contain secrets.
- Docker build succeeds.
- Railway deployment serves HTTPS and health endpoints.
- One controlled real hosted Railway smoke test succeeds before submission.
- Evaluator API key has been delivered privately and is not committed.
- README documents setup, API usage, approach, known limitations, and ethical
  boundaries.

## Manual Review Checklist

- Does any code path fetch `profile_url` directly?
- Does Redis outage fail closed?
- Are limiter decisions atomic?
- Is single-flight lock TTL longer than upstream operation budget?
- Does a profile stampede cause only one provider call?
- Does every physical LinkedIn HTTP attempt consume one upstream-budget token?
- Is the semaphore acquired and released per physical attempt only?
- Does LinkedIn `429` set bounded cooldown and return 503 without another
  LinkedIn attempt?
- Does public response validation forbid extras?
- Does public response validation require non-empty core identity?
- Are partial sections explicit?
- Are negative-cache tests conditional on Spike-0-proven deterministic not-found?
- Are LinkedIn challenge/auth responses treated as stop conditions?
- Are all secrets in env variables?
- Are docs and code aligned?
