import calendar
from datetime import date, datetime, timezone

from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Task, User
from app.schemas.analytics import (
    BurndownPoint,
    CategoryWorkload,
    MonthlyAnalyticsResponse,
    TeamBurndown,
)


def _month_window(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _build_burndown(
    year: int,
    month: int,
    created_counts: dict[int, int],
    completed_counts: dict[int, int],
) -> list[BurndownPoint]:
    running_created = 0
    running_completed = 0
    points = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        running_created += created_counts.get(day, 0)
        running_completed += completed_counts.get(day, 0)
        points.append(
            BurndownPoint(
                date=date(year, month, day),
                created_count=created_counts.get(day, 0),
                completed_count=completed_counts.get(day, 0),
                remaining_count=max(running_created - running_completed, 0),
            )
        )
    return points


def _day_counts(rows) -> dict[int, int]:
    return {int(day): int(count) for day, count in rows}


async def _group_burndown(
    db: AsyncSession,
    chat_ids: list[int],
    year: int,
    month: int,
    start: datetime,
    end: datetime,
) -> list[TeamBurndown]:
    if not chat_ids:
        return []

    created_result = await db.execute(
        select(
            Task.source_chat_id,
            extract("day", Task.created_at),
            func.count(Task.id),
        )
        .where(
            Task.source_chat_id.in_(chat_ids),
            Task.created_at >= start,
            Task.created_at < end,
        )
        .group_by(Task.source_chat_id, extract("day", Task.created_at))
    )
    completed_result = await db.execute(
        select(
            Task.source_chat_id,
            extract("day", Task.completed_at),
            func.count(Task.id),
        )
        .where(
            Task.source_chat_id.in_(chat_ids),
            Task.created_at >= start,
            Task.created_at < end,
            Task.status == "DONE",
            Task.completed_at >= start,
            Task.completed_at < end,
        )
        .group_by(Task.source_chat_id, extract("day", Task.completed_at))
    )

    created_by_chat: dict[int, dict[int, int]] = {chat_id: {} for chat_id in chat_ids}
    completed_by_chat: dict[int, dict[int, int]] = {chat_id: {} for chat_id in chat_ids}
    for chat_id, day, count in created_result:
        created_by_chat[chat_id][int(day)] = int(count)
    for chat_id, day, count in completed_result:
        completed_by_chat[chat_id][int(day)] = int(count)

    return [
        TeamBurndown(
            chat_id=str(chat_id),
            points=_build_burndown(
                year,
                month,
                created_by_chat[chat_id],
                completed_by_chat[chat_id],
            ),
        )
        for chat_id in sorted(chat_ids)
    ]


async def get_monthly_analytics(
    db: AsyncSession,
    current_user: User,
    year: int,
    month: int,
) -> MonthlyAnalyticsResponse:
    start, end = _month_window(year, month)
    completed_result = await db.execute(
        select(
            func.count(Task.id),
            func.count(case((Task.deadline.is_not(None), Task.id))),
            func.count(
                case(
                    (
                        and_(
                            Task.deadline.is_not(None),
                            Task.completed_at <= Task.deadline,
                        ),
                        Task.id,
                    )
                )
            ),
        ).where(
            Task.user_id == current_user.id,
            Task.status == "DONE",
            Task.completed_at >= start,
            Task.completed_at < end,
        )
    )
    completed_count, with_deadline_count, on_time_count = completed_result.one()
    completed_count = int(completed_count or 0)
    with_deadline_count = int(with_deadline_count or 0)
    on_time_count = int(on_time_count or 0)

    overdue_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == current_user.id,
            Task.status != "DONE",
            Task.deadline.is_not(None),
            Task.deadline < datetime.now(timezone.utc),
        )
    )
    overdue_count = int(overdue_result.scalar_one() or 0)

    category_result = await db.execute(
        select(func.coalesce(Task.category, "UNCATEGORIZED"), func.count(Task.id))
        .where(
            Task.user_id == current_user.id,
            Task.created_at >= start,
            Task.created_at < end,
        )
        .group_by(Task.category)
        .order_by(Task.category)
    )
    category_workload = [
        CategoryWorkload(category=category, task_count=int(count))
        for category, count in category_result
    ]

    created_result = await db.execute(
        select(extract("day", Task.created_at), func.count(Task.id))
        .where(
            Task.user_id == current_user.id,
            Task.created_at >= start,
            Task.created_at < end,
        )
        .group_by(extract("day", Task.created_at))
    )
    completed_daily_result = await db.execute(
        select(extract("day", Task.completed_at), func.count(Task.id))
        .where(
            Task.user_id == current_user.id,
            Task.created_at >= start,
            Task.created_at < end,
            Task.status == "DONE",
            Task.completed_at >= start,
            Task.completed_at < end,
        )
        .group_by(extract("day", Task.completed_at))
    )
    burndown = _build_burndown(
        year,
        month,
        _day_counts(created_result),
        _day_counts(completed_daily_result),
    )

    chat_result = await db.execute(
        select(Task.source_chat_id)
        .where(
            Task.user_id == current_user.id,
            Task.source_chat_id.is_not(None),
            Task.source_chat_id < 0,
        )
        .distinct()
    )
    team_burndown = await _group_burndown(
        db,
        [int(chat_id) for chat_id in chat_result.scalars()],
        year,
        month,
        start,
        end,
    )

    return MonthlyAnalyticsResponse(
        year=year,
        month=month,
        completed_count=completed_count,
        completed_with_deadline_count=with_deadline_count,
        on_time_completed_count=on_time_count,
        on_time_rate_percent=(
            round(on_time_count * 100 / with_deadline_count, 1)
            if with_deadline_count
            else 0.0
        ),
        overdue_count=overdue_count,
        category_workload=category_workload,
        burndown=burndown,
        team_burndown=team_burndown,
    )
