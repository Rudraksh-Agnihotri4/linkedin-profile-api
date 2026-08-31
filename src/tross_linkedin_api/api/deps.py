"""FastAPI dependency wiring."""

from __future__ import annotations

from fastapi import Request

from tross_linkedin_api.linkedin.client import LinkedInClient


def get_linkedin_client(request: Request) -> LinkedInClient:
    return request.app.state.linkedin_client
