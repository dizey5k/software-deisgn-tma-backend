import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai

from app.core.security import get_current_user
from app.models.models import Task, User
from app.schemas.task import TaskCreateRequest, TaskParseRequest, TaskResponse, TaskUpdateRequest
from app.core.database import get_async_session
from app.core.dependencies import get_gemini_client
from app.services.task_service import (
    parse_and_save_task, 
    get_user_tasks,
    update_task, 
    delete_task
)
from app.services.calendar_service import (
    create_calendar_event,
    update_calendar_event
)

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks (Задачи)"]
)

@router.post("/parse", response_model=TaskResponse, summary="Парсинг задачи")
async def parse_and_create_task(
    request: TaskParseRequest,
    db: AsyncSession = Depends(get_async_session),
    gemini_client: genai.Client = Depends(get_gemini_client),
    current_user: User = Depends(get_current_user)
):
    new_task = await parse_and_save_task(db=db, gemini_client=gemini_client, request=request, current_user=current_user)

    if new_task.deadline:
        try:
            event_id = create_calendar_event(
                user=current_user,
                task_title=new_task.title,
                task_description=getattr(new_task, 'description', None),
                deadline_iso=new_task.deadline.isoformat()
            )
            if event_id:
                new_task.calendar_event_id = event_id
                await db.commit()
                await db.refresh(new_task)
        except Exception as e:
            print(f"⚠️ Ошибка при создании события в Google Календаре (AI): {e}")

    return new_task

@router.get("/", response_model=List[TaskResponse], summary="Список задач пользователя")
async def list_tasks(
    response: Response,
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    return await get_user_tasks(db=db, current_user=current_user, category=category, status_filter=status_filter)

@router.post("/", response_model=TaskResponse, summary="Создать задачу вручную")
async def create_task_manual(
    body: TaskCreateRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    new_task = Task(
        user_id=current_user.id,
        title=body.title,
        description=getattr(body, 'description', None),
        deadline=body.deadline,
        priority=body.priority,
        category=body.category,
        status="TODO"
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    if new_task.deadline:
        try:
            event_id = create_calendar_event(
                user=current_user,
                task_title=new_task.title,
                task_description=new_task.description,
                deadline_iso=new_task.deadline.isoformat()
            )
            if event_id:
                new_task.calendar_event_id = event_id
                await db.commit()
                await db.refresh(new_task)
        except Exception as e:
            print(f"⚠️ Ошибка при создании события в Google Календаре (Manual): {e}")

    return new_task

@router.patch("/{task_id}", response_model=TaskResponse, summary="Обновить задачу")
async def edit_task(
    task_id: uuid.UUID,
    body: TaskUpdateRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    updated_task = await update_task(db=db, task_id=task_id, update_data=body, current_user=current_user)
    
    if updated_task.deadline:
        try:
            if updated_task.calendar_event_id:
                update_calendar_event(
                    event_id=updated_task.calendar_event_id,
                    user=current_user,
                    task_title=updated_task.title,
                    task_description=updated_task.description,
                    deadline_iso=updated_task.deadline.isoformat()
                )
            else:
                event_id = create_calendar_event(
                    user=current_user,
                    task_title=updated_task.title,
                    task_description=updated_task.description,
                    deadline_iso=updated_task.deadline.isoformat()
                )
                if event_id:
                    updated_task.calendar_event_id = event_id
                    await db.commit()
                    await db.refresh(updated_task)
        except Exception as e:
            print(f"⚠️ Ошибка обновления Календаря: {e}")

    return updated_task

@router.delete("/{task_id}", summary="Удалить задачу")
async def remove_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    await delete_task(db=db, task_id=task_id, current_user=current_user)
    return {"status": "success", "message": "Задача успешно удалена"}