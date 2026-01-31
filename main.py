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

class PandaScoreAPI:
    """API клиент только для CS2"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    async def make_request(self, url: str, params: Optional[Dict] = None):
        """Универсальный запрос"""
        try:
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Error {response.status}: {await response.text()[:100]}")
                    return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_cs2_matches(self, limit: int = 6):
        """Получить предстоящие матчи CS2"""
        url = f"{self.base_url}/csgo/matches/upcoming"
        params = {
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        return await self.make_request(url, params)
    
    async def get_cs2_live(self, limit: int = 3):
        """Получить live матчи CS2"""
        url = f"{self.base_url}/csgo/matches/running"
        params = {
            "per_page": limit,
            "sort": "-begin_at"
        }
        return await self.make_request(url, params)
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== ОФОРМЛЕНИЕ В СТИЛЕ КИБЕРБАРА ==========

def create_main_keyboard():
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 ПРЕДСТОЯЩИЕ", callback_data="upcoming_matches"),
            InlineKeyboardButton(text="🔥 LIVE МАТЧИ", callback_data="live_matches")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh_menu")
        ]
    ])
    return keyboard

def create_match_keyboard(match: Dict, is_live: bool = False):
    """Клавиатура для матча"""
    buttons = []
    
    # Ссылка на стрим
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        if is_live:
            buttons.append([InlineKeyboardButton(text="📺 СМОТРЕТЬ LIVE", url=stream_url)])
        else:
            buttons.append([InlineKeyboardButton(text="🔔 НАПОМНИТЬ", callback_data="remind")])
    
    buttons.append([
        InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time_display(scheduled_at: str) -> str:
    """Красивое отображение времени"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        # Разница во времени
        time_diff = dt_msk - now_msk
        
        # Если сегодня
        if dt_msk.date() == now_msk.date():
            if time_diff.total_seconds() <= 0:
                return "🔴 СЕЙЧАС"
            elif time_diff.total_seconds() <= 3600:
                minutes = int(time_diff.total_seconds() / 60)
                return f"🟡 ЧЕРЕЗ {minutes} МИН"
            else:
                return f"🕐 СЕГОДНЯ {dt_msk.strftime('%H:%M')}"
        
        # Если завтра
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return f"📅 ЗАВТРА {dt_msk.strftime('%H:%M')}"
        
        # Если в течение недели
        elif time_diff.days < 7:
            days_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
            day_name = days_ru[dt_msk.weekday()]
            return f"📅 {day_name} {dt_msk.strftime('%H:%M')}"
        
        else:
            return f"📅 {dt_msk.strftime('%d.%m %H:%M')}"
            
    except:
        return "🕐 СКОРО"

def get_map_name(match: Dict) -> str:
    """Получить название карты"""
    # Пробуем разные поля где может быть карта
    for field in ["map", "maps", "map_name", "current_map"]:
        if match.get(field):
            map_name = match.get(field)
            if isinstance(map_name, dict):
                map_name = map_name.get("name", "")
            if map_name:
                # Красивые иконки для популярных карт CS2
                map_icons = {
                    "inferno": "🔥",
                    "mirage": "🏜️",
                    "dust2": "🏜️",
                    "nuke": "☢️",
                    "overpass": "🌉",
                    "vertigo": "🏢",
                    "ancient": "🗿",
                    "anubis": "🐫"
                }
                
                map_lower = map_name.lower()
                icon = "🎮"
                for key, emoji in map_icons.items():
                    if key in map_lower:
                        icon = emoji
                        break
                
                return f"{icon} {map_name.title()}"
    
    return "🎮 Карта не определена"

def get_match_score(match: Dict) -> str:
    """Получить счет матча"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1_score = opponents[0].get("opponent", {}).get("score", 0)
        team2_score = opponents[1].get("opponent", {}).get("score", 0)
        
        if team1_score is not None and team2_score is not None:
            return f"{team1_score} - {team2_score}"
    
    # Если нет счета, проверяем другие поля
    for field in ["score", "result", "current_score"]:
        if match.get(field):
            return str(match.get(field))
    
    return "0 - 0"

def format_upcoming_match(match: Dict) -> str:
    """Форматирование предстоящего матча"""
    # Основные данные
    league = match.get("league", {}).get("name", "ТУРНИР")
    tournament = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_display = format_time_display(scheduled_at)
    
    # Форматируем красиво
    message = f"""
┌─────────────────────────────┐
│         🎯 CS2 МАТЧ         │
├─────────────────────────────┤

<b>{team1}</b>
   🆚
<b>{team2}</b>

🏆 {league}
{tournament and f'📋 {tournament}' or ''}

{time_display}

└─────────────────────────────┘
"""
    
    return message.strip()

def format_live_match(match: Dict) -> str:
    """Форматирование live матча с картой и счетом"""
    # Основные данные
    league = match.get("league", {}).get("name", "LIVE ТУРНИР")
    tournament = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Карта и счет
    map_name = get_map_name(match)
    score = get_match_score(match)
    
    # Статус матча
    status = match.get("status", "running")
    status_text = "🎮 МАТЧ ИДЕТ"
    if status == "finished":
        status_text = "🏁 МАТЧ ЗАВЕРШЕН"
    elif status == "postponed":
        status_text = "⏸️ ОТЛОЖЕН"
    
    # Форматируем красиво
    message = f"""
┌─────────────────────────────┐
│        🔥 LIVE CS2         │
├─────────────────────────────┤

<b>{team1}</b>
   {score}
<b>{team2}</b>

{map_name}

🏆 {league}
{tournament and f'📋 {tournament}' or ''}

🔴 {status_text}

└─────────────────────────────┘
"""
    
    return message.strip()

# ========== КОМАНДЫ БОТА ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Стартовая команда"""
    welcome = """
<b>🎮 КИБЕРБАР CS2</b>

Добро пожаловать в бар киберспорта!
Только Counter-Strike 2, только хардкор.

👇 <b>Что показываем на экранах?</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("matches"))
async def cmd_matches(message: types.Message):
    """Предстоящие матчи"""
    await show_upcoming_matches(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches(message)

@dp.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    """Обновить меню"""
    await message.answer("🔄 Обновляю меню...")
    await cmd_start(message)

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery):
    """Главное меню"""
    welcome = """
<b>🎮 КИБЕРБАР CS2</b>

👇 <b>Что показываем на экранах?</b>
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh_menu")
async def handle_refresh_menu(callback: types.CallbackQuery):
    """Обновить меню"""
    await handle_main_menu(callback)
    await callback.answer("✅ Меню обновлено")

@dp.callback_query(F.data == "upcoming_matches")
async def handle_upcoming_matches(callback: types.CallbackQuery):
    """Предстоящие матчи"""
    await callback.answer("🎯 Ищу матчи...")
    await show_upcoming_matches_callback(callback)

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live...")
    await show_live_matches_callback(callback)

@dp.callback_query(F.data == "remind")
async def handle_remind(callback: types.CallbackQuery):
    """Напоминание"""
    await callback.answer("🔔 Напомню перед матчем!")

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_upcoming_matches(message_or_callback, is_callback: bool = False):
    """Показать предстоящие матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("🎯 <b>Смотрю расписание...</b>")
    else:
        msg = await message_or_callback.answer("🎯 <b>Смотрю расписание...</b>")
    
    # Получаем матчи
    matches = await panda_api.get_cs2_matches(5)
    
    if not matches:
        no_matches = """
📭 <b>Матчей не найдено</b>

<i>Возможно, турниры еще не анонсированы</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ", callback_data="upcoming_matches")],
            [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=keyboard)
        else:
            await msg.edit_text(no_matches, reply_markup=keyboard)
        return
    
    # Показываем заголовок
    header = f"""
┌─────────────────────────────┐
│     🎯 ПРЕДСТОЯЩИЕ МАТЧИ    │
│        найдено: {len(matches)}        │
└─────────────────────────────┘
"""
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем матчи
    for match in matches:
        match_text = format_upcoming_match(match)
        keyboard = create_match_keyboard(match, is_live=False)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

async def show_upcoming_matches_callback(callback: types.CallbackQuery):
    """Предстоящие матчи через callback"""
    await show_upcoming_matches(callback, is_callback=True)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text("🔥 <b>Смотрю что в эфире...</b>")
    else:
        msg = await message_or_callback.answer("🔥 <b>Смотрю что в эфире...</b>")
    
    # Получаем live матчи
    live_matches = await panda_api.get_cs2_live(3)
    
    if not live_matches:
        no_live = """
📭 <b>Сейчас нет live матчей</b>

<i>Но всегда можно посмотреть предстоящие!</i>
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 ПРЕДСТОЯЩИЕ", callback_data="upcoming_matches")],
            [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_live, reply_markup=keyboard)
        else:
            await msg.edit_text(no_live, reply_markup=keyboard)
        return
    
    # Показываем заголовок
    header = f"""
┌─────────────────────────────┐
│       🔥 LIVE МАТЧИ        │
│      онлайн: {len(live_matches)}       │
└─────────────────────────────┘
"""
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем live матчи
    for match in live_matches:
        match_text = format_live_match(match)
        keyboard = create_match_keyboard(match, is_live=True)
        
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

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю КиберБар CS2...")
    logger.info("🔥 Только Counter-Strike 2")
    
    if not PANDASCORE_TOKEN:
        logger.error("❌ Нет токена PandaScore!")
        return
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет токена Telegram!")
        return
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())