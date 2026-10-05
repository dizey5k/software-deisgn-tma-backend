from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_async_session

router = APIRouter(tags=["Health Check"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_async_session)):
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    overall_status = "healthy" if db_status == "healthy" else "degraded"

    return {
        "status": overall_status,
        "services": {
            "backend": "healthy",
            "database": db_status,
        }
    }