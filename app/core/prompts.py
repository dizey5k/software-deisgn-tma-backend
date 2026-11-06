from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_task_parsing_prompt(
    chat_context: str,
    message_text: str,
    timezone_name: str = "Europe/Moscow",
) -> str:
    try:
        user_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        user_timezone = ZoneInfo("Europe/Moscow")
        timezone_name = "Europe/Moscow"
    current_time = datetime.now(user_timezone)
    utc_offset = current_time.strftime("%z")
    utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}"
    current_local_time = current_time.strftime("%Y-%m-%d %H:%M")

    return f"""
Ты — умный ассистент-парсер. Твоя задача — извлечь данные из текста и вернуть строго JSON.

ВАЖНО — КОНТЕКСТ ВРЕМЕНИ:
Текущая дата и время пользователя: {current_local_time} (часовой пояс {timezone_name}, смещение UTC{utc_offset}).
Интерпретируй относительные даты и время в часовом поясе пользователя.
Все дедлайны возвращай в ISO 8601 со смещением пользователя ({utc_offset}).
Если время явно указано, сохраняй именно его; не заменяй его текущим временем и не конвертируй в UTC.
Если дата понятна, но время не указано, ставь конец этого локального дня: "YYYY-MM-DDT23:59:59{utc_offset}".
Не придумывай дату или время, которых пользователь не указал и которые нельзя однозначно вывести из текста.

Контекст источника (чат/отправитель): {chat_context}

Правила категоризации:
- "WORK": обычные рабочие задачи, рутина, текущие поручения (не относятся к созданию актива).
- "PROF": задачи, которые относятся непосредственно к развитию актива, стратегическим проектам.
- "STUDY": учеба, курсы, саморазвитие.
- "PERSONAL": личные дела, дом, здоровье.

Структура JSON:
{{
    "title": "Краткое название задачи",
    "description"(строка или null): подробное описание, дополнительные детали или подзадачи, если пользователь их указал
    "deadline": "Дата в формате ISO8601 с локальным смещением {utc_offset} или null",
    "priority": "HIGH, MEDIUM или LOW (по умолчанию MEDIUM)",
    "category": "WORK, PROF, STUDY или PERSONAL"
}}

Текст сообщения: "{message_text}"
"""