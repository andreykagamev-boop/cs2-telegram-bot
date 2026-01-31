import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Константы
GAMES = {
    "cs2": {"name": "CS2", "slug": "csgo", "emoji": "🔫"},
    "dota2": {"name": "Dota 2", "slug": "dota-2", "emoji": "⚔️"}
}

class PandaScoreAPI:
    """Класс для работы с PandaScore API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def get_upcoming_matches(self, game_slug: str, limit: int = 10):
        """Получение предстоящих матчей"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{game_slug}/matches/upcoming"
            
            async with session.get(url, params={
                "per_page": limit,
                "sort": "scheduled_at",
                "page": 1
            }) as response:
                
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"API Error: {response.status} - {await response.text()}")
                    return []
                    
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_running_matches(self, game_slug: str):
        """Получение текущих матчей"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{game_slug}/matches/running"
            
            async with session.get(url, params={"per_page": 5}) as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            logger.error(f"Error getting running matches: {e}")
            return []
    
    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API клиента
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

def create_main_keyboard():
    """Создание основной клавиатуры"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 CS2 Матчи", callback_data="matches_cs2"),
            InlineKeyboardButton(text="⚔️ Dota 2 Матчи", callback_data="matches_dota2")
        ],
        [
            InlineKeyboardButton(text="🔴 CS2 Live", callback_data="live_cs2"),
            InlineKeyboardButton(text="🔴 Dota 2 Live", callback_data="live_dota2")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        ]
    ])
    return keyboard

def format_match(match: dict, game_name: str) -> str:
    """Форматирование информации о матче"""
    league = match.get("league", {}).get("name", "Неизвестная лига")
    series = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at")
    if scheduled_at:
        try:
            dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            time_str = dt.strftime("%d.%m.%Y %H:%M UTC")
            
            # Добавляем оставшееся время
            now = datetime.utcnow()
            if dt > now:
                time_diff = dt - now
                if time_diff.days > 0:
                    time_str += f" (через {time_diff.days} д.)"
                elif time_diff.seconds > 3600:
                    hours = time_diff.seconds // 3600
                    time_str += f" (через {hours} ч.)"
                else:
                    minutes = time_diff.seconds // 60
                    time_str += f" (через {minutes} мин.)"
        except:
            time_str = "Время неизвестно"
    else:
        time_str = "Время неизвестно"
    
    # Форматируем сообщение
    message = (
        f"<b>{game_name}</b>\n"
        f"🏆 <b>{league}</b>\n"
        f"{series}\n\n"
        f"⚔️ <b>{team1} vs {team2}</b>\n"
        f"🕐 {time_str}\n"
    )
    
    # Добавляем ссылку если есть
    match_url = match.get("official_stream_url") or match.get("live_url")
    if match_url:
        message += f"\n📺 <a href='{match_url}'>Смотреть</a>"
    
    return message

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = (
        "🎮 <b>Esports Matches Bot</b>\n\n"
        "Я помогу отслеживать матчи по CS2 и Dota 2!\n"
        "Используйте кнопки ниже для навигации.\n\n"
        "📊 <b>Доступные команды:</b>\n"
        "/cs2 - Матчи CS2\n"
        "/dota2 - Матчи Dota 2\n"
        "/live - Текущие матчи\n"
        "/help - Помощь"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """Матчи CS2"""
    await show_matches(message, "cs2")

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Матчи Dota 2"""
    await show_matches(message, "dota2")

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Текущие матчи"""
    await message.answer(
        "Выберите игру для просмотра текущих матчей:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔴 CS2 Live", callback_data="live_cs2"),
                InlineKeyboardButton(text="🔴 Dota 2 Live", callback_data="live_dota2")
            ]
        ])
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь"""
    help_text = (
        "🆘 <b>Помощь по боту</b>\n\n"
        "📊 <b>Команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/cs2 - Показать матчи CS2\n"
        "/dota2 - Показать матчи Dota 2\n"
        "/live - Текущие матчи (live)\n"
        "/help - Эта справка\n\n"
        "🔧 <b>Использование:</b>\n"
        "• Используйте кнопки под сообщениями\n"
        "• Бот обновляет данные в реальном времени\n"
        "• Для обновления нажмите '🔄 Обновить'\n\n"
        "📡 <b>Источник данных:</b> PandaScore API"
    )
    await message.answer(help_text, disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("matches_"))
async def handle_matches_callback(callback: types.CallbackQuery):
    """Обработчик кнопок с матчами"""
    game = callback.data.split("_")[1]  # cs2 или dota2
    await show_matches_callback(callback, game)

@dp.callback_query(F.data.startswith("live_"))
async def handle_live_callback(callback: types.CallbackQuery):
    """Обработчик кнопок с live матчами"""
    game = callback.data.split("_")[1]  # cs2 или dota2
    await show_live_matches(callback, game)

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновление главного меню"""
    await callback.message.edit_text(
        "🎮 <b>Esports Matches Bot</b>\n\n"
        "Выберите действие:",
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer("Меню обновлено!")

@dp.callback_query(F.data == "help")
async def handle_help_callback(callback: types.CallbackQuery):
    """Помощь через callback"""
    await cmd_help(callback.message)
    await callback.answer()

# ========== ФУНКЦИИ ПОКАЗА МАТЧЕЙ ==========

async def show_matches(message_or_callback, game: str):
    """Показать матчи для игры"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    
    if game not in GAMES:
        error_msg = "Игра не найдена"
        if is_callback:
            await message_or_callback.answer(error_msg)
        else:
            await message_or_callback.answer(error_msg)
        return
    
    game_info = GAMES[game]
    
    # Показываем "загрузку"
    if is_callback:
        await message_or_callback.message.edit_text(
            f"⏳ Загружаю матчи {game_info['emoji']} {game_info['name']}..."
        )
    else:
        msg = await message_or_callback.answer(
            f"⏳ Загружаю матчи {game_info['emoji']} {game_info['name']}..."
        )
    
    # Получаем матчи
    matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=5)
    
    if not matches:
        no_matches_text = f"📭 Нет предстоящих матчей по {game_info['name']}"
        if is_callback:
            await message_or_callback.message.edit_text(
                no_matches_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"matches_{game}")]
                ])
            )
        else:
            await msg.edit_text(no_matches_text)
        return
    
    # Отправляем каждый матч отдельным сообщением
    for i, match in enumerate(matches[:5]):
        match_text = format_match(match, game_info["name"])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"matches_{game}"),
                InlineKeyboardButton(text="🏠 Главная", callback_data="refresh")
            ]
        ])
        
        if i == 0 and is_callback:
            await message_or_callback.message.edit_text(
                match_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            if is_callback and i == 0:
                # Первое сообщение уже отредактировано
                continue
            await bot.send_message(
                chat_id=message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id,
                text=match_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
    
    if is_callback:
        await message_or_callback.answer("✅ Матчи загружены!")

async def show_matches_callback(callback: types.CallbackQuery, game: str):
    """Показать матчи через callback"""
    await show_matches(callback, game)

async def show_live_matches(callback: types.CallbackQuery, game: str):
    """Показать текущие матчи"""
    if game not in GAMES:
        await callback.answer("Игра не найдена")
        return
    
    game_info = GAMES[game]
    
    await callback.message.edit_text(
        f"⏳ Ищу текущие матчи {game_info['emoji']} {game_info['name']}..."
    )
    
    matches = await panda_api.get_running_matches(game_info["slug"])
    
    if not matches:
        await callback.message.edit_text(
            f"📭 Сейчас нет live матчей по {game_info['name']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"live_{game}")],
                [InlineKeyboardButton(text="🏠 Главная", callback_data="refresh")]
            ])
        )
        await callback.answer()
        return
    
    for i, match in enumerate(matches[:3]):
        match_text = format_match(match, f"🔴 LIVE {game_info['name']}")
        
        # Добавляем статус live
        match_text += f"\n\n🎮 <b>Матч идет прямо сейчас!</b>"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📺 Смотреть", url=match.get("official_stream_url", "#")),
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"live_{game}")
            ]
        ]) if match.get("official_stream_url") else None
        
        if i == 0:
            await callback.message.edit_text(
                match_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=match_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
    
    await callback.answer("✅ Live матчи загружены!")

# ========== ЗАПУСК БОТА ==========

async def on_startup():
    """Действия при запуске бота"""
    logger.info("Бот запущен!")
    
    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "✅ Бот запущен и готов к работе!")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def on_shutdown():
    """Действия при выключении бота"""
    logger.info("Остановка бота...")
    await panda_api.close()
    await bot.session.close()

async def main():
    """Основная функция запуска"""
    await on_startup()
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    # Проверка обязательных переменных
    if not PANDASCORE_TOKEN:
        logger.error("PANDASCORE_TOKEN не установлен!")
        exit(1)
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        exit(1)
    
    # Запуск бота
    asyncio.run(main())