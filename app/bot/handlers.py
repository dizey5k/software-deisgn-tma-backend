import os
import tempfile

from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai

from app.core.database import async_session_maker
from app.services.task_service import parse_and_save_task
from app.schemas.task import TaskParseRequest
from app.core.dependencies import get_gemini_client
from app.services.user_service import get_or_create_user

router = Router()

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

@router.message((F.text & ~F.text.startswith("/")) | (F.caption & ~F.caption.startswith("/")))
async def handle_task_text(message: Message):
    """Handle text and media captions — parse with AI and save as task"""
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

        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Без дедлайна"
        
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=(
                "✅ **Задача успешно создана!**\n\n"
                f"📌 **Название:** {task.title}\n"
                f"📝 **Описание:** {task.description}\n"
                f"📂 **Категория:** `{task.category}`\n"
                f"⚡ **Приоритет:** `{task.priority}`\n"
                f"⏰ **Дедлайн:** {deadline_str}"
            ),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"❌ Ошибка при создании задачи: `{str(e)}`",
            parse_mode="Markdown"
        )

@router.message(F.voice)
async def handle_voice_message(message: Message):
    """Handle voice messages — convert to text via Gemini, then save as task"""
    telegram_id = message.from_user.id
    processing_msg = await message.answer("🎤 Слушаю и расшифровываю голосовое...")

    try:
        file_id = message.voice.file_id
        file = await message.bot.get_file(file_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_path = temp_file.name
            
        await message.bot.download_file(file.file_path, destination=temp_path)
        
        gemini_client = get_gemini_client()
        
        uploaded_audio = gemini_client.files.upload(file=temp_path)
        
        prompt = "Распознай речь на этом аудио и напиши только текст, без вводных слов и комментариев."
        response = gemini_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[uploaded_audio, prompt]
        )
        
        recognized_text = response.text.strip()
        
        os.remove(temp_path)
        gemini_client.files.delete(name=uploaded_audio.name)
        
        if not recognized_text:
            await processing_msg.edit_text("❌ Не удалось разобрать слова. Попробуй сказать четче.")
            return
            
        await processing_msg.edit_text(f"🗣 **Распознано:** _{recognized_text}_\n\n⏳ Обрабатываю задачу...")

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

        deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "Без дедлайна"
        
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=(
                "✅ **Голосовая задача успешно создана!**\n\n"
                f"📌 **Название:** {task.title}\n"
                f"📂 **Категория:** `{task.category}`\n"
                f"⚡ **Приоритет:** `{task.priority}`\n"
                f"⏰ **Дедлайн:** {deadline_str}\n\n"
                f"🗣 _Оригинал: {recognized_text}_"
            ),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=f"❌ Ошибка при обработке голосового: `{str(e)}`",
            parse_mode="Markdown"
        )