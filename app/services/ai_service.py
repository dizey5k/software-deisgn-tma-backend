import json
from google import genai
from google.genai import types

from app.core.prompts import get_task_parsing_prompt

class AIService:
    """service for interacting with Gemini"""

    @staticmethod
    def parse_task_text(gemini_client: genai.Client, message: str, chat_context: str | None = None) -> dict:
        """
        format prompt, send request Gemini and gives parsed JSON.
        """
        resolved_context = chat_context or "Общий чат"

        # Получаем готовый промпт со свежим временем
        formatted_prompt = get_task_parsing_prompt(
            chat_context=resolved_context,
            message_text=message
        )

        response = gemini_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=formatted_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        if not response.text:
            raise ValueError("model Gemini returned empty response")

        try:
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            raise ValueError(f"failed to parse from model response: {response.text}") from e