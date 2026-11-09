import calendar
from datetime import date, datetime, timezone

from sqlalchemy import and_, case, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GroupMembership, Task, User
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
    opening_count: int = 0,
) -> list[BurndownPoint]:
    remaining = opening_count
    points = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        remaining += created_counts.get(day, 0)
        remaining = max(remaining - completed_counts.get(day, 0), 0)
        points.append(
            BurndownPoint(
                date=date(year, month, day),
                created_count=created_counts.get(day, 0),
                completed_count=completed_counts.get(day, 0),
                remaining_count=remaining,
            )
        )
    return points


def _day_counts(rows) -> dict[int, int]:
    return {int(day): int(count) for day, count in rows}


async def _group_burndown(
    db: AsyncSession,
    chat_titles: dict[int, str | None],
    year: int,
    month: int,
    start: datetime,
    end: datetime,
) -> list[TeamBurndown]:
    chat_ids = list(chat_titles)
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
            Task.is_shared.is_(True),
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
            Task.is_shared.is_(True),
            Task.status == "DONE",
            Task.completed_at >= start,
            Task.completed_at < end,
        )
        .group_by(Task.source_chat_id, extract("day", Task.completed_at))
    )
    opening_result = await db.execute(
        select(Task.source_chat_id, func.count(Task.id))
        .where(
            Task.source_chat_id.in_(chat_ids),
            Task.is_shared.is_(True),
            Task.created_at < start,
            or_(Task.status != "DONE", Task.completed_at >= start),
        )
        .group_by(Task.source_chat_id)
    )

    created_by_chat: dict[int, dict[int, int]] = {chat_id: {} for chat_id in chat_ids}
    completed_by_chat: dict[int, dict[int, int]] = {chat_id: {} for chat_id in chat_ids}
    opening_by_chat = {chat_id: 0 for chat_id in chat_ids}
    for chat_id, count in opening_result:
        opening_by_chat[chat_id] = int(count)
    for chat_id, day, count in created_result:
        created_by_chat[chat_id][int(day)] = int(count)
    for chat_id, day, count in completed_result:
        completed_by_chat[chat_id][int(day)] = int(count)

    return [
        TeamBurndown(
            chat_id=str(chat_id),
            chat_title=chat_titles[chat_id],
            points=_build_burndown(
                year,
                month,
                created_by_chat[chat_id],
                completed_by_chat[chat_id],
                opening_by_chat[chat_id],
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

    opening_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == current_user.id,
            Task.is_shared.is_(False),
            Task.created_at < start,
            or_(Task.status != "DONE", Task.completed_at >= start),
        )
    )
    opening_count = int(opening_result.scalar_one() or 0)

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
        opening_count,
    )

    chat_result = await db.execute(
        select(
            GroupMembership.chat_id,
            func.max(GroupMembership.chat_title),
        )
        .where(
            GroupMembership.user_id == current_user.id
        )
        .group_by(GroupMembership.chat_id)
    )
    team_burndown = await _group_burndown(
        db,
        {
            int(chat_id): chat_title
            for chat_id, chat_title in chat_result
        },
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
