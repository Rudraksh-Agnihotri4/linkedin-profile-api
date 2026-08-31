"""FastAPI application factory scaffold."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the route-free application scaffold."""
    return FastAPI(
        title="Tross LinkedIn Profile API",
        version="0.1.0",
    )
