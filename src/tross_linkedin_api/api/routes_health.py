"""Minimal liveness route; dependency readiness remains a later milestone."""

from fastapi import APIRouter


router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live", "service": "tross-linkedin-profile-api"}
