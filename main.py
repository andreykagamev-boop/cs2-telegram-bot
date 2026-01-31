import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

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
    """API клиент для CS2"""
    
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
    
    async def get_cs2_matches(self, limit: int = 15):
        """Получить предстоящие матчи CS2"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/matches/upcoming"
            
            params = {
                "per_page": limit,
                "sort": "scheduled_at",
                "page": 1
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Error {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_cs2_live(self, limit: int = 10):
        """Получить live матчи CS2"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/matches/running"
            
            params = {
                "per_page": limit,
                "sort": "-begin_at"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== МИНИМАЛИСТИЧНЫЙ ИНТЕРФЕЙС ==========

def create_main_keyboard():
    """Минималистичное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Расписание", callback_data="schedule"),
            InlineKeyboardButton(text="🔥 Live", callback_data="live")
        ]
    ])
    return keyboard

def format_time_minimal(scheduled_at: str) -> str:
    """Минималистичное форматирование времени"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        # Сегодня
        if dt_msk.date() == now_msk.date():
            return dt_msk.strftime("· %H:%M")
        
        # Завтра
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return dt_msk.strftime("· %H:%M (завтра)")
        
        # Другая дата
        else:
            days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            return dt_msk.strftime(f"· %H:%M ({days[dt_msk.weekday()]})")
            
    except:
        return "· время уточняется"

def get_match_score(match: Dict) -> str:
    """Получить счет матча"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1_score = opponents[0].get("opponent", {}).get("score", 0)
        team2_score = opponents[1].get("opponent", {}).get("score", 0)
        
        if team1_score is not None and team2_score is not None:
            return f"{team1_score}:{team2_score}"
    
    return "0:0"

def get_map_name(match: Dict) -> str:
    """Получить название карты"""
    # Пробуем разные поля
    for field in ["map", "current_map", "map_name"]:
        if match.get(field):
            map_data = match.get(field)
            if isinstance(map_data, dict):
                return map_data.get("name", "?")
            return str(map_data)
    
    return "?"

def format_match_line(match: Dict, is_live: bool = False) -> str:
    """Одна строка с информацией о матче"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {}).get("acronym") or opponents[0].get("opponent", {}).get("name", "?")
        team2 = opponents[1].get("opponent", {}).get("acronym") or opponents[1].get("opponent", {}).get("name", "?")
        
        if is_live:
            score = get_match_score(match)
            map_name = get_map_name(match)
            return f"<b>{team1} {score} {team2}</b> · {map_name}"
        else:
            scheduled_at = match.get("scheduled_at", "")
            time_str = format_time_minimal(scheduled_at)
            return f"{team1} vs {team2} {time_str}"
    
    return "?"

def format_schedule_message(matches: List[Dict]) -> str:
    """Форматировать расписание матчей"""
    if not matches:
        return "📭 Нет предстоящих матчей"
    
    # Группируем по дням
    matches_by_day = {}
    
    for match in matches:
        scheduled_at = match.get("scheduled_at")
        if not scheduled_at:
            continue
            
        try:
            dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            dt_msk = dt_utc + timedelta(hours=3)
            date_key = dt_msk.strftime("%Y-%m-%d")
            
            if date_key not in matches_by_day:
                matches_by_day[date_key] = []
            matches_by_day[date_key].append(match)
        except:
            continue
    
    # Формируем сообщение
    lines = ["<b>📅 Расписание CS2</b>", ""]
    
    for date_key in sorted(matches_by_day.keys()):
        matches_on_day = matches_by_day[date_key]
        
        # Заголовок дня
        dt = datetime.fromisoformat(date_key)
        today = datetime.utcnow() + timedelta(hours=3)
        
        if dt.date() == today.date():
            day_header = "· <b>Сегодня</b>"
        elif dt.date() == today.date() + timedelta(days=1):
            day_header = "· <b>Завтра</b>"
        else:
            days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            day_header = f"· <b>{dt.strftime('%d.%m')} ({days[dt.weekday()]})</b>"
        
        lines.append(day_header)
        
        # Матчи этого дня
        for match in matches_on_day:
            match_line = "  " + format_match_line(match, is_live=False)
            
            # Турнир (только если отличается от предыдущего)
            league = match.get("league", {}).get("name", "")
            if league:
                match_line += f" · {league}"
            
            lines.append(match_line)
        
        lines.append("")
    
    return "\n".join(lines).strip()

def format_live_message(matches: List[Dict]) -> str:
    """Форматировать live матчи"""
    if not matches:
        return "📭 Сейчас нет live матчей"
    
    lines = ["<b>🔥 Live CS2</b>", ""]
    
    for match in matches:
        match_line = "· " + format_match_line(match, is_live=True)
        
        # Турнир
        league = match.get("league", {}).get("name", "")
        if league:
            match_line += f" · {league}"
        
        lines.append(match_line)
        
        # Ссылка на стрим если есть
        stream_url = match.get("official_stream_url") or match.get("live_url")
        if stream_url:
            lines.append(f"  → <a href='{stream_url}'>смотреть</a>")
        
        lines.append("")
    
    return "\n".join(lines).strip()

def create_schedule_keyboard():
    """Клавиатура для расписания"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="schedule")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])
    return keyboard

def create_live_keyboard():
    """Клавиатура для live"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="live")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])
    return keyboard

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    message_text = """
<b>CS2 Matches</b>
Только актуальные матчи
"""
    
    await message.answer(
        message_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    """Расписание"""
    await show_schedule(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live(message)

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "menu")
async def handle_menu(callback: types.CallbackQuery):
    """Главное меню"""
    message_text = """
<b>CS2 Matches</b>
Только актуальные матчи
"""
    
    await callback.message.edit_text(
        message_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "schedule")
async def handle_schedule(callback: types.CallbackQuery):
    """Расписание"""
    await callback.answer("📅 Загружаю...")
    await show_schedule_callback(callback)

@dp.callback_query(F.data == "live")
async def handle_live(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live...")
    await show_live_callback(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_schedule(message_or_callback, is_callback: bool = False):
    """Показать расписание"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус
    if is_callback:
        await message_or_callback.message.edit_text("📅 Загружаю расписание...")
    else:
        msg = await message_or_callback.answer("📅 Загружаю расписание...")
    
    # Получаем матчи
    matches = await panda_api.get_cs2_matches(limit=15)  # 15 матчей
    
    if not matches:
        error_text = "📭 Нет данных о матчах"
        
        if is_callback:
            await message_or_callback.message.edit_text(error_text, reply_markup=create_schedule_keyboard())
        else:
            await msg.edit_text(error_text, reply_markup=create_schedule_keyboard())
        return
    
    # Форматируем
    schedule_text = format_schedule_message(matches)
    
    if is_callback:
        await message_or_callback.message.edit_text(
            schedule_text,
            reply_markup=create_schedule_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            schedule_text,
            reply_markup=create_schedule_keyboard(),
            disable_web_page_preview=True
        )

async def show_schedule_callback(callback: types.CallbackQuery):
    """Расписание через callback"""
    await show_schedule(callback, is_callback=True)

async def show_live(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус
    if is_callback:
        await message_or_callback.message.edit_text("🔥 Ищу live матчи...")
    else:
        msg = await message_or_callback.answer("🔥 Ищу live матчи...")
    
    # Получаем live
    matches = await panda_api.get_cs2_live(limit=10)  # 10 live матчей
    
    if not matches:
        error_text = "📭 Сейчас нет live матчей"
        
        if is_callback:
            await message_or_callback.message.edit_text(error_text, reply_markup=create_live_keyboard())
        else:
            await msg.edit_text(error_text, reply_markup=create_live_keyboard())
        return
    
    # Форматируем
    live_text = format_live_message(matches)
    
    if is_callback:
        await message_or_callback.message.edit_text(
            live_text,
            reply_markup=create_live_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            live_text,
            reply_markup=create_live_keyboard(),
            disable_web_page_preview=True
        )

async def show_live_callback(callback: types.CallbackQuery):
    """Live через callback"""
    await show_live(callback, is_callback=True)

# ========== ЗАПУСК ==========

async def main():
    """Запуск бота"""
    logger.info("🚀 Запускаю CS2 Matches...")
    
    if not PANDASCORE_TOKEN or not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Не установлены токены!")
        return
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())