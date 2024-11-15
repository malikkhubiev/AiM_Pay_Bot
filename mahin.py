import logging
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import NoResultFound
from datetime import datetime
from aiohttp import web
import nest_asyncio
from config import (
    API_TOKEN,
    COURSE_AMOUNT,
    REFERRAL_AMOUNT,
    SERVER_URL,
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
    Referral,
    Payout,
)
import requests
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Создание сессии базы данных
Session = sessionmaker(bind=engine)

# Установим базовый уровень логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Применяем nest_asyncio для повторного использования цикла событий
nest_asyncio.apply()

# Определение веб-сервера
def web_server():
    async def handle(request):
        # Проверка типа запроса
        response_data = {"message": "pong"}
        return web.json_response(response_data)
    
    async def notify_user(request):
        data = await request.json()
        telegram_id = data.get("telegram_id")
        message_text = data.get("message")

        # Отправляем сообщение пользователю через Telegram
        if telegram_id and message_text:
            await bot.send_message(chat_id=telegram_id, text=message_text)
            return web.json_response({"status": "notification sent"}, status=200)
        return web.json_response({"error": "Invalid data"}, status=400)

    app = web.Application()
    app.router.add_route("HEAD", "/", handle)
    app.router.add_route("GET", "/", handle)
    app.router.add_post("/notify_user", notify_user)
    return app

async def on_start_polling():
    # Настройка веб-сервера с использованием aiohttp
    app = web.AppRunner(web_server())
    await app.setup()

    # Привязка адреса и порта
    bind_address = "0.0.0.0"
    PORT = int(os.getenv("PORT", 8080))
    site = web.TCPSite(app, bind_address, PORT)
    await site.start()

    logging.info(f"Веб-сервер запущен на порту {PORT}")

    # Запуск бота с ожиданием завершения
    await executor.start_polling(dp, skip_updates=True)

# Главное меню с кнопками
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    telegram_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name

    with Session() as session:
        # Проверка, зарегистрирован ли пользователь
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            await message.answer(f"Привет, {username}! Я тебя знаю. Ты участник AiM course!")
        else:
            # Регистрируем нового пользователя и добавляем реферера, если он есть
            referrer_id = message.get_args()
            new_user = User(
                telegram_id=telegram_id,
                username=username,
                referrer_id=referrer_id if referrer_id else None
            )
            session.add(new_user)
            session.commit()
            await message.answer(f"Добро пожаловать, {username}! Ты успешно зарегистрирован.")
            logging.info(f"Пользователь {username} зарегистрирован {'с реферальной ссылкой' if referrer_id else 'без реферальной ссылки'}.")

    # Создаем основное меню с кнопками
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Оплатить курс", callback_data='pay_course'),
    )

    # Проверка, есть ли хотя бы один реферал у пользователя
    referral_exists = session.query(Referral).filter_by(referrer_id=user.id).first() if user else None
    keyboard.add(InlineKeyboardButton("Заработать на новых клиентах", callback_data='earn_new_clients'))
    # Включить позже, а сверху выключить
    # if referral_exists:
    #     # Кнопка для заработка на клиентах, если есть хотя бы один реферал
    #     keyboard.add(InlineKeyboardButton("Заработать на новых клиентах", callback_data='earn_new_clients'))
    # else:
    #     # Кнопка, если пользователь еще не оплатил курс
    #     keyboard.add(InlineKeyboardButton("Заработать на новых клиентах (нужно оплатить курс)", callback_data='earn_new_clients_disabled'))
    # Включить позже

    # Отправка видео с приветствием и меню
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
    amount = COURSE_AMOUNT
    description = "Оплата курса"
    
    logger.info("Начало обработки платежа для пользователя с Telegram ID: %s", telegram_id)
    
    with Session() as session:
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).one()
            logger.info("Пользователь найден в базе данных: %s", user)
        except NoResultFound:
            logger.warning("Пользователь не зарегистрирован, запрос /pay отклонён.")
            await message.answer("Сначала нажмите /start для регистрации.")
            return

        # Проверка, что у пользователя уже есть выплата с подтвержденным статусом
        existing_payout = session.query(Payout).filter_by(user_id=user.id, notified=False).first()
        # Включить позже
        # if existing_payout:
        #     logger.info("Пользователь с Telegram ID %s уже оплатил курс.", telegram_id)
        #     await message.answer("Вы уже оплатили курс.")
        #     return
        # Включить позже

        # Отправка запроса на сервер для создания платежа
        payment_data = {
            "amount": amount,
            "description": description,
            "telegram_id": telegram_id
        }
        
        try:
            logger.info("Отправка запроса на сервер для создания платежа. Данные: %s", payment_data)
            response = requests.post(SERVER_URL + "/pay", json=payment_data)
        except requests.RequestException as e:
            logger.error("Ошибка при отправке запроса на сервер: %s", e)
            await message.answer("Ошибка при обработке платежа.")
            return

        if response.status_code == 200:
            payment_response = response.json()
            payment_url = payment_response.get('confirmation', {}).get('confirmation_url')
            
            if payment_url:
                logger.info("Платёж успешно создан. Confirmation URL: %s", payment_url)
                # Создаем запись в таблице Payout с состоянием "ожидает уведомления"
                payout = Payout(user_id=user.id, amount=amount, created_at=datetime.utcnow(), notified=False)
                session.add(payout)
                session.commit()
                
                # Отправляем пользователю ссылку для перехода на страницу оплаты
                await message.answer(f"Для оплаты курса, перейдите по ссылке: {payment_url}")
            else:
                logger.error("Ошибка: Confirmation URL отсутствует в ответе сервера.")
                await message.answer("Ошибка при создании ссылки для оплаты.")
        else:
            logger.error("Ошибка при обработке платежа на сервере. Код ответа: %s, Текст ошибки: %s", response.status_code, response.text)
            await message.answer("Ошибка при обработке платежа.")

@dp.message_handler(commands=['report'])
async def generate_report(message: types.Message, telegram_id: str):
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("Используй команду /start для регистрации.")
            return

        # Подсчет рефералов для пользователя
        referral_count = session.query(Referral).filter_by(referrer_id=user.id).count()
        
        report = f"<b>Отчёт для {user.username}:</b>\n\n"
        report += f"Привлечённые пользователи: {referral_count}\n"
        
        # Подсчет общей суммы потенциальных выплат
        payout_per_referral = REFERRAL_AMOUNT
        total_payout = referral_count * payout_per_referral
        report += f"Общая сумма потенциальных выплат: {total_payout} руб.\n\n"

        await bot.send_video(
            chat_id=message.chat.id,
            video=REPORT_VIDEO_URL,
            caption=report,
            parse_mode=ParseMode.HTML
        )


@dp.message_handler(commands=['referral'])
async def send_referral_link(message: types.Message, telegram_id: str):
    with Session() as session:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await message.answer("Используй команду /start для регистрации.")
            return

        # Получение имени пользователя бота
        bot_username = (await bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={telegram_id}"
        await bot.send_video(
            chat_id=message.chat.id,
            video=REFERRAL_VIDEO_URL,
            caption=f"Отправляю тебе реферальную ссылку:\n{referral_link}\nЗарабатывай, продвигая It - образование."
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(on_start_polling())