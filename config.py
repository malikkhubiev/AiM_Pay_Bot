import os
from dotenv import load_dotenv

load_dotenv()  # Загружает переменные окружения из файла .env

API_TOKEN = os.getenv("API_TOKEN")
SERVER_URL = os.getenv("SERVER_URL")
MAHIN_URL = os.getenv("MAHIN_URL")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_database.db")  # SQLite для локального использования, PostgreSQL для деплоя

GROUP_NAME = os.getenv("GROUP_NAME")  # Убедитесь, что здесь используется @
GROUP_ID = os.getenv("GROUP_ID")

COURSE_AMOUNT = os.getenv("COURSE_AMOUNT")
REFERRAL_AMOUNT = os.getenv("REFERRAL_AMOUNT")

# Параметры логирования
LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO")  # Уровень логирования

# YooKassa configuration
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

TAX_INFO_IMG_URL = os.getenv("TAX_INFO_IMG_URL")
EARN_NEW_CLIENTS_VIDEO_URL = os.getenv("EARN_NEW_CLIENTS_VIDEO_URL")
START_VIDEO_URL = os.getenv("START_VIDEO_URL")
REPORT_VIDEO_URL = os.getenv("REPORT_VIDEO_URL")
REFERRAL_VIDEO_URL = os.getenv("REFERRAL_VIDEO_URL")

PORT = os.getenv("PORT")