from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import requests
from config import (
    REFERRAL_AMOUNT,
    YOOKASSA_SECRET_KEY,
    MAHIN_URL,
    YOOKASSA_SHOP_ID
)

from yookassa import Payment, Configuration
import logging
import os
import aiohttp
import uvicorn
from database import get_db, create_payout, get_user, mark_payout_as_notified, create_referral

load_dotenv()

print("YOOKASSA_SHOP_ID:", os.getenv("YOOKASSA_SHOP_ID"))
print("YOOKASSA_SECRET_KEY:", os.getenv("YOOKASSA_SECRET_KEY"))

# Настройка идентификатора магазина и секретного ключа
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Настроим логирование
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Логируем, чтобы проверить, что переменные установлены
logger.info("Account ID: %s", Configuration.account_id)
logger.info("Secret Key: %s", "SET" if Configuration.secret_key else "NOT SET")

# FastAPI application
app = FastAPI()

class UserRegisterRequest(BaseModel):
    telegram_id: str
    username: str
    referrer_id: str

class PaymentRequest(BaseModel):
    amount: float
    description: str
    telegram_id: str

@app.post("/pay")
async def pay(request: PaymentRequest, db: Session = Depends(get_db)):
    """Инициализация платежа."""
    logger.info("Инициализация платежа для пользователя с Telegram ID: %s", request.telegram_id)

    user = get_user(db, request.telegram_id)
    if not user:
        logger.warning("Пользователь с Telegram ID %s не найден.", request.telegram_id)
        raise HTTPException(status_code=400, detail="User not found")

    # Создание платежа в YooKassa
    try:
        payment_response = await create_payment(request.amount, request.description, request.telegram_id)
        logger.info("Платеж успешно создан для пользователя с Telegram ID %s", request.telegram_id)
        return payment_response
    except HTTPException as e:
        logger.error("Ошибка при создании платежа для пользователя с Telegram ID %s: %s", request.telegram_id, e.detail)
        raise HTTPException(status_code=e.status_code, detail=e.detail)

async def create_payment(amount: float, description: str, telegram_id: str):
    """Создание платежа в YooKassa с использованием yookassa SDK."""
    payment_data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"tg://resolve?domain=AiM_Pay_Bot"
        },
        "capture": True,
        "description": description,
        "metadata": {
            "telegram_id": telegram_id
        }
    }
    
    try:
        logger.info("Отправка запроса на создание платежа для пользователя с Telegram ID: %s", telegram_id)
        payment = Payment.create(payment_data)  # Создание платежа через yookassa SDK
        confirmation_url = payment.confirmation.confirmation_url
        if confirmation_url:
            logger.info("Платеж успешно создан. Confirmation URL: %s", confirmation_url)
            return {
                'confirmation': {
                    'confirmation_url': confirmation_url  # Возвращаем ссылку на страницу подтверждения
                }
            }
        else:
            logger.error("Ошибка: Confirmation URL не найден в ответе от YooKassa.")
            raise HTTPException(status_code=400, detail="No confirmation URL found")
    except Exception as e:
        logger.error("Ошибка при создании платежа: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create payment: {str(e)}")
    
@app.post("/payment_notification")
async def payment_notification(request: Request, db: Session = Depends(get_db)):
    """Обработка уведомления о платеже от YooKassa."""
    data = await request.json()
    payment_id = data.get("id")
    status = data.get("status")
    user_telegram_id = data.get("metadata", {}).get("telegram_id")

    if status == "succeeded" and user_telegram_id:
        user = get_user(db, user_telegram_id)
        if user:
            # Обновление статуса оплаты пользователя
            user.payment_status = "paid"
            db.commit()

            # Выплата рефералу, если он существует
            if user.referrer_id:
                referrer = get_user(db, user.referrer_id)
                if referrer:
                    create_payout(db, referrer.id, REFERRAL_AMOUNT)  # Выплата за реферала

            # Создание записи в таблице Referral
            create_referral(db, user.referrer_id, user.id)

            # Обновление статуса выплаты
            mark_payout_as_notified(db, payment_id)

            # Отправка уведомления в mahin.py для оповещения пользователя
            notify_url = f"{MAHIN_URL}/notify_user"
            notification_data = {
                "telegram_id": user_telegram_id,
                "message": "Поздравляем! Ваш платёж прошёл успешно, вы оплатили курс! 🎉"
            }
            response = requests.post(notify_url, json=notification_data)

            if response.status_code == 200:
                logger.info("Пользователь с Telegram ID %s успешно уведомлен через бота.", user_telegram_id)
                return {"message": "Payment processed and user notified successfully"}
            else:
                logger.error("Ошибка при отправке уведомления пользователю через бота.")
                raise HTTPException(status_code=500, detail="Failed to notify user through bot")

    raise HTTPException(status_code=400, detail="Payment not processed")

# Database session dependency
@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    request.state.db = get_db()
    response = await call_next(request)
    return response

@app.api_route("/", methods=["GET", "HEAD"])
async def payment_notification(request: Request):
    return JSONResponse(content={"message": "Супер"}, status_code=200, headers={"Content-Type": "application/json; charset=utf-8"})

async def run_fastapi():
    port = int(os.getenv("PORT", 8000))  # Порт будет извлечен из окружения или 8000 по умолчанию
    uvicorn.run(app, host="0.0.0.0", port=port)