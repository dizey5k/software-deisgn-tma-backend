from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import get_current_user
from app.models.models import User
from app.schemas.analytics import MonthlyAnalyticsResponse
from app.services.analytics_service import get_monthly_analytics

router = APIRouter(prefix="/analytics", tags=["Analytics (Аналитика)"])


@router.get("/monthly", response_model=MonthlyAnalyticsResponse)
async def monthly_analytics(
    year: int = Query(default_factory=lambda: datetime.now(timezone.utc).year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: datetime.now(timezone.utc).month, ge=1, le=12),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> MonthlyAnalyticsResponse:
    return await get_monthly_analytics(db, current_user, year, month)
