import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

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

# Игры
GAMES = {
    "cs2": {
        "name": "Counter-Strike 2",
        "slug": "csgo",
        "search_term": "Counter-Strike",
        "emoji": "🎯",
        "color": "#FF6B00"
    },
    "dota2": {
        "name": "Dota 2",
        "slug": "dota-2",
        "search_term": "Dota",
        "emoji": "⚔️",
        "color": "#E60000"
    }
}

class PandaScoreAPI:
    """API клиент который точно работает"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def make_request(self, url: str, params: Optional[Dict] = None):
        """Базовый запрос"""
        try:
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Error {response.status}: {await response.text()}")
                    return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    # ========== CS2 МЕТОДЫ ==========
    
    async def get_cs2_matches(self, limit: int = 5):
        """Получить CS2 матчи - работает через прямой endpoint"""
        url = f"{self.base_url}/csgo/matches/upcoming"
        params = {
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        return await self.make_request(url, params)
    
    async def get_cs2_live(self):
        """CS2 live матчи"""
        url = f"{self.base_url}/csgo/matches/running"
        params = {"per_page": 3}
        return await self.make_request(url, params)
    
    # ========== DOTA 2 МЕТОДЫ ==========
    
    async def get_dota2_matches_via_search(self, limit: int = 5):
        """Получить Dota 2 матчи через поиск - ЭТО РАБОТАЕТ!"""
        url = f"{self.base_url}/matches"
        params = {
            "search[name]": "Dota",  # Поиск по названию Dota
            "per_page": limit,
            "sort": "scheduled_at",
            "filter[status]": "not_started,running",  # Предстоящие и текущие
            "page": 1
        }
        return await self.make_request(url, params)
    
    async def get_dota2_matches_via_videogame(self, limit: int = 5):
        """Попробовать через videogame фильтр"""
        # Сначала получим ID Dota 2
        url = f"{self.base_url}/videogames"
        games = await self.make_request(url)
        
        dota_id = None
        for game in games:
            if "dota" in game.get("slug", "").lower() or "dota" in game.get("name", "").lower():
                dota_id = game.get("id")
                logger.info(f"Найден Dota 2 ID: {dota_id} ({game.get('name')})")
                break
        
        if dota_id:
            url = f"{self.base_url}/matches"
            params = {
                "filter[videogame_id]": dota_id,
                "per_page": limit,
                "sort": "scheduled_at",
                "filter[status]": "not_started,running",
                "page": 1
            }
            return await self.make_request(url, params)
        
        return []
    
    async def get_dota2_live(self):
        """Dota 2 live матчи через поиск"""
        url = f"{self.base_url}/matches"
        params = {
            "search[name]": "Dota",
            "filter[status]": "running",  # Только running
            "per_page": 3,
            "sort": "-begin_at"  # Сначала самые свежие
        }
        return await self.make_request(url, params)
    
    # ========== ОБЩИЕ МЕТОДЫ ==========
    
    async def get_all_matches(self, limit: int = 8):
        """Все матчи CS2 и Dota 2"""
        all_matches = []
        
        # CS2
        cs2_matches = await self.get_cs2_matches(limit//2)
        for match in cs2_matches:
            match["game"] = "cs2"
            all_matches.append(match)
        
        # Dota 2 через поиск
        dota_matches = await self.get_dota2_matches_via_search(limit//2)
        for match in dota_matches:
            match["game"] = "dota2"
            all_matches.append(match)
        
        # Если Dota через поиск не нашел, пробуем другой метод
        if not dota_matches:
            dota_matches = await self.get_dota2_matches_via_videogame(limit//2)
            for match in dota_matches:
                match["game"] = "dota2"
                all_matches.append(match)
        
        # Сортируем по времени
        all_matches.sort(key=lambda x: x.get("scheduled_at", "9999"))
        return all_matches[:limit]
    
    async def get_all_live(self):
        """Все live матчи"""
        all_live = []
        
        # CS2 live
        cs2_live = await self.get_cs2_live()
        for match in cs2_live:
            match["game"] = "cs2"
            all_live.append(match)
        
        # Dota 2 live
        dota_live = await self.get_dota2_live()
        for match in dota_live:
            match["game"] = "dota2"
            all_live.append(match)
        
        return all_live
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== ОФОРМЛЕНИЕ ==========

def create_main_keyboard():
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 CS2 Матчи", callback_data="cs2_matches"),
            InlineKeyboardButton(text="⚔️ Dota 2 Матчи", callback_data="dota2_matches")
        ],
        [
            InlineKeyboardButton(text="🔥 Live Матчи", callback_data="live_matches"),
            InlineKeyboardButton(text="📊 Все Матчи", callback_data="all_matches")
        ]
    ])
    return keyboard

def create_back_keyboard():
    """Кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")]
    ])

def create_match_keyboard(match: Dict, game: str):
    """Клавиатура для матча"""
    buttons = []
    
    # Ссылка на трансляцию
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="📺 Смотреть трансляцию", url=stream_url)])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"{game}_matches"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_live_keyboard(match: Dict):
    """Клавиатура для live матча"""
    buttons = []
    
    # Ссылка на live трансляцию
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="🔥 Смотреть LIVE", url=stream_url)])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="live_matches"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time(scheduled_at: str) -> str:
    """Форматирование времени в MSK"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        # Сегодня/завтра/другой день
        if dt_msk.date() == now_msk.date():
            return f"<b>Сегодня в {dt_msk.strftime('%H:%M')}</b>"
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return f"<b>Завтра в {dt_msk.strftime('%H:%M')}</b>"
        else:
            days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            day_name = days[dt_msk.weekday()]
            return f"<b>{dt_msk.strftime('%d.%m')} ({day_name}) в {dt_msk.strftime('%H:%M')}</b>"
    except:
        return "<b>Скоро</b>"

def format_match(match: Dict, game_info: Dict, is_live: bool = False) -> str:
    """Форматирование информации о матче"""
    # Основная информация
    name = match.get("name", "")
    league = match.get("league", {}).get("name", "Турнир")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = "TBA"
    team2 = "TBA"
    
    if opponents and len(opponents) > 0:
        team1 = opponents[0].get("opponent", {}).get("name", "TBA")
    if opponents and len(opponents) > 1:
        team2 = opponents[1].get("opponent", {}).get("name", "TBA")
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_str = format_time(scheduled_at) if scheduled_at else "<b>Скоро</b>"
    
    # Статус
    if is_live:
        status = "🔴 <b>LIVE СЕЙЧАС</b>"
    else:
        status = "🟢 <b>Будет скоро</b>"
    
    # Формируем сообщение
    message = f"""
<blockquote>
{game_info['emoji']} <b>{game_info['name']}</b>

🏆 {league}
{name and f'📝 {name}' or ''}

<b>{team1}</b>
   ⚔️  vs  ⚔️
<b>{team2}</b>

{time_str}
{status}
</blockquote>
"""
    
    return message.strip()

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
<b>🎮 Каппер Бармен</b>

Следим за лучшими киберспортивными матчами:

🎯 Counter-Strike 2
⚔️ Dota 2

👇 Выбери что интересует:
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """CS2 матчи"""
    await show_cs2_matches(message)

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Dota 2 матчи"""
    await show_dota2_matches(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches(message)

@dp.message(Command("all"))
async def cmd_all(message: types.Message):
    """Все матчи"""
    await show_all_matches(message)

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery):
    """Главное меню"""
    welcome = """
<b>🎮 Каппер Бармен</b>

👇 Выбери что интересует:
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "cs2_matches")
async def handle_cs2_matches(callback: types.CallbackQuery):
    """CS2 матчи"""
    await callback.answer("🎯 Загружаю...")
    await show_cs2_matches_callback(callback)

@dp.callback_query(F.data == "dota2_matches")
async def handle_dota2_matches(callback: types.CallbackQuery):
    """Dota 2 матчи"""
    await callback.answer("⚔️ Загружаю...")
    await show_dota2_matches_callback(callback)

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live...")
    await show_live_matches_callback(callback)

@dp.callback_query(F.data == "all_matches")
async def handle_all_matches(callback: types.CallbackQuery):
    """Все матчи"""
    await callback.answer("📊 Собираю все...")
    await show_all_matches_callback(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_cs2_matches_callback(callback: types.CallbackQuery):
    """CS2 матчи через callback"""
    await show_cs2_matches(callback, is_callback=True)

async def show_cs2_matches(message_or_callback, is_callback: bool = False):
    """Показать CS2 матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("🎯 Ищу CS2 матчи...")
    else:
        msg = await message_or_callback.answer("🎯 Ищу CS2 матчи...")
    
    # Получаем матчи
    matches = await panda_api.get_cs2_matches(limit=5)
    
    if not matches:
        no_matches = "📭 Нет предстоящих матчей CS2"
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=create_back_keyboard())
        else:
            await msg.edit_text(no_matches, reply_markup=create_back_keyboard())
        return
    
    # Заголовок
    header = "<b>🎯 Counter-Strike 2 - Ближайшие матчи</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем матчи
    game_info = GAMES["cs2"]
    for match in matches:
        match_text = format_match(match, game_info)
        keyboard = create_match_keyboard(match, "cs2")
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

async def show_dota2_matches_callback(callback: types.CallbackQuery):
    """Dota 2 матчи через callback"""
    await show_dota2_matches(callback, is_callback=True)

async def show_dota2_matches(message_or_callback, is_callback: bool = False):
    """Показать Dota 2 матчи - ИСПРАВЛЕННЫЙ МЕТОД!"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("⚔️ Ищу Dota 2 матчи...")
    else:
        msg = await message_or_callback.answer("⚔️ Ищу Dota 2 матчи...")
    
    # Пробуем разные методы для Dota 2
    matches = []
    
    # 1. Через поиск (это работает!)
    matches = await panda_api.get_dota2_matches_via_search(limit=5)
    
    # 2. Если не нашли, пробуем другой метод
    if not matches:
        matches = await panda_api.get_dota2_matches_via_videogame(limit=5)
    
    # Фильтруем только Dota 2 матчи
    dota_matches = []
    for match in matches:
        # Проверяем что это действительно Dota 2
        league_name = match.get("league", {}).get("name", "").lower()
        match_name = match.get("name", "").lower()
        
        if "dota" in league_name or "dota" in match_name or match.get("game") == "dota2":
            dota_matches.append(match)
    
    if not dota_matches:
        no_matches = "📭 Нет предстоящих матчей Dota 2"
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=create_back_keyboard())
        else:
            await msg.edit_text(no_matches, reply_markup=create_back_keyboard())
        return
    
    # Заголовок
    header = "<b>⚔️ Dota 2 - Ближайшие матчи</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем матчи
    game_info = GAMES["dota2"]
    for match in dota_matches[:5]:  # Ограничиваем 5 матчами
        match_text = format_match(match, game_info)
        keyboard = create_match_keyboard(match, "dota2")
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

async def show_live_matches_callback(callback: types.CallbackQuery):
    """Live матчи через callback"""
    await show_live_matches(callback, is_callback=True)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("🔥 Ищу live матчи...")
    else:
        msg = await message_or_callback.answer("🔥 Ищу live матчи...")
    
    # Получаем live матчи
    live_matches = await panda_api.get_all_live()
    
    if not live_matches:
        no_live = "📭 Сейчас нет live матчей"
        
        if is_callback:
            await message_or_callback.message.edit_text(no_live, reply_markup=create_back_keyboard())
        else:
            await msg.edit_text(no_live, reply_markup=create_back_keyboard())
        return
    
    # Заголовок
    header = "<b>🔥 LIVE МАТЧИ ПРЯМО СЕЙЧАС</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем live матчи
    for match in live_matches:
        game_key = match.get("game", "cs2")
        game_info = GAMES.get(game_key, GAMES["cs2"])
        
        match_text = format_match(match, game_info, is_live=True)
        keyboard = create_live_keyboard(match)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

async def show_all_matches_callback(callback: types.CallbackQuery):
    """Все матчи через callback"""
    await show_all_matches(callback, is_callback=True)

async def show_all_matches(message_or_callback, is_callback: bool = False):
    """Показать все матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("📊 Собираю все матчи...")
    else:
        msg = await message_or_callback.answer("📊 Собираю все матчи...")
    
    # Получаем все матчи
    all_matches = await panda_api.get_all_matches(limit=8)
    
    if not all_matches:
        no_matches = "📭 Нет предстоящих матчей"
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=create_back_keyboard())
        else:
            await msg.edit_text(no_matches, reply_markup=create_back_keyboard())
        return
    
    # Заголовок
    header = "<b>📊 ВСЕ МАТЧИ CS2 И DOTA 2</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Группируем по играм и показываем
    cs2_matches = [m for m in all_matches if m.get("game") == "cs2"]
    dota_matches = [m for m in all_matches if m.get("game") == "dota2"]
    
    # CS2 матчи
    if cs2_matches:
        cs2_header = "<b>🎯 Counter-Strike 2</b>\n"
        await bot.send_message(chat_id, cs2_header)
        
        game_info = GAMES["cs2"]
        for match in cs2_matches[:3]:  # Первые 3 CS2 матча
            match_text = format_match(match, game_info)
            keyboard = create_match_keyboard(match, "cs2")
            
            await bot.send_message(
                chat_id=chat_id,
                text=match_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            await asyncio.sleep(0.2)
    
    # Dota 2 матчи
    if dota_matches:
        dota_header = "<b>⚔️ Dota 2</b>\n"
        await bot.send_message(chat_id, dota_header)
        
        game_info = GAMES["dota2"]
        for match in dota_matches[:3]:  # Первые 3 Dota 2 матча
            match_text = format_match(match, game_info)
            keyboard = create_match_keyboard(match, "dota2")
            
            await bot.send_message(
                chat_id=chat_id,
                text=match_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            await asyncio.sleep(0.2)

# ========== ЗАПУСК ==========

async def main():
    """Запуск бота"""
    logger.info("🚀 Запускаю Каппер Бармен...")
    logger.info("🎯 CS2 через прямой endpoint")
    logger.info("⚔️ Dota 2 через поиск (это работает!)")
    
    if not PANDASCORE_TOKEN or not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Не установлены токены!")
        return
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())