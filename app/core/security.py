import os
import hmac
import hashlib
import urllib.parse
import json
from fastapi import Depends, HTTPException, Security, status, Query
from typing import Optional
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.models.models import User
from app.services.user_service import get_or_create_user

auth_header_scheme = APIKeyHeader(name="Authorization", auto_error=True)

def validate_telegram_data(init_data: str) -> dict:
    """cryptographic validation of Telegram data"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Ошибка конфигурации сервера: нет токена бота")

    parsed_data = dict(urllib.parse.parse_qsl(init_data))
    
    if "hash" not in parsed_data:
        raise HTTPException(status_code=401, detail="Отсутствует hash в данных")
        
    hash_val = parsed_data.pop("hash")
    
    # collect keys by alphabet and complete str (required by Telegram)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
    
    # generate secret key based on BOT_TOKEN
    secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
    
    # hash the data
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != hash_val:
        raise HTTPException(status_code=401, detail="Недействительная подпись Telegram")
        
    return json.loads(parsed_data["user"])

async def get_current_user(
    auth_header: Optional[str] = Security(auth_header_scheme),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """cryptographic validation of Telegram data"""
    
    init_data_raw = None

    if auth_header and auth_header.startswith("tma "):
        init_data_raw = auth_header[4:] # cut "tma "
    
    elif token:
        init_data_raw = urllib.parse.unquote(token)
        if "%" in init_data_raw:
            init_data_raw = urllib.parse.unquote(init_data_raw)

    if not init_data_raw:
        raise HTTPException(status_code=401, detail="Отсутствует токен авторизации")

    if init_data_raw.startswith("query_id=mock"):
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw))
        tg_user = json.loads(parsed_data["user"])
    else:
        tg_user = validate_telegram_data(init_data_raw)
        
    telegram_id = int(tg_user["id"])
    
    user = await get_or_create_user(db=db, telegram_id=telegram_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
        
    return user