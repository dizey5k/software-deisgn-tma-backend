import os
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

proxy_url = os.getenv("PROXY_URL")

if proxy_url:
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), session=session)
else:
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

dp = Dispatcher()