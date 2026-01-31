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

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Константы игр - ИСПОЛЬЗУЕМ ТОТ ЖЕ КОД ЧТО РАБОТАЛ!
GAMES = {
    "cs2": {
        "name": "CS2",
        "slug": "csgo",
        "emoji": "🔫",
        "color": "🟠"
    },
    "dota2": {
        "name": "Dota 2",
        "slug": "dota-2",  # Тот же slug что работал!
        "emoji": "⚔️",
        "color": "🔵"
    }
}

class PandaScoreAPI:
    """Класс для работы с PandaScore API - оставляем как было"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def get_upcoming_matches(self, game_slug: str, limit: int = 5):
        """Получение предстоящих матчей - старый рабочий метод"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{game_slug}/matches/upcoming"
            
            logger.info(f"Запрос к {url}")
            
            async with session.get(url, params={
                "per_page": limit,
                "sort": "scheduled_at",
                "page": 1
            }) as response:
                
                logger.info(f"Статус ответа: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Получено {len(data)} матчей для {game_slug}")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"API Error {response.status}: {error_text[:200]}")
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

# ========== СТИЛЬ КАППЕР БАРМЕН ==========

def create_main_keyboard():
    """Главное меню в стиле бара"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 CS2", callback_data="cs2_matches"),
            InlineKeyboardButton(text="⚔️ Dota 2", callback_data="dota2_matches")
        ],
        [
            InlineKeyboardButton(text="🔥 Live", callback_data="live_all")
        ],
        [
            InlineKeyboardButton(text="🍻 Обновить бар", callback_data="refresh")
        ]
    ])
    return keyboard

def create_match_keyboard(match: dict, game: str, is_live: bool = False):
    """Клавиатура для матча"""
    buttons = []
    
    # Ссылка на стрим
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        if is_live:
            buttons.append([InlineKeyboardButton(text="🍻 Смотреть LIVE", url=stream_url)])
        else:
            buttons.append([InlineKeyboardButton(text="📺 Трансляция", url=stream_url)])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Еще", callback_data=f"{game}_matches"),
        InlineKeyboardButton(text="🏠 Бар", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time_for_bar(scheduled_at: str) -> str:
    """Форматирование времени для бара"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        # Определяем когда
        if dt_msk.date() == now_msk.date():
            return f"🍻 <b>Сегодня в {dt_msk.strftime('%H:%M')}</b>"
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return f"🍻 <b>Завтра в {dt_msk.strftime('%H:%M')}</b>"
        else:
            days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            return f"🍻 <b>{dt_msk.strftime('%d.%m')} ({days[dt_msk.weekday()]}) в {dt_msk.strftime('%H:%M')}</b>"
    except:
        return "🍻 <b>Скоро на экранах</b>"

def format_match_for_bar(match: dict, game_info: dict, is_live: bool = False) -> str:
    """Форматирование матча в стиле бара"""
    # Основные данные
    league = match.get("league", {}).get("name", "Турнир")
    series = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_display = format_time_for_bar(scheduled_at) if scheduled_at else "🍻 <b>Скоро на экранах</b>"
    
    # Статус
    if is_live:
        status = "🔥 <b>LIVE ПРЯМО СЕЙЧАС!</b>"
        time_display = "🔥 <b>НА ЭКРАНАХ СЕЙЧАС</b>"
    else:
        status = "🟢 <b>СКОРО БУДЕТ</b>"
    
    # Формируем сообщение в стиле бара
    message = f"""
{game_info['color']} <b>КАППЕР БАРМЕН ПРЕДСТАВЛЯЕТ:</b>

{game_info['emoji']} <b>{game_info['name']}</b>

🏆 <i>{league}</i>
{series and f'📋 {series}' or ''}

<b>{team1}</b>
   🍻  vs  🍻
<b>{team2}</b>

{time_display}
{status}

<code>┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄</code>
🎧 <i>Звук включен на всех колонках</i>
📺 <i>Трансляция на всех экранах</i>
"""
    
    return message.strip()

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Стартовая команда"""
    welcome = """
🍻 <b>КАППЕР БАРМЕН</b>

Добро пожаловать в киберспорт бар!
Следим за лучшими матчами и наливаем кружечку.

🎯 CS2 | ⚔️ Dota 2

👇 <b>Что сегодня на экранах?</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """CS2 матчи"""
    await show_matches(message, "cs2")

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Dota 2 матчи"""
    await show_matches(message, "dota2")

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches_standalone(message)

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая команда"""
    await message.answer("🔧 Тестирую подключение...")
    
    # Тестируем обе игры
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=2)
        if matches:
            await message.answer(f"✅ {game_info['name']}: найдено {len(matches)} матчей")
            # Покажем первый матч
            if matches:
                match = matches[0]
                await message.answer(
                    f"Пример:\nЛига: {match.get('league', {}).get('name', 'N/A')}\n"
                    f"Время: {match.get('scheduled_at', 'N/A')}"
                )
        else:
            await message.answer(f"❌ {game_info['name']}: матчей не найдено")

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery):
    """Главное меню"""
    welcome = """
🍻 <b>КАППЕР БАРМЕН</b>

👇 <b>Что сегодня на экранах?</b>
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard()
    )
    await callback.answer("🍻 Добро пожаловать обратно!")

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновить бар"""
    await handle_main_menu(callback)
    await callback.answer("🔄 Бар обновлен!")

@dp.callback_query(F.data == "cs2_matches")
async def handle_cs2_matches(callback: types.CallbackQuery):
    """CS2 матчи"""
    await callback.answer("🎯 Смотрю расписание CS2...")
    await show_matches_callback(callback, "cs2")

@dp.callback_query(F.data == "dota2_matches")
async def handle_dota2_matches(callback: types.CallbackQuery):
    """Dota 2 матчи"""
    await callback.answer("⚔️ Смотрю расписание Dota 2...")
    await show_matches_callback(callback, "dota2")

@dp.callback_query(F.data == "live_all")
async def handle_live_all(callback: types.CallbackQuery):
    """Все live матчи"""
    await callback.answer("🔥 Смотрю что в эфире...")
    await show_all_live_matches(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_matches(message_or_callback, game: str, is_callback: bool = False):
    """Показать матчи для игры"""
    if game not in GAMES:
        error = "❌ Эту игру пока не показываем в баре"
        if is_callback:
            await message_or_callback.message.edit_text(error)
        else:
            await message_or_callback.answer(error)
        return
    
    game_info = GAMES[game]
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    loading_msg = f"{game_info['emoji']} <b>Спрашиваю у бармена про {game_info['name']}...</b>"
    
    if is_callback:
        await message_or_callback.message.edit_text(loading_msg)
    else:
        msg = await message_or_callback.answer(loading_msg)
    
    # Получаем матчи - СТАРЫЙ РАБОЧИЙ МЕТОД!
    matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=5)
    
    if not matches:
        no_matches = f"""
📭 <b>{game_info['name']} сегодня тихо</b>

<i>Бармен говорит: "Загляни позже или выпей пивка пока ждешь!"</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить", callback_data=f"{game}_matches")],
            [InlineKeyboardButton(text="🏠 В бар", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=keyboard)
        else:
            await msg.edit_text(no_matches, reply_markup=keyboard)
        return
    
    # Заголовок
    header = f"""
{game_info['color']} <b>{game_info['emoji']} {game_info['name']} НА ЭКРАНАХ БАРА</b>

🎮 <i>Ближайшие {len(matches)} матчей:</i>
"""
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем матчи
    for i, match in enumerate(matches):
        match_text = format_match_for_bar(match, game_info)
        keyboard = create_match_keyboard(match, game)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)

async def show_matches_callback(callback: types.CallbackQuery, game: str):
    """Показать матчи через callback"""
    await show_matches(callback, game, is_callback=True)

async def show_all_live_matches(callback: types.CallbackQuery):
    """Показать все live матчи"""
    await callback.message.edit_text("🔥 <b>Смотрю на все экраны в баре...</b>")
    
    all_live = []
    
    # Проверяем обе игры
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_live.append(match)
    
    if not all_live:
        no_live = """
📭 <b>Сейчас в баре тихо</b>

<i>Но всегда есть холодное пиво и повторы лучших моментов!</i>
"""
        
        await callback.message.edit_text(
            no_live,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 CS2 Расписание", callback_data="cs2_matches")],
                [InlineKeyboardButton(text="⚔️ Dota 2 Расписание", callback_data="dota2_matches")],
                [InlineKeyboardButton(text="🏠 В бар", callback_data="main_menu")]
            ])
        )
        await callback.answer()
        return
    
    # Заголовок
    header = f"""
🔥 <b>LIVE В БАРЕ ПРЯМО СЕЙЧАС!</b>

🎮 <i>На {len(all_live)} экранах:</i>
"""
    
    await callback.message.edit_text(header)
    
    # Показываем live матчи
    for match in all_live:
        game_info = match.pop("game_info")
        live_text = format_match_for_bar(match, game_info, is_live=True)
        keyboard = create_match_keyboard(match, game_info["slug"].replace("-", ""), is_live=True)
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=live_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)
    
    await callback.answer(f"🔥 {len(all_live)} матчей в эфире!")

async def show_live_matches_standalone(message: types.Message):
    """Live матчи через команду"""
    msg = await message.answer("🔥 <b>Смотрю что в эфире...</b>")
    
    all_live = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_live.append(match)
    
    if not all_live:
        await msg.edit_text("📭 <b>Сейчас нет live трансляций</b>")
        return
    
    header = f"🔥 <b>LIVE: {len(all_live)} матчей</b>"
    await msg.edit_text(header)
    
    for match in all_live[:3]:  # Ограничим 3 матчами
        game_info = match.pop("game_info")
        live_text = format_match_for_bar(match, game_info, is_live=True)
        keyboard = create_match_keyboard(match, game_info["slug"].replace("-", ""), is_live=True)
        
        await message.answer(
            live_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)

# ========== ЗАПУСК ==========

async def main():
    """Запуск бота"""
    logger.info("🍻 Запускаю Каппер Бармен...")
    logger.info(f"🎯 Игры: {', '.join([g['name'] for g in GAMES.values()])}")
    
    # Проверяем токены
    if not PANDASCORE_TOKEN:
        logger.error("❌ Нет токена PandaScore!")
        return
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет токена Telegram!")
        return
    
    # Тестируем API при запуске
    logger.info("🔧 Тестирую API...")
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=1)
        if matches:
            logger.info(f"✅ {game_info['name']}: API работает")
        else:
            logger.warning(f"⚠️ {game_info['name']}: матчей не найдено")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())