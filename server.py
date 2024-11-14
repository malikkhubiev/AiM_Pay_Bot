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
    YOO_KASSA_SHOP_ID
)
import os
import aiohttp
import uvicorn
from database import get_db, create_payout, get_user, mark_payout_as_notified, create_referral

load_dotenv()

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
    user = get_user(db, request.telegram_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    # Создание платежа в YooKassa
    try:
        payment_response = await create_payment(request.amount, request.description, request.telegram_id)
        return payment_response
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


async def create_payment(amount: float, description: str, telegram_id: str):
    """Создание платежа в YooKassa."""
    url = "https://api.yookassa.ru/v3/payments"
    headers = {
        "Authorization": f"Bearer {YOOKASSA_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    payment_data = {
        "amount": {
            "value": f"{amount:.2f}",  # Форматируем сумму с двумя знаками после запятой
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://web.telegram.org/a/#7859098027"
        },
        "capture": True,
        "description": description,
        "metadata": {
            "telegram_id": telegram_id  # Добавляем ID пользователя для дальнейшей идентификации
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payment_data) as response:
            if response.status == 200:
                payment_response = await response.json()
                confirmation_url = payment_response.get('confirmation', {}).get('confirmation_url')
                if confirmation_url:
                    return {
                        'confirmation': {
                            'confirmation_url': confirmation_url  # Возвращаем ссылку на страницу подтверждения
                        }
                    }
                else:
                    raise HTTPException(status_code=400, detail="No confirmation URL found")
            else:
                raise HTTPException(status_code=response.status, detail=f"Failed to create payment: {await response.text()}")

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
                return {"message": "Payment processed and user notified successfully"}
            else:
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