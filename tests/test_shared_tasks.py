import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

from app.bot.handlers import (
    _format_created_task,
    _mini_app_keyboard,
    _parse_task_command,
)
from app.services.task_service import get_user_tasks
from app.services.user_service import join_group


class FakeResult:
    def __init__(self, rowcount=0):
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return []


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.statement = None
        self.memberships = set()
        self.chat_titles = {}

    async def execute(self, statement):
        self.statement = statement
        if isinstance(statement, Insert):
            values = statement.compile().params
            membership = (values["user_id"], values["chat_id"])
            self.memberships.add(membership)
            if values["chat_title"] is not None:
                self.chat_titles[membership] = values["chat_title"]
            return FakeResult(rowcount=1)
        return FakeResult()

    async def commit(self):
        self.commits += 1


def test_task_command_distinguishes_shared_and_personal_tasks():
    assert _parse_task_command("Подготовить отчет") == (None, "Подготовить отчет")
    assert _parse_task_command("@oleg Подготовить отчет") == (
        "@oleg",
        "Подготовить отчет",
    )
    assert _parse_task_command("@oleg") is None
    assert _parse_task_command("  ") is None


def test_group_task_keyboard_opens_group_tasks_in_mini_app(monkeypatch):
    monkeypatch.delenv("TELEGRAM_MINI_APP_URL", raising=False)
    button = _mini_app_keyboard().inline_keyboard[0][0]

    assert button.text == "📋 Открыть групповые задачи"
    assert button.url == "https://t.me/TM_dizZy_bot?startapp=group"


def test_bot_formats_deadline_in_users_timezone():
    task = type(
        "TaskRef",
        (),
        {
            "deadline": datetime(2026, 11, 11, 15, tzinfo=timezone.utc),
            "title": "Project",
            "description": None,
            "category": "WORK",
            "priority": "HIGH",
        },
    )()

    text = _format_created_task(task, timezone_name="Europe/Moscow")

    assert "Дедлайн: 11.11.2026 18:00" in text


def test_join_group_is_idempotent():
    user = type("UserRef", (), {"id": uuid4()})()
    session = FakeSession()

    first_join = asyncio.run(join_group(session, user, -100123, "Team tasks"))
    second_join = asyncio.run(join_group(session, user, -100123, "Renamed team"))

    assert first_join is True
    assert second_join is True
    assert session.commits == 2
    assert session.chat_titles[(user.id, -100123)] == "Renamed team"


def test_task_list_query_includes_only_shared_tasks_from_joined_chats():
    user = type("UserRef", (), {"id": uuid4()})()
    session = FakeSession()

    asyncio.run(get_user_tasks(session, user))

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "group_memberships" in sql
    assert "tasks.is_shared IS true" in sql
    assert "tasks.user_id =" in sql
