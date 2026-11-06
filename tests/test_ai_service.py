from types import SimpleNamespace

import pytest

from app.core.prompts import get_task_parsing_prompt
from app.services.ai_service import AIService, AIUnavailableError


@pytest.fixture(autouse=True)
def reset_ai_service_state():
    with AIService._lock:
        AIService._cache.clear()
        AIService._failure_count = 0
        AIService._opened_until = 0.0
    yield
    with AIService._lock:
        AIService._cache.clear()
        AIService._failure_count = 0
        AIService._opened_until = 0.0


class FakeModels:
    def __init__(self, response_text=None, error=None):
        self.response_text = response_text
        self.error = error
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.response_text)


def test_ai_results_are_cached_per_user_scope():
    models = FakeModels('{"title":"Prepare report"}')
    client = SimpleNamespace(models=models)

    first = AIService.parse_task_text(client, "Prepare a report", cache_scope="user-a")
    second = AIService.parse_task_text(client, "Prepare a report", cache_scope="user-a")

    assert first == second == {"title": "Prepare report"}
    assert models.calls == 1


def test_ai_cache_is_not_shared_between_users():
    models = FakeModels('{"title":"Prepare report"}')
    client = SimpleNamespace(models=models)

    AIService.parse_task_text(client, "Prepare a report", cache_scope="user-a")
    AIService.parse_task_text(client, "Prepare a report", cache_scope="user-b")

    assert models.calls == 2


def test_task_prompt_uses_requested_timezone_offset():
    prompt = get_task_parsing_prompt(
        chat_context="Telegram private chat",
        message_text="завтра в 15:00 созвон",
        timezone_name="Europe/Berlin",
    )

    assert "Europe/Berlin" in prompt
    assert "UTC+01:00" in prompt or "UTC+02:00" in prompt
    assert "не конвертируй в UTC" in prompt


def test_ai_circuit_breaker_opens_after_repeated_failures():
    models = FakeModels(error=RuntimeError("provider offline"))
    client = SimpleNamespace(models=models)

    for _ in range(AIService._failure_threshold):
        with pytest.raises(AIUnavailableError):
            AIService.parse_task_text(client, "new task")

    with pytest.raises(AIUnavailableError, match="circuit is open"):
        AIService.parse_task_text(client, "another task")

    assert models.calls == AIService._failure_threshold
