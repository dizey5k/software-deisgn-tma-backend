from datetime import datetime, timezone
from typing import List
import uuid
from google import genai
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select

from app.models.models import GroupMembership, Task, User
from app.schemas.task import TaskParseRequest, TaskUpdateRequest
from app.services.ai_service import AIService


def _visible_tasks_filter(current_user: User):
    return or_(
        Task.user_id == current_user.id,
        and_(
            Task.is_shared.is_(True),
            Task.source_chat_id.in_(
                select(GroupMembership.chat_id).where(
                    GroupMembership.user_id == current_user.id
                )
            ),
        ),
    )


async def parse_and_save_task(
    db: AsyncSession, 
    gemini_client: genai.Client, 
    request: TaskParseRequest,
    current_user: User,
    source_chat_id: int | None = None,
    is_shared: bool = False,
) -> Task:
    ai_data = await AIService.parse_task_text_async(
        gemini_client=gemini_client,
        message=request.message,
        chat_context=request.chat_context,
        cache_scope=(
            f"group:{source_chat_id}" if is_shared else str(current_user.id)
        ),
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
    new_task.source_chat_id = source_chat_id
    new_task.is_shared = is_shared

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task

async def get_user_tasks(
    db: AsyncSession, 
    current_user: User,
    category: str | None = None,
    status_filter: str | None = None
) -> List[Task]:
    stmt = select(Task).where(_visible_tasks_filter(current_user))
    
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
    stmt = select(Task).where(
        Task.id == task_id,
        _visible_tasks_filter(current_user),
    )
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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
    stmt = select(Task).where(
        Task.id == task_id,
        _visible_tasks_filter(current_user),
    )
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или у вас нет к ней доступа"
        )
        
    await db.delete(task)
    await db.commit()