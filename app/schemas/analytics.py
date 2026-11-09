from datetime import date
from pydantic import BaseModel


class CategoryWorkload(BaseModel):
    category: str
    task_count: int


class BurndownPoint(BaseModel):
    date: date
    created_count: int
    completed_count: int
    remaining_count: int


class TeamBurndown(BaseModel):
    chat_id: str
    chat_title: str | None = None
    points: list[BurndownPoint]


class MonthlyAnalyticsResponse(BaseModel):
    year: int
    month: int
    completed_count: int
    completed_with_deadline_count: int
    on_time_completed_count: int
    on_time_rate_percent: float
    overdue_count: int
    category_workload: list[CategoryWorkload]
    burndown: list[BurndownPoint]
    team_burndown: list[TeamBurndown]
