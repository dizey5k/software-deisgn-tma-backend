import asyncio
from datetime import datetime, timedelta, timezone
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.tasks import router as tasks_router
from app.api.google_calendar import router as google_calendar_router
from app.api.health import router as health_router
from app.bot.dispatcher import bot, dp
from app.bot.handlers import router as bot_router
from app.core.database import async_session_maker
from app.models.models import Task

load_dotenv()
dp.include_router(bot_router)

scheduler = AsyncIOScheduler(timezone=timezone.utc)

async def check_upcoming_deadlines():
    """background task: finds deadlines within the next hour and sends reminders to users via Telegram bot."""
    now = datetime.now(timezone.utc)
    one_hour_later = now + timedelta(hours=1)
    
    async with async_session_maker() as db:
        stmt = select(Task).options(selectinload(Task.user)).where(
            Task.deadline != None,
            Task.deadline <= one_hour_later,
            Task.deadline > now,
            Task.status != "DONE",
            Task.reminder_sent == False
        )
        result = await db.execute(stmt)
        tasks_to_remind = result.scalars().all()
        
        for task in tasks_to_remind:
            try:
                await bot.send_message(
                    chat_id=task.user.telegram_id,
                    text=(
                        f"⏰ **Напоминание!**\n\n"
                        f"Задача **{task.title}** должна быть выполнена меньше чем через час!\n"
                        f"Категория: `{task.category}`"
                    ),
                    parse_mode="Markdown"
                )
                task.reminder_sent = True
                await db.commit()
            except Exception as e:
                error_msg = f"Ошибка отправки напоминания для задачи {task.id}: {e}"
                print(error_msg)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))
    
    scheduler.add_job(check_upcoming_deadlines, 'interval', minutes=1)
    scheduler.start()
    print("Scheduler started!")
    
    yield
    
    scheduler.shutdown()
    await bot.session.close()

app = FastAPI(
    title="TMA Backend API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
allow_origins=[
        "https://tma-dizzzy.space",
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc),
            "path": request.url.path
        }
    )

app.include_router(tasks_router, prefix="/api")
app.include_router(google_calendar_router, prefix="/api")
app.include_router(health_router, prefix="/api")