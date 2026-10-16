import os
import jwt
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from app.core.database import get_async_session
from app.core.security import get_current_user
from app.models.models import User


from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/auth/google", tags=["Google Calendar"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_key_change_me")
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "https://www.googleapis.com/auth/calendar.events"

@router.get("/login")
def google_login(current_user: User = Depends(get_current_user)):
    """Генерируем ссылку для авторизации вручную без капризных Flow"""
    state_data = {"telegram_id": current_user.telegram_id}
    encoded_state = jwt.encode(state_data, SECRET_KEY, algorithm="HS256")

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": encoded_state
    }
    
    query_string = requests.compat.urlencode(params)
    authorization_url = f"{GOOGLE_AUTH_URL}?{query_string}"
    
    return {"url": authorization_url}

@router.get("/callback", response_class=HTMLResponse)
async def google_callback(
    request: Request,
    code: str, 
    state: str, 
    db: AsyncSession = Depends(get_async_session)
):
    """Меняем код на токены, сохраняем и показываем красивую HTML-страничку"""
    try:
        decoded_state = jwt.decode(state, SECRET_KEY, algorithms=["HS256"])
        telegram_id = decoded_state.get("telegram_id")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Недействительный state параметр")

    token_data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    response = requests.post(GOOGLE_TOKEN_URL, data=token_data)
    
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Ошибка получения токена от Google: {response.text}")

    tokens = response.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден в базе")

    user.google_access_token = access_token
    if refresh_token:
        user.google_refresh_token = refresh_token
        
    await db.commit()

    return templates.TemplateResponse(request, "google_success.html")