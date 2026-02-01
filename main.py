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
    """API клиент для CS2 - исправленная версия"""
    
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
    
    async def get_upcoming_matches(self, days: int = 2):
        """Получить предстоящие матчи - исправленный метод"""
        try:
            session = await self.get_session()
            
            # Получаем ВСЕ предстоящие матчи
            url = f"{self.base_url}/csgo/matches/upcoming"
            params = {
                "per_page": 100,  # Больше матчей за один запрос
                "sort": "scheduled_at",
                "page": 1
            }
            
            logger.info("Запрос предстоящих матчей...")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Получено матчей: {len(matches)}")
                    
                    # Фильтруем по дате
                    now = datetime.utcnow()
                    filtered_matches = []
                    
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                
                                # Проверяем что матч в будущем
                                if match_time > now:
                                    # Фильтруем по количеству дней
                                    days_diff = (match_time.date() - now.date()).days
                                    if days_diff < days:
                                        filtered_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"После фильтрации: {len(filtered_matches)} матчей")
                    return filtered_matches
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка {response.status}: {error_text[:200]}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
            return []
    
    async def get_today_matches(self):
        """Получить матчи только на сегодня"""
        try:
            session = await self.get_session()
            
            # Получаем текущую дату в UTC
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            # Форматируем даты для API
            today_str = today.isoformat()
            tomorrow_str = tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today_str},{tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            logger.info(f"Запрос матчей с {today_str} по {tomorrow_str}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем только сегодняшние
                    today_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                if match_time.date() == today:
                                    today_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"Найдено матчей на сегодня: {len(today_matches)}")
                    return today_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении сегодняшних матчей: {e}")
            return []
    
    async def get_tomorrow_matches(self):
        """Получить матчи только на завтра"""
        try:
            session = await self.get_session()
            
            # Получаем дату завтра
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after_tomorrow = today + timedelta(days=2)
            
            # Форматируем даты для API
            tomorrow_str = tomorrow.isoformat()
            day_after_tomorrow_str = day_after_tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{tomorrow_str},{day_after_tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            logger.info(f"Запрос матчей с {tomorrow_str} по {day_after_tomorrow_str}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем только завтрашние
                    tomorrow_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                if match_time.date() == tomorrow:
                                    tomorrow_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"Найдено матчей на завтра: {len(tomorrow_matches)}")
                    return tomorrow_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении завтрашних матчей: {e}")
            return []
    
    async def get_live_matches(self):
        """Получить live матчи"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/matches/running"
            
            params = {
                "per_page": 10,
                "sort": "-begin_at"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Найдено live матчей: {len(matches)}")
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении live матчей: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== ПРОФЕССИОНАЛЬНЫЙ ДИЗАЙН ==========

def create_main_keyboard():
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 СЕГОДНЯ", callback_data="today"),
            InlineKeyboardButton(text="📅 ЗАВТРА", callback_data="tomorrow")
        ],
        [
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
    """Форматирование времени в MSK"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%H:%M")
    except:
        return "Скоро"

def get_match_score(match: Dict) -> tuple:
    """Получить счет матча - без карты"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        # Получаем счет
        team1_score = team1.get("score", 0)
        team2_score = team2.get("score", 0)
        
        return team1_score, team2_score
    
    return 0, 0

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд"""
    if not team_name:
        return "🎮"
    
    team_lower = team_name.lower()
    
    # Популярные команды
    if "navi" in team_lower or "natus" in team_lower:
        return "🟡"
    elif "vitality" in team_lower or "vita" in team_lower:
        return "🐝"
    elif "faze" in team_lower:
        return "⚡"
    elif "g2" in team_lower:
        return "👑"
    elif "spirit" in team_lower:
        return "🐉"
    elif "cloud9" in team_lower or "c9" in team_lower:
        return "☁️"
    elif "liquid" in team_lower:
        return "💧"
    elif "heroic" in team_lower:
        return "⚔️"
    elif "astralis" in team_lower:
        return "⭐"
    elif "ence" in team_lower:
        return "🇫🇮"
    elif "furia" in team_lower:
        return "🔥"
    elif "vp" in team_lower or "virtus" in team_lower:
        return "🐻"
    
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
        
        # Простая строка
        return f"{index}. {team1_emoji} <b>{team1_name}</b>  vs  {team2_emoji} <b>{team2_name}</b>\n   ⏰ {time_str}  |  🏆 {league}"
    
    return ""

def format_live_match(match: Dict, index: int) -> str:
    """Форматирование live матча - БЕЗ КАРТЫ"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        
        team1_emoji = get_team_emoji(team1_name)
        team2_emoji = get_team_emoji(team2_name)
        
        # Получаем счет
        score1, score2 = get_match_score(match)
        league = match.get("league", {}).get("name", "")
        
        return f"{index}. 🔴 {team1_emoji} <b>{team1_name}</b>  {score1}:{score2}  {team2_emoji} <b>{team2_name}</b>\n   🏆 {league}"
    
    return ""

def create_today_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на сегодня"""
    today = datetime.utcnow() + timedelta(hours=3)
    today_str = today.strftime('%d.%m')
    
    if not matches:
        return f"""
📅 <b>МАТЧИ НА СЕГОДНЯ ({today_str})</b>

📭 Сегодня нет запланированных матчей CS2.

👉 <i>Проверьте матчи на завтра</i>
"""
    
    # Сортируем по времени
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА СЕГОДНЯ ({today_str})</b>",
        "",
        f"📊 <i>Найдено матчей: {len(matches)}</i>",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        match_line = format_upcoming_match(match, i)
        if match_line:
            lines.append(match_line)
            lines.append("")
    
    lines.append(f"⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_tomorrow_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на завтра"""
    tomorrow = datetime.utcnow() + timedelta(hours=3) + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%d.%m')
    
    if not matches:
        return f"""
📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>

📭 Завтра нет запланированных матчей CS2.

👉 <i>Проверьте матчи на сегодня</i>
"""
    
    # Сортируем по времени
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>",
        "",
        f"📊 <i>Найдено матчей: {len(matches)}</i>",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        match_line = format_upcoming_match(match, i)
        if match_line:
            lines.append(match_line)
            lines.append("")
    
    lines.append(f"⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_live_message(matches: List[Dict]) -> str:
    """Создать сообщение с live матчами - БЕЗ КАРТЫ"""
    if not matches:
        return """
🔥 <b>LIVE МАТЧИ CS2</b>

📭 В данный момент нет матчей в прямом эфире.

👉 <i>Проверьте предстоящие матчи на сегодня/завтра</i>
"""
    
    lines = [
        "🔥 <b>LIVE МАТЧИ CS2</b>",
        "",
        f"📡 <i>Матчей в эфире: {len(matches)}</i>",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        match_line = format_live_match(match, i)
        if match_line:
            lines.append(match_line)
            
            # Ссылка на трансляцию
            stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
            if stream_url:
                lines.append(f"   📺 <a href='{stream_url}'>Смотреть трансляцию</a>")
            
            lines.append("")
    
    return "\n".join(lines)

# ========== КОМАНДЫ БОТА ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
🎮 <b>CS2 MATCHES</b>

Актуальные матчи Counter-Strike 2
Только сегодня, завтра и live трансляции

👇 <b>Выберите раздел:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Матчи сегодня"""
    await show_today(message)

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    """Матчи завтра"""
    await show_tomorrow(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live(message)

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    """Назад в меню"""
    welcome = """
🎮 <b>CS2 MATCHES</b>

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

@dp.callback_query(F.data == "info")
async def handle_info(callback: types.CallbackQuery):
    """Информация"""
    info_text = """
ℹ️ <b>ИНФОРМАЦИЯ</b>

🎮 <b>CS2 MATCHES</b>
Простой и удобный бот для отслеживания матчей CS2.

📊 <b>Что показывает:</b>
• Матчи на сегодня
• Матчи на завтра  
• Live трансляции со счетом

⚙️ <b>Техническая информация:</b>
• Источник: PandaScore API
• Время: MSK (Москва)
• Обновление: по требованию

<i>Для быстрого доступа к актуальной информации</i>
"""
    
    await callback.message.edit_text(
        info_text,
        reply_markup=create_back_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "today")
async def handle_today(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("📅 Загружаю матчи на сегодня...")
    await show_today_callback(callback)

@dp.callback_query(F.data == "tomorrow")
async def handle_tomorrow(callback: types.CallbackQuery):
    """Матчи завтра"""
    await callback.answer("📅 Загружаю матчи на завтра...")
    await show_tomorrow_callback(callback)

@dp.callback_query(F.data == "live")
async def handle_live(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live матчи...")
    await show_live_callback(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_today_callback(callback: types.CallbackQuery):
    """Матчи сегодня через callback"""
    await show_today(callback, is_callback=True)

async def show_today(message_or_callback, is_callback: bool = False):
    """Показать матчи на сегодня"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📅 <b>Загружаю матчи на сегодня...</b>")
    else:
        msg = await message_or_callback.answer("📅 <b>Загружаю матчи на сегодня...</b>")
    
    # Получаем матчи
    matches = await panda_api.get_today_matches()
    
    # Создаем сообщение
    message_text = create_today_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="today")],
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

async def show_tomorrow_callback(callback: types.CallbackQuery):
    """Матчи завтра через callback"""
    await show_tomorrow(callback, is_callback=True)

async def show_tomorrow(message_or_callback, is_callback: bool = False):
    """Показать матчи на завтра"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📅 <b>Загружаю матчи на завтра...</b>")
    else:
        msg = await message_or_callback.answer("📅 <b>Загружаю матчи на завтра...</b>")
    
    # Получаем матчи
    matches = await panda_api.get_tomorrow_matches()
    
    # Создаем сообщение
    message_text = create_tomorrow_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="tomorrow")],
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

async def show_live_callback(callback: types.CallbackQuery):
    """Live матчи через callback"""
    await show_live(callback, is_callback=True)

async def show_live(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("🔥 <b>Ищу матчи в прямом эфире...</b>")
    else:
        msg = await message_or_callback.answer("🔥 <b>Ищу матчи в прямом эфире...</b>")
    
    # Получаем live матчи
    matches = await panda_api.get_live_matches()
    
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

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю CS2 MATCHES...")
    logger.info("📅 Отдельные запросы на сегодня/завтра")
    logger.info("🔥 Live матчи без карты")
    
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