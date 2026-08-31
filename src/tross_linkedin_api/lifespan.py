"""FastAPI lifespan ownership for settings and the long-lived HTTP client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx

from tross_linkedin_api.linkedin.client import LinkedInClient
from tross_linkedin_api.linkedin.transport import LinkedInTransport
from tross_linkedin_api.logging import configure_logging
from tross_linkedin_api.settings import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI


def build_lifespan(
    configured_settings: Settings | None = None,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
):
    """Build an application lifespan, with a mockable upstream transport."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = configured_settings or Settings.from_env()
        configure_logging(settings.log_level)
        cookies = httpx.Cookies()
        cookies.set(
            "li_at",
            settings.linkedin_li_at,
            domain=".linkedin.com",
            path="/",
        )
        cookies.set(
            "JSESSIONID",
            settings.linkedin_jsessionid_cookie_value,
            domain=".linkedin.com",
            path="/",
        )
        client = httpx.AsyncClient(
            base_url=settings.linkedin_base_url,
            headers={
                "accept": "application/vnd.linkedin.normalized+json+2.1",
                "accept-language": "en-US,en;q=0.9",
                "csrf-token": settings.linkedin_csrf_token,
                "user-agent": settings.linkedin_user_agent,
                "x-restli-protocol-version": "2.0.0",
            },
            cookies=cookies,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(
                connect=settings.upstream_connect_timeout_seconds,
                read=settings.upstream_read_timeout_seconds,
                write=settings.upstream_write_timeout_seconds,
                pool=settings.upstream_pool_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_connections=settings.httpx_max_connections,
                max_keepalive_connections=settings.httpx_max_keepalive_connections,
                keepalive_expiry=settings.httpx_keepalive_expiry_seconds,
            ),
            transport=upstream_transport,
        )
        app.state.settings = settings
        app.state.http_client = client
        app.state.linkedin_client = LinkedInClient(
            LinkedInTransport(client),
            retry_after_default_seconds=settings.upstream_cooldown_default_seconds,
            retry_after_max_seconds=settings.upstream_retry_after_max_seconds,
        )
        try:
            yield
        finally:
            await client.aclose()

    return lifespan
