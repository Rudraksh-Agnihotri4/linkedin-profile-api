# Tross LinkedIn Profile API

## What this service does

This FastAPI service accepts a LinkedIn public-profile URL, strictly validates
and canonicalizes its `/in/{slug}`, resolves the profile through a bounded
three-call LinkedIn Voyager GraphQL flow, and returns a strict versioned JSON
response.

Resolution is dynamic: the backend can resolve any valid LinkedIn
`/in/{slug}` profile visible to its configured LinkedIn session. No author
profile, slug, or profile URN is hardcoded.

## Live evaluation

- **Swagger UI:** <https://linkedin-profile-api-1zee.onrender.com/docs>
- **POST endpoint:** <https://linkedin-profile-api-1zee.onrender.com/v1/profiles:resolve>
- **Authentication:** the current hosted evaluation mode is public and requires
  no API key.

In Swagger, expand `POST /v1/profiles:resolve`, select **Try it out**, replace
the example slug with a public LinkedIn profile slug, and select **Execute**.

```bash
curl --request POST \
  --url https://linkedin-profile-api-1zee.onrender.com/v1/profiles:resolve \
  --header 'content-type: application/json' \
  --data '{"profile_url":"https://www.linkedin.com/in/your-public-slug"}'
```

The first request after inactivity may be slower because the service uses
Render's free tier.

## API contract

### Request schema and validation

```json
{
  "profile_url": "https://www.linkedin.com/in/your-public-slug"
}
```

`profile_url` is a required JSON string. The accepted target is a canonical
LinkedIn public-profile path, `/in/{slug}`, where the slug is 3-100 ASCII
letters, digits, or hyphens. The service accepts `http` or `https` input on the
strictly allowlisted LinkedIn hosts, then lowercases the slug and emits the
canonical form `https://www.linkedin.com/in/{slug}`. Invalid hosts, userinfo,
ports, malformed paths, non-profile URLs, and deceptive URL forms are rejected
before any LinkedIn request occurs.

### Successful response example

A successful request returns `200 OK`, `content-type: application/json`, an
`x-request-id`, `x-cache: miss`, and `cache-control: no-store`. Values below are
representative; image fields are `null` when the proven response does not
contain a safe LinkedIn CDN image.

```json
{
  "api_version": "v1",
  "request_id": "req_example",
  "profile": {
    "canonical_id": "example-profile",
    "canonical_url": "https://www.linkedin.com/in/example-profile",
    "name": "Example Person",
    "headline": "Software Engineer",
    "location": null,
    "about": null,
    "images": {
      "profile": {
        "url": "https://media.licdn.com/dms/image/example/profile-displayphoto/0",
        "width": 400,
        "height": 400
      },
      "background": {
        "url": "https://media.licdn.com/dms/image/example/profile-background/0",
        "width": 1584,
        "height": 396
      }
    },
    "experience": [],
    "education": [],
    "skills": [],
    "certifications": [],
    "languages": []
  },
  "sections": {
    "identity": {"status": "complete", "item_count": null},
    "about": {"status": "unavailable", "item_count": null},
    "experience": {"status": "unavailable", "item_count": 0},
    "education": {"status": "unavailable", "item_count": 0},
    "skills": {"status": "unavailable", "item_count": 0},
    "certifications": {"status": "unavailable", "item_count": 0},
    "languages": {"status": "unavailable", "item_count": 0},
    "images": {"status": "complete", "item_count": 2}
  },
  "warnings": [
    {"code": "section_unavailable", "section": "about", "message": "About was not observed in the three proven responses."},
    {"code": "section_unavailable", "section": "experience", "message": "Value-level mapping is not currently available."},
    {"code": "section_unavailable", "section": "education", "message": "Value-level mapping is not currently available."},
    {"code": "section_unavailable", "section": "skills", "message": "Value-level mapping is not currently available."},
    {"code": "section_unavailable", "section": "certifications", "message": "Value-level mapping is not currently available."},
    {"code": "section_unavailable", "section": "languages", "message": "A profile-language section was not safely confirmed."}
  ],
  "cache": {
    "stored_at": "2026-01-01T12:00:00Z",
    "expires_at": "2026-01-01T12:00:00Z"
  },
  "fetched_at": "2026-01-01T12:00:00Z"
}
```

Equal cache timestamps and `x-cache: miss` reflect the current uncached
vertical slice; they do not claim that Redis served the response.

### Current field coverage

Currently value-mapped and returned:

- canonical identity (`canonical_id`, `canonical_url`) and `name`;
- `headline` and `location` when present;
- profile image and background image when present and safely constructible as
  LinkedIn HTTPS CDN URLs.

Currently unavailable or not value-mapped:

- `about` is returned as `null` with an `unavailable` section status;
- `experience`, `education`, `skills`, `certifications`, and `languages` are
  returned as empty arrays with `unavailable` statuses. Structural signals for
  several of these sections were observed, but the service deliberately does
  not infer unproven value-level mappings.

### Error/status-code table

Errors use RFC 9457 Problem Details with
`content-type: application/problem+json`. The body includes `type`, `title`,
`status`, `detail`, `instance`, `request_id`, and a stable `code`; retryable
responses may also include `retry_after_seconds` and `retry-after`.

| Status | Meaning in the public contract |
| --- | --- |
| `400` | Malformed JSON request body. |
| `403` | Reserved for a later protective access-policy layer; documented but not currently emitted by the public route. |
| `404` | Reserved for deterministic profile-not-found mapping once that upstream signal is safely proven. |
| `422` | Missing/wrongly typed request data or an invalid/unsupported LinkedIn profile URL. |
| `429` | Reserved for the deferred distributed inbound rate limiter; current LinkedIn throttling is reported as `503`. |
| `500` | Unexpected internal failure. |
| `502` | LinkedIn returned an unusable response, invalid normalized JSON, or an untrusted contract shape. |
| `503` | The LinkedIn session needs authentication, a challenge requires operator attention, or LinkedIn is throttling retrieval. |
| `504` | A bounded upstream LinkedIn request timed out. |

The public evaluation endpoint does not advertise or require a `401` API-key
flow.

## Reverse-engineered LinkedIn approach

The service uses the exact high-level three-query Voyager GraphQL sequence
proven for the current backend session:

1. **Identity:** query by canonical `vanityName` and discover the profile's
   runtime `urn:li:fsd_profile:...` identifier.
2. **ProfileComponents:** query that runtime URN with section type
   `content-collections`.
3. **ProfileCards:** query the same runtime URN with section type
   `CONTENT_COLLECTIONS_DETAILS`.

The query hashes are observed current LinkedIn web-client contracts, not a
public or stable API, and may drift. The repository contains the contract names
needed by the implementation but exposes no personal captured URNs, cookies,
CSRF tokens, or other secrets.

Each Voyager response uses LinkedIn's normalized JSON envelope. The parser
collects included entities, merges repeated entities by URN, correlates root
elements and the discovered profile URN back to the requested slug, and maps
only fields supported by consistent evidence. Missing or ambiguous data is
reported as unavailable rather than guessed. Authentication walls, redirects,
HTML, checkpoints/CAPTCHA challenges, throttling signals, unexpected content
types, and unsafe payload shapes stop the sequence immediately.

Because the runtime URN is discovered from the requested vanity name on every
resolution, the same flow supports arbitrary valid `/in/{slug}` URLs visible
to the configured backend session.

## Architecture

```text
Client
  -> FastAPI POST /v1/profiles:resolve
  -> strict LinkedIn URL canonicalizer
  -> controlled LinkedIn client
  -> [1] vanityName identity -> runtime fsd_profile URN
  -> [2] ProfileComponents(content-collections)
  -> [3] ProfileCards(CONTENT_COLLECTIONS_DETAILS)
  -> response classifier + normalized-envelope parser
  -> ProfileResponseV1 or RFC 9457 Problem Details
```

## Security and SSRF protections

- Hosts are strictly allowlisted to `linkedin.com`, `www.linkedin.com`, and
  two-letter LinkedIn country subdomains. Deceptive suffixes, userinfo, custom
  ports, control characters, and path tricks are rejected.
- The raw user-supplied URL is never fetched. After validation, only the
  canonical slug reaches the provider, which constructs controlled HTTPS
  requests against the configured LinkedIn origin.
- The lifespan-owned HTTP client uses `follow_redirects=False` and
  `trust_env=False`, so redirects and ambient proxy environment variables
  cannot silently change the destination.
- There is no browser automation, proxy rotation, TLS/browser-fingerprint
  evasion, access-control bypass, or CAPTCHA bypass.
- Cookies, CSRF tokens, API keys, authorization headers, and related secret
  names are redacted from logs. Requests log a hash of the slug rather than the
  raw profile identifier.
- Authentication, HTML, redirect, challenge, CAPTCHA, and throttle signals are
  terminal; the client stops instead of continuing the three-call sequence.

## Local setup

Python 3.12 and `uv` are required. Install `uv` using its official installer
or package manager, then from the repository root run:

```bash
uv sync --locked
cp .env.example .env
```

Replace placeholders in `.env`; never commit secret values. The minimum
configuration for the current vertical slice is:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `local`, `staging`, `production`, or `test`. |
| `APP_NAME` | Service name used by the runtime. |
| `PUBLIC_BASE_URL` | Absolute public base URL used in Problem Details links; use `http://localhost:8000` locally. |
| `LOG_LEVEL` | Standard level such as `INFO`. |
| `API_KEY_HASHES` | Digest-only configuration validated at startup. It becomes authentication material only if the existing API-key dependency is enabled for a local/private deployment; never place a raw key here. |
| `LINKEDIN_BASE_URL` | Controlled origin; must remain `https://www.linkedin.com`. |
| `LINKEDIN_USER_AGENT` | Non-empty descriptive user agent. |
| `LINKEDIN_LI_AT` | Backend LinkedIn session cookie; secret. |
| `LINKEDIN_JSESSIONID` | Backend AJAX session cookie; secret. |
| `LINKEDIN_CSRF_TOKEN` | Unquoted CSRF token matching `JSESSIONID`; secret. |
| `SCHEMA_DRIFT_SAMPLE_LOGGING` | Keep `false` unless sanitized drift diagnostics are intentionally enabled. |

The current hosted evaluator route is public and needs no `x-api-key` header.
Digest-based API-key auth code remains available for private/local wiring; its
presence does not make the hosted endpoint authenticated.

Load the environment and start Uvicorn:

```bash
set -a
source .env
set +a
uv run uvicorn --app-dir src tross_linkedin_api.main:app \
  --host 0.0.0.0 --port 8000
```

Local Swagger is available at <http://localhost:8000/docs> and liveness at
<http://localhost:8000/health/live>.

## Testing

Run the full mocked suite and make Python warnings fail the run:

```bash
PYTHONPATH=src PYTHONWARNINGS=error .venv/bin/python -m unittest discover -s tests -v
```

Then verify that all application and test modules compile:

```bash
PYTHONPATH=src PYTHONWARNINGS=error .venv/bin/python -m compileall -q src tests
```

Tests use a mocked upstream transport and make no live LinkedIn requests. This
README-only rewrite did not rerun the suite, so it intentionally does not claim
a test count.

## Docker and Render deployment

The repository-root `Dockerfile` uses Python 3.12, installs the locked
production dependencies, and starts Uvicorn on Render's dynamic `PORT` (falling
back to `8000`). Use these Render Web Service settings:

| Setting | Value |
| --- | --- |
| Runtime | `Docker` |
| Branch | `main` |
| Dockerfile | `./Dockerfile` |
| Health check path | `/health/live` |
| Auto-deploy | Enabled on commit |
| Public access | Render-provided HTTPS URL |

Set the required environment variables in the Render dashboard; do not bake
session material into the image. The Dockerfile already contains the start
command and binds Uvicorn to `0.0.0.0:${PORT:-8000}`. Render free-tier instances
can spin down, so the first request after inactivity can have cold-start
latency.

## Known limitations

- About is unavailable.
- Experience, education, skills, certifications, and languages value-level
  mappings are not currently returned even though structural signals were
  observed.
- LinkedIn Voyager query hashes may drift and require a controlled contract
  update.
- Redis cache, per-profile single-flight, distributed rate limiting and
  cooldown, bounded retry bulkhead, readiness, and negative caching are not
  implemented yet.
- Render free-tier cold starts add latency after inactivity.
- Profile and field visibility depends on the configured backend LinkedIn
  session; an expired, restricted, or challenged session stops retrieval.

## Responsible-use caveat

LinkedIn access and automation may be governed by LinkedIn's terms, policies,
and applicable law. Operators are responsible for ensuring an appropriate
legal basis, authorization, and compliant data handling. This project does not
bypass authentication, access controls, checkpoints, or CAPTCHA challenges.
