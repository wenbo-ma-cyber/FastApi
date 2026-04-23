from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.hotspot import AIHotspotService, HotspotServiceError
from app.models import AIHotspotSummaryResponse

router = APIRouter()


def _get_hotspot_service(request: Request) -> AIHotspotService:
    return request.app.state.ai_hotspot_service


@router.get("/scrape-ai-hotspot", response_model=AIHotspotSummaryResponse)
def scrape_ai_hotspot(request: Request) -> AIHotspotSummaryResponse:
    try:
        return _get_hotspot_service(request).scrape_ai_hotspot()
    except HotspotServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
