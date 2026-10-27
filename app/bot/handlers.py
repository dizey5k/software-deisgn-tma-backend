import os
import tempfile
import logging
import asyncio

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.database import async_session_maker
from app.services.task_service import parse_and_save_task
from app.schemas.task import TaskParseRequest
from app.core.dependencies import get_gemini_client
from app.services.user_service import get_or_create_user, get_user_by_username
from app.services.ai_service import AIService, AIUnavailableError

router = Router()
logger = logging.getLogger(__name__)


def _format_created_task(task, heading: str = "Задача успешно создана!") -> str:
    deadline = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Без дедлайна"
    return (
        f"✅ {heading}\n\n"
        f"📌 Название: {task.title}\n"
        f"📝 Описание: {task.description or '—'}\n"
        f"📂 Категория: {task.category}\n"
        f"⚡ Приоритет: {task.priority}\n"
        f"⏰ Дедлайн: {deadline}"
    )

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

    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2 or not args[0].startswith("@"):
        await message.answer("Формат команды: /task @username текст задачи")
        return

    recipient_username, task_text = args
    async with async_session_maker() as db:
        recipient = await get_user_by_username(db, recipient_username)
        if recipient is None:
            await message.answer(
                f"Не нашёл {recipient_username}. Попросите адресата открыть бота командой /start, "
                "затем повторите назначение."
            )
            return

        processing_msg = await message.answer(
            f"⏳ Создаю задачу для {recipient_username}..."
        )
        try:
            task = await parse_and_save_task(
                db=db,
                gemini_client=get_gemini_client(),
                request=TaskParseRequest(
                    message=task_text,
                    telegram_id=recipient.telegram_id,
                    chat_context=f"Telegram group chat {message.chat.id}",
                ),
                current_user=recipient,
                source_chat_id=message.chat.id,
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

    await processing_msg.edit_text(
        _format_created_task(task, f"Задача назначена @{recipient.username or recipient_username.lstrip('@')}.")
    )


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
            text=_format_created_task(task),
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
            text=f"{_format_created_task(task, 'Голосовая задача успешно создана!')}\n\n"
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