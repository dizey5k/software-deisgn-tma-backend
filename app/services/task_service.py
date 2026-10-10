from datetime import datetime, timezone
from typing import List
import uuid
from google import genai
from fastapi import HTTPException
from grpc import Status
from pyparsing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Task, User
from app.schemas.task import TaskParseRequest, TaskUpdateRequest
from app.services.ai_service import AIService
from app.services.user_service import get_or_create_user

async def parse_and_save_task(
    db: AsyncSession, 
    gemini_client: genai.Client, 
    request: TaskParseRequest,
    current_user: User
) -> Task:
    ai_data = AIService.parse_task_text(
        gemini_client=gemini_client,
        message=request.message,
        chat_context=request.chat_context
    )

    deadline_val = None
    if ai_data.get("deadline"):
        try:
            deadline_val = datetime.fromisoformat(ai_data["deadline"])
            if deadline_val.tzinfo is None:
                deadline_val = deadline_val.replace(tzinfo=timezone.utc)
        except ValueError:
            deadline_val = None

    new_task = Task(
        user_id=current_user.id,
        title=ai_data.get("title", request.message),
        description=ai_data.get("description"),
        deadline=deadline_val,
        priority=ai_data.get("priority", "MEDIUM"),
        category=ai_data.get("category", "WORK"),
        status="TODO"
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task

async def get_user_tasks(
    db: AsyncSession, 
    current_user: User,
    category: Optional[str] = None,
    status_filter: Optional[str] = None
) -> List[Task]:
    stmt = select(Task).where(Task.user_id == current_user.id)
    
    if category:
        stmt = stmt.where(Task.category == category)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_task(
    db: AsyncSession, 
    task_id: uuid.UUID, 
    update_data: TaskUpdateRequest,
    current_user: User
) -> Task:
    stmt = select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(
            status_code=Status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или у вас нет к ней доступа"
        )
        
    update_dict = update_data.model_dump(exclude_unset=True)

    if "status" in update_dict:
        new_status = update_dict["status"]
        if new_status == "DONE" and task.status != "DONE":
            task.completed_at = datetime.now(timezone.utc)
        elif new_status != "DONE" and task.status == "DONE":
            task.completed_at = None
    
    for key, value in update_dict.items():
        setattr(task, key, value)
        
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(
    db: AsyncSession, 
    task_id: uuid.UUID,
    current_user: User
) -> None:
    stmt = select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(
            status_code=Status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или у вас нет к ней доступа"
        )
        
    await db.delete(task)
    await db.commit()