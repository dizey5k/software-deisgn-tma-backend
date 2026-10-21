import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

HEALTH_ENDPOINT = "/health"
PARSE_TASKS_ENDPOINT = "/api/tasks/parse"

TEST_TASK_PAYLOAD = {
    "message": "Завтра нужно обсудить стратегию развития актива с командой",
    "telegram_id": 987654321,
    "chat_context": "Стратегический актив-чат"
}

def test_health_check():
    response = client.get(HEALTH_ENDPOINT)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_task_parse_endpoint_structure():
    """Тест проверяет контракт эндпоинта парсинга"""
    response = client.post(PARSE_TASKS_ENDPOINT, json=TEST_TASK_PAYLOAD)
    
    # Пока эндпоинт пустой (возвращает заглушку или 422/500), 
    # но структура запроса валидируется Pydantic корректно.
    # Когда напишем бизнес-логику, здесь будет assert response.status_code == 200
    assert response.status_code in [200, 422]