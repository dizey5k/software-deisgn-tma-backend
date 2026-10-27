import asyncio
import hashlib
import json
import logging
import threading
import time
from google import genai
from google.genai import types

from app.core.prompts import get_task_parsing_prompt

logger = logging.getLogger(__name__)


class AIUnavailableError(RuntimeError):
    """Raised when the external AI provider cannot process a request."""


class AIService:
    """Service for interacting with Gemini, with bounded local caching and failure control."""

    _cache: dict[str, tuple[float, dict]] = {}
    _lock = threading.Lock()
    _failure_count = 0
    _opened_until = 0.0
    _failure_threshold = 3
    _cooldown_seconds = 30
    _cache_ttl_seconds = 60
    _cache_limit = 512

    @staticmethod
    def _ensure_available() -> None:
        with AIService._lock:
            if AIService._opened_until > time.monotonic():
                raise AIUnavailableError("AI provider circuit is open")
            AIService._opened_until = 0.0

    @staticmethod
    def _record_failure() -> None:
        with AIService._lock:
            AIService._failure_count += 1
            if AIService._failure_count >= AIService._failure_threshold:
                AIService._opened_until = time.monotonic() + AIService._cooldown_seconds

    @staticmethod
    def _record_success() -> None:
        with AIService._lock:
            AIService._failure_count = 0
            AIService._opened_until = 0.0

    @staticmethod
    def parse_task_text(
        gemini_client: genai.Client,
        message: str,
        chat_context: str | None = None,
        cache_scope: str = "",
    ) -> dict:
        """
        format prompt, send request Gemini and gives parsed JSON.
        """
        resolved_context = chat_context or "Общий чат"
        cache_key = hashlib.sha256(
            f"{cache_scope}\0{resolved_context}\0{message}".encode("utf-8")
        ).hexdigest()

        with AIService._lock:
            cached = AIService._cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                return cached[1].copy()
            if cached:
                AIService._cache.pop(cache_key, None)

        AIService._ensure_available()

        # Получаем готовый промпт со свежим временем
        formatted_prompt = get_task_parsing_prompt(
            chat_context=resolved_context,
            message_text=message
        )

        try:
            response = gemini_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=formatted_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            if not response.text:
                raise ValueError("model Gemini returned empty response")

            parsed = json.loads(response.text)
            if not isinstance(parsed, dict):
                raise ValueError("model Gemini returned a non-object response")
        except Exception as exc:
            AIService._record_failure()
            raise AIUnavailableError("AI provider request failed") from exc

        AIService._record_success()
        with AIService._lock:
            if len(AIService._cache) >= AIService._cache_limit:
                AIService._cache.clear()
            AIService._cache[cache_key] = (
                time.monotonic() + AIService._cache_ttl_seconds,
                parsed.copy(),
            )

        return parsed

    @staticmethod
    def transcribe_audio(gemini_client: genai.Client, audio_path: str) -> str:
        AIService._ensure_available()
        uploaded_audio = None
        try:
            uploaded_audio = gemini_client.files.upload(file=audio_path)
            response = gemini_client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[
                    uploaded_audio,
                    "Распознай речь на этом аудио и напиши только текст, без вводных слов и комментариев.",
                ],
            )
            if not response.text or not response.text.strip():
                raise ValueError("model Gemini returned empty transcription")
            transcription = response.text.strip()
        except Exception as exc:
            AIService._record_failure()
            raise AIUnavailableError("AI provider request failed") from exc
        finally:
            if uploaded_audio is not None:
                try:
                    gemini_client.files.delete(name=uploaded_audio.name)
                except Exception:
                    logger.exception("Could not delete the temporary Gemini audio file")

        AIService._record_success()
        return transcription

    @staticmethod
    async def parse_task_text_async(
        gemini_client: genai.Client,
        message: str,
        chat_context: str | None = None,
        cache_scope: str = "",
    ) -> dict:
        return await asyncio.to_thread(
            AIService.parse_task_text,
            gemini_client,
            message,
            chat_context,
            cache_scope,
        )