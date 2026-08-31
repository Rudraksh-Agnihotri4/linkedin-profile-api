# Tross LinkedIn Profile API - Failure Matrix

Status: canonical failure design; implementation in progress
Last verified: 2026-08-31

This matrix defines expected behavior for normal, corner, and edge cases. The
goal is predictable degradation without unsafe LinkedIn traffic, secret leakage,
or public schema drift.

## Matrix

| Scenario | Detection | Response | HTTP | Cache | Retry/Cooldown | Log level | Test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Valid URL, cache hit | Redis returns valid `CachedProfileSnapshotV1` | Build request response from cached snapshot | 200 | read | none | info | integration |
| Valid URL, cache miss, upstream success | Cache miss, lock acquired, cooldown clear, parser succeeds | Return fresh response | 200 | write success snapshot TTL | bounded retry only on transient errors | info | integration |
| Valid URL, optional section missing | Parser cannot find optional section | Return partial success with section status | 200 | write success TTL | none | info | fixture parser |
| Valid URL, one section parser drift | Section parser raises controlled error | Return partial success if core identity is valid | 200 | write success TTL with warning | none | warn | fixture parser |
| Core identity missing after parse | Strict response builder cannot produce non-empty core identity | Problem Details `upstream_bad_response` or `schema_drift` | 502 | do not cache success | no retry for parser errors | error | fixture parser |
| Malformed JSON request | FastAPI/body parser error | Problem Details `invalid_json` | 400 | none | none | info | API unit |
| Missing API key | Auth dependency sees no header | Problem Details `api_key_missing` | 401 | none | none | info | API unit |
| Invalid API key | Constant-time compare fails | Problem Details `api_key_invalid` | 401 | none | none | warn | API unit |
| API key over limit | Redis limiter denies | Problem Details `rate_limited` with `Retry-After` | 429 | none | client may retry after header | info | limiter integration |
| URL too long | Canonicalizer length check | Problem Details `invalid_profile_url` | 422 | none | none | info | URL unit |
| URL contains control chars | Canonicalizer pre-parse check | Problem Details `invalid_profile_url` | 422 | none | none | warn | URL unit |
| URL has unsupported scheme | Scheme not `http`/`https` | Problem Details `invalid_profile_url` | 422 | none | none | info | URL unit |
| URL has userinfo | `username` or `password` present | Problem Details `invalid_profile_url` | 422 | none | none | warn | URL unit |
| URL has explicit port | `port` present | Problem Details `invalid_profile_url` | 422 | none | none | warn | URL unit |
| URL host is `linkedin.com.evil.com` | Host allowlist fails | Problem Details `invalid_profile_url` | 422 | none | none | warn | URL unit |
| URL host is `evil.linkedin.com` | Host allowlist fails unless exactly two-letter country subdomain | Problem Details | 422 | none | none | warn | URL unit |
| URL path not `/in/{slug}` | Path parser fails | Problem Details | 422 | none | none | info | URL unit |
| Slug contains invalid chars | Slug regex fails | Problem Details | 422 | none | none | info | URL unit |
| HTTP LinkedIn URL | Scheme accepted, canonicalized to HTTPS | Continue safely | 200 or downstream result | normal | normal | info | URL unit |
| Query/fragment present | Canonicalizer discards query/fragment | Continue with canonical URL | 200 or downstream result | normal | normal | info | URL unit |
| Redis unavailable on profile request | Redis ping/command fails | Fail closed | 503 | unavailable | no upstream fetch | error | integration |
| Redis unavailable on live check | Live does not call Redis | Return live | 200 | none | none | info | health unit |
| Redis unavailable on ready check | Ready ping fails | Return not ready | 503 | none | none | warn | health unit |
| Cache value corrupt | JSON parse or strict validation fails | Delete key if possible, treat as miss | eventual 200/5xx | delete corrupt | normal | warn | integration |
| Single-flight winner succeeds | Follower sees cache after wait | Follower returns cached response | 200 | read | none | info | concurrency |
| Single-flight lock wait expires | Follower cannot acquire and cache still empty | Problem Details `profile_fetch_in_progress` | 503 | none | `Retry-After` short | warn | concurrency |
| Lock owner exceeds TTL | Lock ownership release fails or duplicate risk | Log ownership loss; response may still return if cache write succeeds | 200/5xx | best effort | tune TTL | error | concurrency |
| Lock release fails due Redis issue | Redis exception on release | Do not crash after response if already safe; log | 200 or 503 | uncertain | fail closed for new requests | error | integration |
| Upstream budget exhausted | Redis upstream limiter denies before a physical HTTP attempt | Problem Details with `Retry-After` | 503 | none | retry after limiter reset | info | limiter integration |
| Upstream cooldown active | Cooldown key exists | Problem Details with `Retry-After` | 503 | none | wait for cooldown TTL | info | integration |
| Upstream connect timeout | HTTPX timeout | Retry if attempts remain; else timeout error | 504 | no success cache | bounded retry | warn | provider unit |
| Upstream read timeout | HTTPX timeout | Retry if attempts remain; else timeout error | 504 | no success cache | bounded retry | warn | provider unit |
| Upstream pool timeout | HTTPX pool timeout | Retry if attempts remain; else service busy | 503/504 | none | bounded retry | warn | provider unit |
| Upstream 429 with small Retry-After | Classifier sees 429/header | Set bounded cooldown and return immediately | 503 | no success cache | no additional LinkedIn attempt in that request | warn | provider unit |
| Upstream 429 with huge Retry-After | Header exceeds configured max | Set cooldown capped by policy and return immediately | 503 | no success cache | no additional LinkedIn attempt in that request | warn | provider unit |
| Upstream 500/502/503/504 | Classifier transient | Retry bounded; fail if exhausted | 502/504 | no success cache | bounded retry | warn | provider unit |
| Upstream 401/403/login page | Classifier auth required | Stop; do not retry aggressively | 503 | no success cache | short cooldown until operator updates session | error | provider fixture |
| Upstream challenge/checkpoint/CAPTCHA | Body/header classifier | Stop; do not bypass | 503 | no success cache | cooldown; operator action | error | provider fixture |
| Upstream 404/profile not visible | Classifier sees deterministic not-found or visibility-limited payload | Return `profile_not_found` only for Spike-0-proven deterministic not-found; return partial if identity exists | 404/200 | negative cache only after Spike 0 proves safe | none | info | provider fixture |
| Unexpected content type | Classifier mismatch | Treat as malformed or challenge if markers found | 502/503 | no success cache | no parser retry | warn | provider fixture |
| HTML instead of JSON | Classifier inspects for login/challenge markers | Auth/challenge or malformed payload | 502/503 | no success cache | cooldown on challenge | warn/error | provider fixture |
| Public response validation fails | Pydantic strict validation error | Internal bug or mapper bug | 500 | do not cache | none | error | schema unit |
| Logging redaction failure risk | Sensitive fields in structured event | Redaction filter masks before emit | not applicable | none | none | test fails | logging unit |
| Shutdown while request in flight | Uvicorn signal/lifespan shutdown | Rely on Uvicorn graceful drain; lifespan teardown closes resources only | 200/503 depending stage | best effort | none | info | integration/manual |
| Railway healthcheck during startup | `/health/ready` before dependencies ready | Not ready | 503 | none | Railway retries during deploy | info | health integration |
| Railway Redis private URL uses `redis://` | Env URL from Railway | Use as supplied | normal | normal | none | info | config unit |
| Missing LinkedIn session env | Settings validation or provider check | Ready may fail if profile endpoint enabled; profile returns operational error | 503 | no upstream | operator action | error | settings unit |
| Expired LinkedIn session | Auth-required classifier | Stop and report operational error | 503 | no success cache | cooldown; operator refresh | error | provider fixture |
| User sends many different uncached profiles | Cache misses, per-key locks do not coalesce globally | Process-local semaphore and upstream limiter bound upstream work | 200/503 | normal | upstream limiter/cooldown; inbound limiter separately applies | info/warn | load/concurrency |
| User sends same uncached profile concurrently | Same profile hash lock | One upstream call, followers return cache or 503 | 200/503 | write once | no duplicate by default | info | concurrency |

## Normal Cases

- Valid `/in/{slug}` URL with cache hit.
- Valid URL with cache miss and successful upstream parse.
- Valid URL where optional sections are absent.
- Valid URL with query parameters from LinkedIn sharing links.
- Documented two-letter country subdomain URL.
- HTTP public profile URL canonicalized to HTTPS.

## Corner Cases

- Same profile requested concurrently.
- Different uncached profiles requested concurrently.
- Cache value corrupt or from older schema.
- Lock wait expires but winner later succeeds.
- Redis recovers after readiness failure.
- Upstream returns `Retry-After`.
- Optional LinkedIn sections are visible for one profile but absent for another.
- Profile language suffix exists in URL.

## Edge Cases

- Malicious URL with userinfo.
- Hostname tricks:
  `linkedin.com.evil.com`, `evil.linkedin.com`, punycode/confusable hosts.
- Explicit port.
- Embedded newline/tab/control characters.
- Oversized URL.
- Redirect-looking path or encoded slashes.
- Auth challenge/CAPTCHA/checkpoint.
- Session expiry during a request burst.
- Shutdown while holding a single-flight lock.
- Redis unavailable while inbound traffic continues.

## Redis Failure Policy

Redis is required for:

- Cache.
- Single-flight.
- Rate limiting.
- Upstream cooldown.

Therefore protected profile requests fail closed when Redis is unavailable.

Rationale:

- If Redis is down, bypassing it would also bypass all upstream protections.
- A direct-fetch fallback could multiply LinkedIn traffic during exactly the
  failure mode where coordination is missing.
- This behavior is easier to defend in an interview than a fragile degraded
  direct mode.

## Upstream Challenge Policy

When LinkedIn returns login, checkpoint, CAPTCHA, or access-control signals:

- Stop.
- Do not attempt bypass.
- Do not rotate identity.
- Do not alter TLS fingerprint.
- Do not retry aggressively.
- Return a 503 operational Problem Details response.
- Set short cooldown to protect the session.
- Redact all upstream details from the client response and logs.

## Upstream Budget And Bulkhead Policy

- Check upstream cooldown before entering the provider attempt loop.
- Acquire and release the process semaphore for each physical LinkedIn HTTP
  attempt only.
- Consume one upstream-budget token for every physical LinkedIn HTTP attempt.
- Release the semaphore before any retry backoff.
- If the global upstream budget is exhausted, return 503 with `Retry-After`.
- If LinkedIn returns `429`, set bounded cooldown and return immediate 503 with
  `Retry-After`; return without issuing another LinkedIn attempt.

## Negative Cache Policy

- Negative cache remains disabled until Spike 0 proves a deterministic
  not-found signal.
- Generic upstream `404` before Spike 0 is not safely cacheable by itself.
- Visibility-limited profile data with usable identity is partial `200`, not a
  negative-cache entry.

## Schema Drift Policy

When upstream payload shape changes:

1. The tolerant parser attempts section-level extraction.
2. Unknown fields are ignored.
3. Missing optional paths produce section warnings.
4. If non-empty core identity remains valid, return partial `200`.
5. If core identity cannot be trusted, return `502`.
6. Add sanitized fixture before fixing parser logic.
7. Keep `ProfileResponseV1` stable.

## Retry Policy Summary

Retry:

- Transport errors.
- Connect/read/pool timeouts.
- Selected transient HTTP statuses.

Do not retry:

- Input/auth errors.
- Parser errors.
- LinkedIn `429`.
- Login/challenge/CAPTCHA.
- Most 4xx.
- Profile not found.

## Logging Severity Guide

| Level | Examples |
| --- | --- |
| `info` | Request completed, cache hit/miss, known optional section missing. |
| `warn` | Rate limited, transient upstream retry, schema drift partial, cache corruption. |
| `error` | Redis unavailable, LinkedIn auth expired, challenge detected, public response validation failure. |
| `critical` | Not expected for normal app flow; reserved for unrecoverable startup configuration failure. |
