import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.services.analytics_service import _build_burndown, get_monthly_analytics


class FakeResult:
    def __init__(self, rows=(), one=None, scalar=None):
        self.rows = rows
        self._one = one
        self._scalar = scalar

    def one(self):
        return self._one

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self):
        self.results = [
            FakeResult(one=(2, 1, 1)),
            FakeResult(scalar=1),
            FakeResult(rows=[("WORK", 2)]),
            FakeResult(scalar=3),
            FakeResult(rows=[(1, 2), (2, 1)]),
            FakeResult(rows=[(2, 1)]),
            FakeResult(rows=[]),
        ]

    async def execute(self, _statement):
        return self.results.pop(0)


def test_burndown_includes_opening_backlog_and_subtracts_completions():
    points = _build_burndown(
        2026,
        2,
        created_counts={2: 2},
        completed_counts={2: 1},
        opening_count=3,
    )

    assert points[0].remaining_count == 3
    assert points[1].remaining_count == 4
    assert points[1].created_count == 2
    assert points[1].completed_count == 1


def test_monthly_analytics_calculates_rates_and_daily_burndown():
    user = SimpleNamespace(id=uuid4())

    result = asyncio.run(get_monthly_analytics(FakeSession(), user, 2026, 2))

    assert result.completed_count == 2
    assert result.completed_with_deadline_count == 1
    assert result.on_time_completed_count == 1
    assert result.on_time_rate_percent == 100
    assert result.overdue_count == 1
    assert result.category_workload[0].task_count == 2
    assert result.burndown[0].date == date(2026, 2, 1)
    assert result.burndown[0].remaining_count == 5
    assert result.burndown[1].remaining_count == 5
    assert len(result.burndown) == 28
    assert result.team_burndown == []
