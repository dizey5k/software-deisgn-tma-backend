import os

from aiogram import Bot, Dispatcher

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

dp = Dispatcher()