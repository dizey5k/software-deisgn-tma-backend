# app/schemas/task.py

import uuid
from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

# Enums for task attributes
class TaskPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class TaskCategory(str, Enum):
    WORK = "WORK"
    PROF = "PROF"
    STUDY = "STUDY"
    PERSONAL = "PERSONAL"

class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"

# incoming request schema
class TaskParseRequest(BaseModel):
    message: str = Field(
        ..., 
        title="Текст сообщения", 
        description="Сырой текст, из которого нейросеть извлечет задачу",
        json_schema_extra={"example": "Напомни завтра в 14:00 созвониться с командой"}
    )
    telegram_id: Optional[int] = Field(None, description="ID пользователя в Telegram")
    chat_context: Optional[str] = Field(None, description="Контекст чата или источника (например, 'Актив-чат')")

# outgoing response schema
class TaskResponse(BaseModel):
    id: uuid.UUID = Field(..., description="Уникальный ID задачи")
    title: str = Field(..., description="Название задачи")
    description: Optional[str] = Field(None, description="Описание задачи")
    deadline: Optional[datetime] = Field(None, description="Дедлайн задачи")
    priority: TaskPriority = Field(..., description="Приоритет")
    category: TaskCategory = Field(..., description="Категория")
    status: TaskStatus = Field(..., description="Текущий статус")
    created_at: datetime = Field(..., description="Дата создания")
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, description="Название задачи")
    description: Optional[str] = Field(None, description="Описание задачи")
    category: Optional[str] = Field(None, description="Категория")
    priority: Optional[str] = Field(None, description="Приоритет")
    status: Optional[str] = Field(None, description="Статус задачи")
    deadline: Optional[datetime] = Field(None, description="Дедлайн задачи")

class TaskCreateRequest(BaseModel):
    title: str = Field(..., description="Название задачи")
    description: Optional[str] = Field(None, description="Описание задачи (необязательно)")
    category: str = Field(default="WORK", description="Категория: WORK, STUDY, PERSONAL")
    priority: str = Field(default="MEDIUM", description="Приоритет: LOW, MEDIUM, HIGH")
    deadline: Optional[datetime] = Field(None, description="Дедлайн задачи в формате ISO 8601")