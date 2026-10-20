import os
import json
from datetime import datetime
import pytest
from google import genai
from google.genai import types
from dotenv import load_dotenv

from app.core.prompts import TASK_PARSER_PROMPT

@pytest.fixture(scope="module")
def gemini_client():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.fail("GEMINI_API_KEY не найден в .env файле")

    # setting up proxy for google ai studio
    os.environ['HTTP_PROXY'] = 'socks5://127.0.0.1:10808'
    os.environ['HTTPS_PROXY'] = 'socks5://127.0.0.1:10808'
        
    return genai.Client(api_key=api_key)

def test_gemini_json_parsing(gemini_client):
    current_date = datetime.now().strftime("%Y-%m-%d")

    test_message = "Блин, забыл совсем, завтра в 14:00 созвон с командой разрабов, надо подготовить отчет"

    formatted_prompt = TASK_PARSER_PROMPT.format(
        current_date=current_date,
        chat_context="Обычный рабочий чат",
        message_text=test_message
    )
    
    response = gemini_client.models.generate_content(
        model='gemini-3.6-flash',
        contents=formatted_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    # 1. check for response
    assert response.text is not None, "Модель вернула пустой ответ"
    
    # 2. check for valid json
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        pytest.fail(f"Ответ модели не является валидным JSON. Ответ: {response.text}")
        
    # 3. check expected keys
    expected_keys = {"title", "deadline", "priority", "category"}
    assert expected_keys.issubset(data.keys()), f"В JSON отсутствуют нужные ключи. Получено: {data.keys()}"
    
    # 4. check logic: ai understand, call with devs - work
    assert data["category"] == "WORK", f"Ожидалась категория WORK, получено: {data['category']}"

    print("\nДинамическая дата:", current_date)
    print("\nСпарсенные данные:", json.dumps(data, indent=2, ensure_ascii=False))