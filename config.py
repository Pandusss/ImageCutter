"""
Конфигурационный файл с настройками бота
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# Параметры обработки изображений
EMOJI_SIZE = 100  # Размер эмодзи в пикселях (требование Telegram)
MIN_FRAGMENT_SIZE = 100  # Минимальный размер фрагмента до масштабирования
