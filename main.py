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
    """Профессиональный API клиент"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def get_cs2_matches(self, limit: int = 12):
        """Получить предстоящие матчи"""
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
                    data = await response.json()
                    return data
                return []
        except Exception as e:
            logger.error(f"API Error: {e}")
            return []
    
    async def get_cs2_live(self, limit: int = 8):
        """Получить live матчи"""
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
            logger.error(f"API Error: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== ПРОФЕССИОНАЛЬНЫЙ ДИЗАЙН ==========

def create_main_keyboard():
    """Профессиональное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 ПРЕДСТОЯЩИЕ", callback_data="upcoming"),
            InlineKeyboardButton(text="🔥 LIVE", callback_data="live")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh"),
            InlineKeyboardButton(text="ℹ️ ИНФО", callback_data="info")
        ]
    ])
    return keyboard

def create_back_keyboard():
    """Кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])

def format_match_time(scheduled_at: str) -> str:
    """Профессиональное форматирование времени"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        # Если сегодня
        if dt_msk.date() == now_msk.date():
            # Если меньше часа до начала
            time_diff = dt_msk - now_msk
            if 0 < time_diff.total_seconds() <= 3600:
                mins = int(time_diff.total_seconds() / 60)
                return f"⏰ {mins} мин"
            return f"📅 {dt_msk.strftime('%H:%M')}"
        
        # Если завтра
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return f"📅 {dt_msk.strftime('%H:%M')} (завтра)"
        
        # Другой день
        else:
            days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
            return f"📅 {dt_msk.strftime('%d.%m')} {dt_msk.strftime('%H:%M')}"
            
    except:
        return "⏳ Скоро"

def get_match_score(match: Dict) -> tuple:
    """Получить счет и информацию о картах"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1_score = opponents[0].get("opponent", {}).get("score", 0)
        team2_score = opponents[1].get("opponent", {}).get("score", 0)
        
        # Карта
        map_name = match.get("videogame_version", {}).get("current_version", "")
        if not map_name:
            map_name = match.get("map", {}).get("name", "?")
        
        return team1_score, team2_score, map_name
    
    return 0, 0, "?"

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд"""
    team_emojis = {
        "navi": "🟡", "natus vincere": "🟡",
        "vitality": "🐝", "team vitality": "🐝",
        "faze": "⚡", "faze clan": "⚡",
        "g2": "👑", "g2 esports": "👑",
        "virtus.pro": "🐻", "vp": "🐻",
        "spirit": "🐉", "team spirit": "🐉",
        "cloud9": "☁️", "c9": "☁️",
        "heroic": "⚔️",
        "astralis": "⭐",
        "nip": "👑", "ninjas in pyjamas": "👑",
        "mouz": "🐭", "mousesports": "🐭",
        "ence": "🇫🇮",
        "furia": "🔥",
        "imperial": "👑",
        "big": "🇩🇪",
        "complexity": "🌀",
        "liquid": "💧", "team liquid": "💧"
    }
    
    team_lower = team_name.lower()
    for key, emoji in team_emojis.items():
        if key in team_lower:
            return emoji
    
    return "🎮"

def format_upcoming_match(match: Dict, index: int) -> str:
    """Форматирование предстоящего матча"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        
        team1_emoji = get_team_emoji(team1_name)
        team2_emoji = get_team_emoji(team2_name)
        
        league = match.get("league", {}).get("name", "")
        scheduled_at = match.get("scheduled_at", "")
        time_str = format_match_time(scheduled_at)
        
        return f"{index}. {team1_emoji} <b>{team1_name}</b> vs {team2_emoji} <b>{team2_name}</b>\n   └─ {time_str} • {league}"
    
    return f"{index}. Матч не определен"

def format_live_match(match: Dict, index: int) -> str:
    """Форматирование live матча"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        
        team1_emoji = get_team_emoji(team1_name)
        team2_emoji = get_team_emoji(team2_name)
        
        score1, score2, map_name = get_match_score(match)
        league = match.get("league", {}).get("name", "")
        
        # Статус матча
        status = match.get("status", "running")
        status_emoji = "🔴" if status == "running" else "🟡"
        
        return f"{index}. {status_emoji} {team1_emoji} <b>{team1_name}</b> {score1}:{score2} {team2_emoji} <b>{team2_name}</b>\n   └─ 🗺️ {map_name} • {league}"
    
    return f"{index}. Матч не определен"

def create_upcoming_message(matches: List[Dict]) -> str:
    """Создать сообщение с предстоящими матчами"""
    if not matches:
        return """
🎯 <b>ПРЕДСТОЯЩИЕ МАТЧИ CS2</b>

📭 На данный момент нет запланированных матчей.

🔄 <i>Попробуйте обновить позже</i>
"""
    
    lines = [
        "🎯 <b>ПРЕДСТОЯЩИЕ МАТЧИ CS2</b>",
        "",
        f"📊 <i>Найдено матчей: {len(matches)}</i>",
        ""
    ]
    
    for i, match in enumerate(matches[:10], 1):  # Показываем первые 10
        lines.append(format_upcoming_match(match, i))
    
    if len(matches) > 10:
        lines.append(f"\n... и еще {len(matches) - 10} матчей")
    
    lines.append("\n⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_live_message(matches: List[Dict]) -> str:
    """Создать сообщение с live матчами"""
    if not matches:
        return """
🔥 <b>LIVE МАТЧИ CS2</b>

📭 В данный момент нет матчей в прямом эфире.

🔄 <i>Проверьте предстоящие матчи</i>
"""
    
    lines = [
        "🔥 <b>LIVE МАТЧИ CS2</b>",
        "",
        f"📡 <i>Матчей в эфире: {len(matches)}</i>",
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        lines.append(format_live_match(match, i))
        
        # Ссылка на стрим если есть
        stream_url = match.get("official_stream_url") or match.get("live_url")
        if stream_url:
            lines.append(f"   └─ 📺 <a href='{stream_url}'>Смотреть трансляцию</a>")
        
        lines.append("")
    
    return "\n".join(lines)

# ========== КОМАНДЫ БОТА ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
🎮 <b>CS2 PRO TRACKER</b>

Точная аналитика и отслеживание матчей Counter-Strike 2.

📊 <b>Функции:</b>
• Расписание предстоящих матчей
• Live трансляции со счетом
• Уведомления о начале матчей
• Профессиональная аналитика

👇 <b>Выберите раздел:</b>
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

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    """Назад в меню"""
    welcome = """
🎮 <b>CS2 PRO TRACKER</b>

👇 <b>Выберите раздел:</b>
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновить"""
    await callback.answer("🔄 Обновление...")
    await cmd_start(callback.message)
    await callback.answer("✅ Обновлено")

@dp.callback_query(F.data == "info")
async def handle_info(callback: types.CallbackQuery):
    """Информация"""
    info_text = """
ℹ️ <b>ИНФОРМАЦИЯ</b>

🎮 <b>CS2 PRO TRACKER</b>
Профессиональный бот для отслеживания матчей Counter-Strike 2.

📊 <b>Данные:</b>
• Источник: PandaScore API
• Время: MSK (Москва)
• Обновление: в реальном времени

⚙️ <b>Команды:</b>
/start - Главное меню
/matches - Предстоящие матчи  
/live - Live трансляции

📈 <b>Особенности:</b>
• Точное время матчей
• Счет live матчей
• Карты и турниры
• Ссылки на трансляции

<i>Для точной аналитики и ставок</i>
"""
    
    await callback.message.edit_text(
        info_text,
        reply_markup=create_back_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "upcoming")
async def handle_upcoming(callback: types.CallbackQuery):
    """Предстоящие матчи"""
    await callback.answer("📊 Загружаю расписание...")
    await show_upcoming_matches_callback(callback)

@dp.callback_query(F.data == "live")
async def handle_live(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live матчи...")
    await show_live_matches_callback(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_upcoming_matches(message_or_callback, is_callback: bool = False):
    """Показать предстоящие матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📊 <b>Загружаю расписание матчей...</b>")
    else:
        msg = await message_or_callback.answer("📊 <b>Загружаю расписание матчей...</b>")
    
    # Получаем матчи
    matches = await panda_api.get_cs2_matches(12)
    
    # Создаем сообщение
    message_text = create_upcoming_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="upcoming")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

async def show_upcoming_matches_callback(callback: types.CallbackQuery):
    """Предстоящие через callback"""
    await show_upcoming_matches(callback, is_callback=True)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("🔥 <b>Ищу матчи в прямом эфире...</b>")
    else:
        msg = await message_or_callback.answer("🔥 <b>Ищу матчи в прямом эфире...</b>")
    
    # Получаем live матчи
    matches = await panda_api.get_cs2_live(8)
    
    # Создаем сообщение
    message_text = create_live_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="live")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")]
    ])
    
    if is_callback:
        await message_or_callback.message.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

async def show_live_matches_callback(callback: types.CallbackQuery):
    """Live через callback"""
    await show_live_matches(callback, is_callback=True)

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю CS2 PRO TRACKER...")
    
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