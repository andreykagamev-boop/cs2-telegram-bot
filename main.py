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
        "name": "CS2",
        "slug": "csgo",
        "emoji": "🎯",
        "color": "🟠"
    },
    "dota2": {
        "name": "Dota 2", 
        "slug": "dota-2",
        "emoji": "⚔️",
        "color": "🔵"
    }
}

class PandaScoreAPI:
    """Умный API клиент - CS2 через endpoint, Dota 2 через поиск"""
    
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
        """Универсальный запрос"""
        try:
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Error {response.status} for {url}")
                    return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    # ========== CS2 МЕТОДЫ ==========
    
    async def get_cs2_matches(self, limit: int = 5):
        """CS2 матчи - через endpoint (это работает)"""
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
    
    async def get_dota2_matches(self, limit: int = 5):
        """Dota 2 матчи - через поиск (endpoint не работает!)"""
        url = f"{self.base_url}/matches"
        params = {
            "search": "Dota",  # Ищем по слову Dota
            "filter[status]": "not_started",  # Только предстоящие
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        
        matches = await self.make_request(url, params)
        
        # Фильтруем чтобы точно были Dota 2 матчи
        dota_matches = []
        for match in matches:
            # Проверяем по разным признакам что это Dota 2
            league_name = match.get("league", {}).get("name", "").lower()
            match_name = match.get("name", "").lower()
            game_slug = match.get("videogame", {}).get("slug", "").lower()
            
            if any(x in league_name for x in ["dota", "dotа"]) or \
               any(x in match_name for x in ["dota", "dotа"]) or \
               any(x in game_slug for x in ["dota", "dotа"]):
                dota_matches.append(match)
        
        return dota_matches[:limit]
    
    async def get_dota2_live(self):
        """Dota 2 live матчи - через поиск"""
        url = f"{self.base_url}/matches"
        params = {
            "search": "Dota",
            "filter[status]": "running",  # Только live
            "per_page": 3,
            "sort": "-begin_at"
        }
        
        matches = await self.make_request(url, params)
        
        # Фильтруем Dota 2
        dota_matches = []
        for match in matches:
            league_name = match.get("league", {}).get("name", "").lower()
            match_name = match.get("name", "").lower()
            
            if any(x in league_name for x in ["dota", "dotа"]) or \
               any(x in match_name for x in ["dota", "dotа"]):
                dota_matches.append(match)
        
        return dota_matches
    
    # ========== ОБЩИЕ МЕТОДЫ ==========
    
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
    
    async def get_all_matches(self, limit: int = 8):
        """Все матчи CS2 и Dota 2"""
        all_matches = []
        
        # CS2
        cs2_matches = await self.get_cs2_matches(limit//2)
        for match in cs2_matches:
            match["game"] = "cs2"
            all_matches.append(match)
        
        # Dota 2
        dota_matches = await self.get_dota2_matches(limit//2)
        for match in dota_matches:
            match["game"] = "dota2"
            all_matches.append(match)
        
        # Сортируем по времени
        all_matches.sort(key=lambda x: x.get("scheduled_at", "9999"))
        return all_matches[:limit]
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== СТИЛЬ КАППЕР БАРМЕН ==========

def create_main_keyboard():
    """Главное меню в стиле бара"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 CS2 Матчи", callback_data="cs2_matches"),
            InlineKeyboardButton(text="⚔️ Dota 2 Матчи", callback_data="dota2_matches")
        ],
        [
            InlineKeyboardButton(text="🔥 Live Матчи", callback_data="live_matches")
        ],
        [
            InlineKeyboardButton(text="🍻 Обновить", callback_data="refresh")
        ]
    ])
    return keyboard

def create_match_keyboard(match: Dict, game: str, is_live: bool = False):
    """Клавиатура для матча"""
    buttons = []
    
    # Ссылка на трансляцию
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        if is_live:
            buttons.append([InlineKeyboardButton(text="🔥 Смотреть LIVE", url=stream_url)])
        else:
            buttons.append([InlineKeyboardButton(text="📺 Трансляция", url=stream_url)])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Еще", callback_data=f"{game}_matches"),
        InlineKeyboardButton(text="🏠 Бар", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time_for_bar(scheduled_at: str) -> str:
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
            return f"<b>{dt_msk.strftime('%d.%m')} ({days[dt_msk.weekday()]}) в {dt_msk.strftime('%H:%M')}</b>"
    except:
        return "<b>Скоро</b>"

def format_match_for_bar(match: Dict, game_info: Dict, is_live: bool = False) -> str:
    """Форматирование матча в стиле бара"""
    # Данные матча
    league = match.get("league", {}).get("name", "Турнир")
    tournament = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_str = format_time_for_bar(scheduled_at) if scheduled_at else "<b>Скоро</b>"
    
    # Статус
    if is_live:
        status = "🔥 <b>LIVE ПРЯМО СЕЙЧАС!</b>"
        time_str = "🔥 <b>НА ЭКРАНАХ</b>"
    else:
        status = "🟢 <b>СКОРО БУДЕТ</b>"
    
    # Сообщение в стиле бара
    message = f"""
{game_info['emoji']} <b>{game_info['name']}</b>

🏆 <i>{league}</i>
{tournament and f'📋 {tournament}' or ''}

<b>{team1}</b>
   ⚔️  vs  ⚔️
<b>{team2}</b>

{time_str}
{status}

<code>┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄</code>
🎧 <i>Звук включен</i> | 📺 <i>На всех экранах</i>
"""
    
    return message.strip()

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
<b>🍻 Каппер Бармен</b>

Добро пожаловать в киберспорт бар!

🎯 CS2 матчи
⚔️ Dota 2 матчи

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
    await show_cs2_matches(message)

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Dota 2 матчи"""
    await show_dota2_matches(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches(message)

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тест API"""
    await message.answer("🔧 Тестирую API...")
    
    # Тест CS2
    cs2_matches = await panda_api.get_cs2_matches(1)
    cs2_status = f"🎯 CS2: {'✅ Работает' if cs2_matches else '❌ Нет матчей'}"
    
    # Тест Dota 2
    dota_matches = await panda_api.get_dota2_matches(1)
    dota_status = f"⚔️ Dota 2: {'✅ Работает' if dota_matches else '❌ Нет матчей'}"
    
    await message.answer(f"{cs2_status}\n{dota_status}")

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery):
    """Главное меню"""
    welcome = """
<b>🍻 Каппер Бармен</b>

👇 <b>Что сегодня на экранах?</b>
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновить"""
    await handle_main_menu(callback)
    await callback.answer("🔄 Обновлено!")

@dp.callback_query(F.data == "cs2_matches")
async def handle_cs2_matches(callback: types.CallbackQuery):
    """CS2 матчи"""
    await callback.answer("🎯 Загружаю...")
    await show_cs2_matches(callback, is_callback=True)

@dp.callback_query(F.data == "dota2_matches")
async def handle_dota2_matches(callback: types.CallbackQuery):
    """Dota 2 матчи"""
    await callback.answer("⚔️ Загружаю...")
    await show_dota2_matches(callback, is_callback=True)

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live...")
    await show_live_matches(callback, is_callback=True)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_cs2_matches(message_or_callback, is_callback: bool = False):
    """Показать CS2 матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("🎯 Ищу CS2 матчи...")
    else:
        msg = await message_or_callback.answer("🎯 Ищу CS2 матчи...")
    
    # Получаем матчи
    matches = await panda_api.get_cs2_matches(5)
    
    if not matches:
        no_matches = "📭 Нет матчей CS2"
        
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
        match_text = format_match_for_bar(match, game_info)
        keyboard = create_match_keyboard(match, "cs2")
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

async def show_dota2_matches(message_or_callback, is_callback: bool = False):
    """Показать Dota 2 матчи - через поиск!"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("⚔️ Ищу Dota 2 матчи...")
    else:
        msg = await message_or_callback.answer("⚔️ Ищу Dota 2 матчи...")
    
    # Получаем матчи через поиск
    matches = await panda_api.get_dota2_matches(5)
    
    if not matches:
        no_matches = "📭 Нет матчей Dota 2"
        
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
    for match in matches:
        match_text = format_match_for_bar(match, game_info)
        keyboard = create_match_keyboard(match, "dota2")
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

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
        
        match_text = format_match_for_bar(match, game_info, is_live=True)
        keyboard = create_match_keyboard(match, game_key, is_live=True)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

def create_back_keyboard():
    """Клавиатура с кнопкой назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")]
    ])

# ========== ЗАПУСК ==========

async def main():
    """Запуск бота"""
    logger.info("🍻 Запускаю Каппер Бармен...")
    logger.info("🎯 CS2: через /csgo/matches/upcoming")
    logger.info("⚔️ Dota 2: через поиск /matches?search=Dota")
    
    if not PANDASCORE_TOKEN or not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Не установлены токены!")
        return
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())