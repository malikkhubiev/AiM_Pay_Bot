import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import sessionmaker
from config import (
    API_TOKEN,
    COURSE_AMOUNT,
    REFERRAL_AMOUNT,
    GROUP_ID,
    TAX_INFO_IMG_URL,
    EARN_NEW_CLIENTS_VIDEO_URL,
    START_VIDEO_URL,
    REPORT_VIDEO_URL,
    REFERRAL_VIDEO_URL
)
from database import (
    engine,
    User,
)
import requests

API_URL = "https://aim-pay-bot.onrender.com"  # Адрес API FastAPI

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Создание сессии базы данных
Session = sessionmaker(bind=engine)

# Логирование
logging.basicConfig(level=logging.INFO)

# Главное меню с кнопками
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    telegram_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name

    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            await message.answer(f"Привет, {username}! Я тебя знаю. Ты участник AiM course!")
        else:
            referrer_id = message.get_args()
            new_user = User(telegram_id=telegram_id, username=username, referrer_id=referrer_id if referrer_id else None)
            session.add(new_user)
            session.commit()
            await message.answer(f"Добро пожаловать, {username}! Ты успешно зарегистрирован.")
            logging.info(f"Пользователь {username} зарегистрирован {'с реферальной ссылкой' if referrer_id else 'без реферальной ссылки'}.")
    
    # Основное меню с кнопками
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Оплатить курс", callback_data='pay_course'),
    )

    # Проверка оплаты через выплаты или рефералы
    if user and user.referral_count > 0:  # Проверка наличия хотя бы одного реферала
        keyboard.add(InlineKeyboardButton("Заработать на новых клиентах", callback_data='earn_new_clients'))
    else:
        keyboard.add(InlineKeyboardButton("Заработать на новых клиентах (нужно оплатить курс)", callback_data='earn_new_clients_disabled'))

    await bot.send_video(
        chat_id=message.chat.id,
        video=START_VIDEO_URL,
        caption="Добро пожаловать! Здесь Вы можете оплатить курс и заработать на привлечении новых клиентов.",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data == 'pay_course')
async def process_pay_course(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await callback_query.message.answer("Здесь будет информация о платеже. Нажмите /pay для оплаты.")


@dp.callback_query_handler(lambda c: c.data == 'earn_new_clients')
async def process_earn_new_clients(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Получить реферальную ссылку", callback_data='get_referral'),
        InlineKeyboardButton("Сформировать отчёт о заработке", callback_data='generate_report'),
        InlineKeyboardButton("Налоги", callback_data='tax_info')
    )

    # Отправка изображения
    await bot.send_video(
        chat_id=callback_query.message.chat.id,
        video=EARN_NEW_CLIENTS_VIDEO_URL,
        caption="Курс стоит 6000 рублей.\nЗа каждого привлечённого вами клиента вы заработаете 2000 рублей.\nПосле 3-х клиентов курс становится для Вас бесплатным.\nНачиная с 4-го клиента, вы начинаете зарабатывать на продвижении It-образования."
    )
    await bot.send_message(
        callback_query.message.chat.id,
        "Отправляйте рекламные сообщения в тематические чаты по изучению программирования, а также в телеграм-группы различных российских вузов и вы можете выйти на прибыль в 100.000 рублей после привлечения 50 клиентов.",
        reply_markup=keyboard
    )


# Обработка кнопки "Получить реферальную ссылку"
@dp.callback_query_handler(lambda c: c.data == 'get_referral')
async def process_get_referral(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await send_referral_link(callback_query.message, callback_query.from_user.id)


# Обработка кнопки "Сформировать отчёт о заработке"
@dp.callback_query_handler(lambda c: c.data == 'generate_report')
async def process_generate_report(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await generate_report(callback_query.message, callback_query.from_user.id)


# Обработка кнопки "Налоги"
@dp.callback_query_handler(lambda c: c.data == 'tax_info')
async def process_tax_info(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
 
    # Отправка изображения
    await bot.send_photo(
        chat_id=callback_query.message.chat.id,
        photo=TAX_INFO_IMG_URL,
        caption="Реферальные выплаты могут облагаться налогом. Рекомендуем зарегистрироваться как самозанятый."
    )

    # Отправка HTML-сообщения с инструкцией
    info_text = """
<b>Как зарегистрироваться и выбрать вид деятельности для уплаты налогов:</b>

1. Информацию о способах регистрации и не только вы можете найти на официальном сайте <a href="https://npd.nalog.ru/app/">npd.nalog.ru/app</a>.
   
2. При выборе вида деятельности рекомендуем указать: «Реферальные выплаты» или «Услуги».

<i>Пока вы платите налоги, вы защищаете себя и делаете реферальные выплаты законными.</i>
"""
    await callback_query.message.answer(info_text, parse_mode=ParseMode.HTML)


@dp.message_handler(commands=['pay'])
async def process_payment(message: types.Message):
    telegram_id = str(message.from_user.id)
    amount = COURSE_AMOUNT  # Сумма платежа
    description = "Оплата курса"
    
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("Сначала нажмите /start для регистрации.")
            return

        # Проверка, что пользователю уже не была начислена выплата
        if user.payment_status == 'paid':
            await message.answer("Вы уже оплатили курс.")
            return

        # Отправка запроса на сервер для создания платежа
        payment_data = {
            "amount": amount,
            "description": description,
            "telegram_id": telegram_id
        }
        response = requests.post(API_URL + "/pay", json=payment_data)  # URL вашего FastAPI сервера
        
        if response.status_code == 200:
            payment_response = response.json()
            payment_url = payment_response.get('confirmation', {}).get('confirmation_url')
            
            if payment_url:
                # Отправляем пользователю ссылку для перехода на страницу оплаты
                await message.answer(f"Для оплаты курса, перейдите по ссылке: {payment_url}")
            else:
                await message.answer("Ошибка при создании ссылки для оплаты.")
        else:
            await message.answer("Ошибка при обработке платежа.")

async def simulate_payment():
    await asyncio.sleep(1)
    return True


@dp.message_handler(commands=['report'])
async def generate_report(message: types.Message, telegram_id):
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("Используй команду /start для регистрации.")
            return

        report = f"<b>Отчёт для {user.username}:</b>\n\n"
        report += f"Привлечённые пользователи: {user.referral_count}\n"
        payout_per_referral = REFERRAL_AMOUNT
        total_payout = user.referral_count * payout_per_referral
        report += f"Общая сумма потенциальных выплат: {total_payout} руб.\n\n"

        await bot.send_video(
            chat_id=message.chat.id,
            video=REPORT_VIDEO_URL,
            caption=report,
            parse_mode=ParseMode.HTML
        )


@dp.message_handler(commands=['referral'])
async def send_referral_link(message: types.Message, telegram_id):
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("Используй команду /start для регистрации.")
            return

        referral_link = f"https://t.me/{bot.username}?start={telegram_id}"
        await message.answer(f"Твоя реферальная ссылка: {referral_link}")


if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
