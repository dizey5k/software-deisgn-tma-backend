import os
import httpx
from google import genai
from google.genai import types
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator
from app.core.database import async_session_maker

load_dotenv()

def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY has not been set in the environment variables. Please check your .env file.")
    
    proxy_url = os.getenv("PROXY_URL")
    
    if proxy_url:
        transport = httpx.HTTPTransport(proxy=proxy_url)
        async_transport = httpx.AsyncHTTPTransport(proxy=proxy_url)
        
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                client_args={"transport": transport},
                async_client_args={"transport": async_transport},
            )
        )

    return genai.Client(api_key=api_key)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an asynchronous SQLAlchemy session."""
    async with async_session_maker() as session:
        yield session