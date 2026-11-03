import asyncio
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

from app.bot.handlers import _parse_task_command
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

    async def execute(self, statement):
        self.statement = statement
        if isinstance(statement, Insert):
            values = statement.compile().params
            membership = (values["user_id"], values["chat_id"])
            if membership in self.memberships:
                return FakeResult()
            self.memberships.add(membership)
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


def test_join_group_is_idempotent():
    user = type("UserRef", (), {"id": uuid4()})()
    session = FakeSession()

    first_join = asyncio.run(join_group(session, user, -100123))
    second_join = asyncio.run(join_group(session, user, -100123))

    assert first_join is True
    assert second_join is False
    assert session.commits == 2


def test_task_list_query_includes_only_shared_tasks_from_joined_chats():
    user = type("UserRef", (), {"id": uuid4()})()
    session = FakeSession()

    asyncio.run(get_user_tasks(session, user))

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "group_memberships" in sql
    assert "tasks.is_shared IS true" in sql
    assert "tasks.user_id =" in sql
