import os
import tempfile
import logging
import asyncio
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core.database import async_session_maker
from app.services.task_service import parse_and_save_task
from app.schemas.task import TaskParseRequest
from app.core.dependencies import get_gemini_client
from app.services.user_service import (
    get_or_create_user,
    get_user_by_username,
    join_group,
)
from app.services.ai_service import AIService, AIUnavailableError

router = Router()
logger = logging.getLogger(__name__)


def _mini_app_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Открыть групповые задачи",
                    url=os.getenv(
                        "TELEGRAM_MINI_APP_URL",
                        "https://t.me/TM_dizZy_bot?startapp=group",
                    ),
                )
            ]
        ]
    )


def _format_created_task(
    task,
    heading: str = "Задача успешно создана!",
    timezone_name: str = "Europe/Moscow",
) -> str:
    deadline = "Без дедлайна"
    if task.deadline:
        try:
            user_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            user_timezone = ZoneInfo("Europe/Moscow")
        task_deadline = task.deadline
        if task_deadline.tzinfo is None:
            task_deadline = task_deadline.replace(tzinfo=timezone.utc)
        deadline = task_deadline.astimezone(user_timezone).strftime("%d.%m.%Y %H:%M")
    return (
        f"✅ {heading}\n\n"
        f"📌 Название: {task.title}\n"
        f"📝 Описание: {task.description or '—'}\n"
        f"📂 Категория: {task.category}\n"
        f"⚡ Приоритет: {task.priority}\n"
        f"⏰ Дедлайн: {deadline}"
    )


def _parse_task_command(args: str | None) -> tuple[str | None, str] | None:
    command_text = (args or "").strip()
    if not command_text:
        return None

    parts = command_text.split(maxsplit=1)
    username = parts[0]
    if username.startswith("@"):
        return (username, parts[1]) if len(parts) == 2 else None

    return None, command_text


@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message):
    """Greeting and autoregister"""
    async with async_session_maker() as db:
        await get_or_create_user(
            db=db, 
            telegram_id=message.from_user.id, 
            username=message.from_user.username
        )
    
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n"
        "Я твой умный таск-менеджер. Просто напиши мне задачу в свободной форме "
        "(например: *'Завтра в 15:00 созвон с инвестором'*), и я сам её структурирую и сохраню!"
    )


@router.message(Command("task"))
async def handle_group_task(message: Message, command: CommandObject):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("Команда /task доступна в групповых чатах.")
        return

    parsed_command = _parse_task_command(command.args)
    if parsed_command is None:
        await message.answer(
            "Формат: /task текст задачи (общая для группы) "
            "или /task @username текст задачи (личная)."
        )
        return

    recipient_username, task_text = parsed_command
    is_personal = recipient_username is not None
    async with async_session_maker() as db:
        if is_personal:
            task_owner = await get_user_by_username(db, recipient_username)
            if task_owner is None:
                await message.answer(
                    f"Не нашёл {recipient_username}. Попросите адресата открыть бота командой /start, "
                    "затем повторите назначение."
                )
                return
        else:
            task_owner = await get_or_create_user(
                db,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
            )
            await join_group(
                db,
                task_owner,
                message.chat.id,
                message.chat.title,
            )

        processing_msg = await message.answer(
            "⏳ Создаю задачу..."
        )
        try:
            task = await parse_and_save_task(
                db=db,
                gemini_client=get_gemini_client(),
                request=TaskParseRequest(
                    message=task_text,
                    telegram_id=task_owner.telegram_id,
                    chat_context=f"Telegram group chat {message.chat.id}",
                ),
                current_user=task_owner,
                source_chat_id=message.chat.id,
                is_shared=not is_personal,
            )
        except AIUnavailableError:
            await processing_msg.edit_text(
                "⚠️ ИИ-ассистент временно недоступен. Попробуйте позже."
            )
            return
        except Exception:
            logger.exception("Could not create a delegated task")
            await processing_msg.edit_text("Не удалось создать задачу. Попробуйте позже.")
            return

    heading = (
        f"Задача назначена @{task_owner.username or recipient_username.lstrip('@')}."
        if is_personal
        else "Совместная задача создана для участников группы."
    )
    await processing_msg.edit_text(
        _format_created_task(task, heading, task_owner.timezone_name),
        reply_markup=_mini_app_keyboard() if not is_personal else None,
    )


@router.message(Command("join"))
async def handle_group_join(message: Message):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("Команда /join доступна только в групповых чатах.")
        return

    async with async_session_maker() as db:
        user = await get_or_create_user(
            db,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        joined = await join_group(
            db,
            user,
            message.chat.id,
            message.chat.title,
        )

    await message.answer(
        f"Готово: теперь вы видите совместные задачи чата "
        f"«{message.chat.title or 'Групповой чат'}».",
        reply_markup=_mini_app_keyboard(),
    )


@router.message(Command("timezone"))
async def handle_timezone(message: Message, command: CommandObject):
    if message.chat.type != "private":
        await message.answer("Настроить часовой пояс можно в личном чате с ботом.")
        return

    timezone_name = (command.args or "").strip()
    async with async_session_maker() as db:
        user = await get_or_create_user(
            db,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        if not timezone_name:
            await message.answer(
                f"Текущий часовой пояс: {user.timezone_name}\n"
                "Указать часовой пояс можно так: /timezone Europe/Moscow"
            )
            return

        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            await message.answer(
                "Неизвестный часовой пояс. Пример: /timezone Europe/Moscow"
            )
            return

        user.timezone_name = timezone_name
        await db.commit()

    await message.answer(f"Часовой пояс установлен: {timezone_name}")


@router.message((F.text & ~F.text.startswith("/")) | (F.caption & ~F.caption.startswith("/")))
async def handle_task_text(message: Message):
    """Handle text and media captions — parse with AI and save as task"""
    if message.chat.type != "private":
        return

    telegram_id = message.from_user.id
    
    task_text = message.text or message.caption
    
    processing_msg = await message.answer("⏳ Обрабатываю задачу с помощью ИИ...")

    try:
        async with async_session_maker() as db:
            user = await get_or_create_user(
                db=db, 
                telegram_id=telegram_id, 
                username=message.from_user.username
            )
            
            gemini_client = get_gemini_client()
            
            request_data = TaskParseRequest(
                message=task_text,
                telegram_id=telegram_id,
                chat_context=f"Telegram Chat ({message.chat.type})"
            )
            
            task = await parse_and_save_task(
                db=db,
                gemini_client=gemini_client,
                request=request_data,
                current_user=user
            )

        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=_format_created_task(task, timezone_name=user.timezone_name),
        )
    except AIUnavailableError:
        await processing_msg.edit_text(
            "⚠️ ИИ-ассистент временно недоступен. Попробуйте позже."
        )
    except Exception:
        logger.exception("Could not create a task from a Telegram message")
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text="Не удалось создать задачу. Попробуйте позже.",
        )

@router.message(F.voice)
async def handle_voice_message(message: Message):
    """Handle voice messages — convert to text via Gemini, then save as task"""
    if message.chat.type != "private":
        return

    telegram_id = message.from_user.id
    processing_msg = await message.answer("🎤 Слушаю и расшифровываю голосовое...")
    temp_path = None

    try:
        file_id = message.voice.file_id
        file = await message.bot.get_file(file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_path = temp_file.name

        await message.bot.download_file(file.file_path, destination=temp_path)
        gemini_client = get_gemini_client()

        recognized_text = await asyncio.to_thread(
            AIService.transcribe_audio,
            gemini_client,
            temp_path,
        )

        if not recognized_text:
            await processing_msg.edit_text("❌ Не удалось разобрать слова. Попробуй сказать четче.")
            return

        await processing_msg.edit_text(
            f"🗣 Распознано: {recognized_text}\n\n⏳ Обрабатываю задачу..."
        )

        async with async_session_maker() as db:
            user = await get_or_create_user(
                db=db, 
                telegram_id=telegram_id, 
                username=message.from_user.username
            )
            
            request_data = TaskParseRequest(
                message=recognized_text,
                telegram_id=telegram_id,
                chat_context=f"Telegram Voice Chat"
            )
            
            task = await parse_and_save_task(
                db=db,
                gemini_client=gemini_client,
                request=request_data,
                current_user=user
            )

        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"{_format_created_task(task, 'Голосовая задача успешно создана!', user.timezone_name)}\n\n"
            f"🗣 Оригинал: {recognized_text}",
        )

    except AIUnavailableError:
        await processing_msg.edit_text(
            "⚠️ ИИ-ассистент временно недоступен. Попробуйте позже."
        )
    except Exception:
        logger.exception("Could not process a Telegram voice message")
        await processing_msg.edit_text("Не удалось обработать голосовое сообщение.")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)