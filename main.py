import os
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
from enum import Enum

import aiohttp
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv
import redis.asyncio as redis

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Константы
CACHE_TTL = 300  # 5 минут
MAX_MATCHES_PER_PAGE = 10
TIMEZONE_OFFSET = 3  # MSK (UTC+3)

# Инициализация роутера
router = Router()

class MatchStatus(Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"

class PandaScoreAPI:
    """API клиент для CS2 с кэшированием"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co/csgo"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
        self.redis_client = None
        
    async def init_redis(self):
        """Инициализация Redis для кэширования"""
        try:
            self.redis_client = await redis.from_url(REDIS_URL)
            logger.info("Redis подключен")
        except Exception as e:
            logger.warning(f"Redis не подключен: {e}")
            self.redis_client = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    async def get_cached(self, key: str) -> Optional[Dict]:
        """Получить данные из кэша"""
        if not self.redis_client:
            return None
        
        try:
            data = await self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Ошибка получения из кэша: {e}")
            return None
    
    async def set_cached(self, key: str, data: Dict, ttl: int = CACHE_TTL):
        """Сохранить данные в кэш"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.setex(key, ttl, json.dumps(data))
        except Exception as e:
            logger.error(f"Ошибка сохранения в кэш: {e}")
    
    async def get_matches_by_date(self, target_date: datetime.date) -> List[Dict]:
        """Получить матчи на конкретную дату"""
        cache_key = f"matches_{target_date.isoformat()}"
        
        # Проверяем кэш
        cached = await self.get_cached(cache_key)
        if cached:
            return cached
        
        try:
            session = await self.get_session()
            
            start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(days=1)
            
            url = f"{self.base_url}/matches"
            params = {
                "range[scheduled_at]": f"{start_dt.isoformat()},{end_dt.isoformat()}",
                "per_page": 100,
                "sort": "scheduled_at",
                "filter[status]": "not_started",
                "filter[videogame_version]": "2"  # CS2
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем по точной дате
                    filtered_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                if match_dt.date() == target_date:
                                    filtered_matches.append(match)
                            except:
                                continue
                    
                    # Кэшируем результат
                    await self.set_cached(cache_key, filtered_matches)
                    return filtered_matches
                else:
                    logger.error(f"API error: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
            return []
    
    async def get_live_matches(self, force_refresh: bool = False) -> List[Dict]:
        """Получить live матчи"""
        cache_key = "live_matches"
        
        if not force_refresh:
            cached = await self.get_cached(cache_key)
            if cached:
                return cached
        
        try:
            session = await self.get_session()
            url = f"{self.base_url}/matches/running"
            
            params = {
                "per_page": 20,
                "sort": "-begin_at",
                "filter[videogame_version]": "2"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    await self.set_cached(cache_key, matches, ttl=60)  # Live матчи кэшируем на 1 минуту
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении live матчей: {e}")
            return []
    
    async def get_upcoming_matches(self, limit: int = 10) -> List[Dict]:
        """Получить ближайшие матчи"""
        cache_key = f"upcoming_matches_{limit}"
        
        cached = await self.get_cached(cache_key)
        if cached:
            return cached
        
        try:
            session = await self.get_session()
            now = datetime.now(timezone.utc)
            future = now + timedelta(days=7)  # Матчи на ближайшие 7 дней
            
            url = f"{self.base_url}/matches"
            params = {
                "range[scheduled_at]": f"{now.isoformat()},{future.isoformat()}",
                "per_page": limit,
                "sort": "scheduled_at",
                "filter[status]": "not_started",
                "filter[videogame_version]": "2"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    await self.set_cached(cache_key, matches, ttl=300)
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении ближайших матчей: {e}")
            return []
    
    async def close(self):
        """Закрытие соединений"""
        if self.session and not self.session.closed:
            await self.session.close()
        if self.redis_client:
            await self.redis_client.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

def format_match_time(scheduled_at: str) -> Tuple[str, str]:
    """Форматирование времени в MSK"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        dt_msk = dt_utc + timedelta(hours=TIMEZONE_OFFSET)
        return dt_msk.strftime("%H:%M"), dt_msk.strftime("%d.%m.%Y")
    except:
        return "Скоро", ""

def get_match_status(match: Dict) -> MatchStatus:
    """Получить статус матча"""
    status = match.get("status", "").lower()
    for match_status in MatchStatus:
        if status == match_status.value:
            return match_status
    return MatchStatus.NOT_STARTED

def get_match_score(match: Dict) -> Tuple[int, int]:
    """Получить счет матча"""
    results = match.get("results", [])
    if len(results) >= 2:
        return results[0].get("score", 0), results[1].get("score", 0)
    
    # Альтернативный способ
    opponents = match.get("opponents", [])
    if len(opponents) >= 2:
        team1_score = opponents[0].get("opponent", {}).get("score", 0)
        team2_score = opponents[1].get("opponent", {}).get("score", 0)
        return team1_score, team2_score
    
    return 0, 0

TEAM_EMOJIS = {
    "navi": "🟡", "natus": "🟡",
    "vitality": "🐝", "vita": "🐝",
    "faze": "⚡", "faze clan": "⚡",
    "g2": "👑", "g2 esports": "👑",
    "spirit": "🐉", "team spirit": "🐉",
    "cloud9": "☁️", "c9": "☁️",
    "liquid": "💧", "team liquid": "💧",
    "heroic": "⚔️",
    "astralis": "⭐",
    "ence": "🇫🇮",
    "furia": "🔥", "furia esports": "🔥",
    "virtus.pro": "🐻", "vp": "🐻", "virtus pro": "🐻",
    "mouz": "🐭", "mousesports": "🐭",
    "nip": "👑", "ninjas in pyjamas": "👑",
    "big": "🇩🇪",
    "og": "⚫",
    "fnatic": "🟠",
    "complexity": "🔴"
}

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд"""
    if not team_name:
        return "🎮"
    
    team_lower = team_name.lower()
    
    for team_key, emoji in TEAM_EMOJIS.items():
        if team_key in team_lower:
            return emoji
    
    return "🎮"

def get_team_name(team_data: Dict) -> str:
    """Получить имя команды"""
    if not team_data:
        return "TBA"
    
    # Пробуем получить acronym
    acronym = team_data.get("acronym")
    if acronym and acronym != "null":
        return acronym
    
    # Или полное имя
    name = team_data.get("name", "TBA")
    if name == "null":
        return "TBA"
    
    return name

def format_match_info(match: Dict, show_date: bool = False) -> str:
    """Форматирование информации о матче"""
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        return "Команды не определены"
    
    team1_data = opponents[0].get("opponent", {})
    team2_data = opponents[1].get("opponent", {})
    
    team1_name = get_team_name(team1_data)
    team2_name = get_team_name(team2_data)
    
    team1_emoji = get_team_emoji(team1_name)
    team2_emoji = get_team_emoji(team2_name)
    
    status = get_match_status(match)
    scheduled_at = match.get("scheduled_at", "")
    time_str, date_str = format_match_time(scheduled_at)
    
    league = match.get("league", {}).get("name", "")
    tournament = match.get("tournament", {}).get("name", "")
    event_name = tournament or league or "Матч"
    
    if status == MatchStatus.RUNNING:
        score1, score2 = get_match_score(match)
        return (f"🔴 {team1_emoji} <b>{team1_name}</b> {score1}:{score2} <b>{team2_name}</b> {team2_emoji}\n"
                f"   ⏱️ LIVE | 🏆 {event_name}")
    
    elif status == MatchStatus.FINISHED:
        winner_id = match.get("winner_id")
        score1, score2 = get_match_score(match)
        
        if winner_id == team1_data.get("id"):
            winner_text = f"✅ <b>{team1_name}</b> побеждает"
        elif winner_id == team2_data.get("id"):
            winner_text = f"✅ <b>{team2_name}</b> побеждает"
        else:
            winner_text = "Матч завершен"
        
        return f"{winner_text} ({score1}:{score2})\n🏆 {event_name}"
    
    else:  # NOT_STARTED, CANCELLED или другие
        date_info = f" | 📅 {date_str}" if show_date and date_str else ""
        status_emoji = "⏰" if status == MatchStatus.NOT_STARTED else "❌"
        return (f"{team1_emoji} <b>{team1_name}</b> vs {team2_emoji} <b>{team2_name}</b>\n"
                f"   {status_emoji} {time_str}{date_info} | 🏆 {event_name}")

def create_pagination_keyboard(page: int, total_pages: int, callback_prefix: str) -> InlineKeyboardMarkup:
    """Создание клавиатуры с пагинацией"""
    buttons = []
    
    # Кнопка "Назад" если не первая страница
    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{callback_prefix}_{page-1}"))
    
    # Информация о странице
    buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    
    # Кнопка "Вперед" если не последняя страница
    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"{callback_prefix}_{page+1}"))
    
    # Основные кнопки
    keyboard = [
        buttons,
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 СЕГОДНЯ", callback_data="today_1"),
            InlineKeyboardButton(text="📅 ЗАВТРА", callback_data="tomorrow_1")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE", callback_data="live_1"),
            InlineKeyboardButton(text="⏳ БЛИЖАЙШИЕ", callback_data="upcoming_1")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh"),
            InlineKeyboardButton(text="ℹ️ ПОМОЩЬ", callback_data="help")
        ]
    ])
    return keyboard

async def send_match_list(chat_id: int, matches: List[Dict], title: str, page: int = 1):
    """Отправить список матчей с пагинацией"""
    if not matches:
        await bot.send_message(
            chat_id,
            f"🤷‍♂️ <b>{title}</b>\n\n"
            f"На данный момент матчей не найдено.\n"
            f"Попробуйте позже или проверьте другие даты.",
            reply_markup=create_main_keyboard()
        )
        return
    
    # Пагинация
    total_pages = (len(matches) + MAX_MATCHES_PER_PAGE - 1) // MAX_MATCHES_PER_PAGE
    start_idx = (page - 1) * MAX_MATCHES_PER_PAGE
    end_idx = min(start_idx + MAX_MATCHES_PER_PAGE, len(matches))
    
    message_text = f"<b>{title}</b>\n\n"
    
    for i, match in enumerate(matches[start_idx:end_idx], start=start_idx + 1):
        match_info = format_match_info(match, show_date=("завтра" in title.lower() or "ближай" in title.lower()))
        message_text += f"{i}. {match_info}\n\n"
    
    message_text += f"📊 Показано {start_idx + 1}-{end_idx} из {len(matches)} матчей\n"
    message_text += f"⏱️ Время указано в MSK (UTC+{TIMEZONE_OFFSET})"
    
    if total_pages > 1:
        # Определяем префикс для callback_data
        if "сегодня" in title.lower():
            prefix = "today"
        elif "завтра" in title.lower():
            prefix = "tomorrow"
        elif "live" in title.lower():
            prefix = "live"
        else:
            prefix = "upcoming"
        
        keyboard = create_pagination_keyboard(page, total_pages, prefix)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
            [InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]
        ])
    
    try:
        await bot.send_message(chat_id, message_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# Инициализация бота ДО использования
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
dp.include_router(router)

# Обработчики команд
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    welcome_text = (
        "🎮 <b>CS2 MATCHES BOT</b>\n\n"
        "Добро пожаловать! Я помогу отслеживать матчи по Counter-Strike 2:\n\n"
        "📅 <b>Матчи на сегодня/завтра</b>\n"
        "🔥 <b>Live матчи со счетом</b>\n"
        "⏰ <b>Ближайшие матчи</b>\n"
        "📊 <b>Статистика и результаты</b>\n\n"
        "Используйте кнопки ниже для навигации:"
    )
    
    await message.answer(welcome_text, reply_markup=create_main_keyboard())

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    help_text = (
        "🆘 <b>СПРАВКА ПО КОМАНДАМ</b>\n\n"
        "Основные команды:\n"
        "/start - Запустить бота\n"
        "/today - Матчи на сегодня\n"
        "/tomorrow - Матчи на завтра\n"
        "/live - Текущие live матчи\n"
        "/upcoming - Ближайшие матчи\n"
        "/refresh - Обновить данные\n"
        "/help - Эта справка\n\n"
        
        "📌 <b>Кнопки управления:</b>\n"
        "• Используйте кнопки для навигации\n"
        "• Пагинация при большом количестве матчей\n"
        "• 🔄 Обновление данных каждые 5 минут\n\n"
        
        "⏱️ <b>Время:</b>\n"
        "Все время указано в MSK (Московское время)\n\n"
        
        "📡 <b>Источник данных:</b>\n"
        "Данные предоставляются PandaScore API"
    )
    
    await message.answer(help_text, reply_markup=create_main_keyboard())

# Обработчики callback-запросов
@router.callback_query(F.data.startswith("today_"))
async def handle_today_matches(callback: CallbackQuery):
    """Матчи на сегодня"""
    try:
        page = int(callback.data.split("_")[1])
        today = datetime.now(timezone.utc).date()
        matches = await panda_api.get_matches_by_date(today)
        
        await send_match_list(
            callback.message.chat.id,
            matches,
            f"📅 МАТЧИ НА СЕГОДНЯ ({today.strftime('%d.%m.%Y')})",
            page
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in today matches: {e}")
        await callback.answer("Ошибка при получении данных")

@router.callback_query(F.data.startswith("tomorrow_"))
async def handle_tomorrow_matches(callback: CallbackQuery):
    """Матчи на завтра"""
    try:
        page = int(callback.data.split("_")[1])
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
        matches = await panda_api.get_matches_by_date(tomorrow)
        
        await send_match_list(
            callback.message.chat.id,
            matches,
            f"📅 МАТЧИ НА ЗАВТРА ({tomorrow.strftime('%d.%m.%Y')})",
            page
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in tomorrow matches: {e}")
        await callback.answer("Ошибка при получении данных")

@router.callback_query(F.data.startswith("live_"))
async def handle_live_matches(callback: CallbackQuery):
    """Live матчи"""
    try:
        page = int(callback.data.split("_")[1])
        matches = await panda_api.get_live_matches(force_refresh=True)
        
        if not matches:
            await bot.send_message(
                callback.message.chat.id,
                "📡 <b>LIVE МАТЧИ</b>\n\n"
                "В данный момент live матчей нет.\n"
                "Проверьте расписание предстоящих матчей!",
                reply_markup=create_main_keyboard()
            )
            await callback.answer()
            return
        
        await send_match_list(
            callback.message.chat.id,
            matches,
            "🔥 LIVE МАТЧИ CS2",
            page
        )
        await callback.answer("Данные обновлены")
    except Exception as e:
        logger.error(f"Error in live matches: {e}")
        await callback.answer("Ошибка при получении данных")

@router.callback_query(F.data.startswith("upcoming_"))
async def handle_upcoming_matches(callback: CallbackQuery):
    """Ближайшие матчи"""
    try:
        page = int(callback.data.split("_")[1])
        matches = await panda_api.get_upcoming_matches(limit=50)
        
        await send_match_list(
            callback.message.chat.id,
            matches,
            "⏳ БЛИЖАЙШИЕ МАТЧИ CS2",
            page
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in upcoming matches: {e}")
        await callback.answer("Ошибка при получении данных")

@router.callback_query(F.data == "refresh")
async def handle_refresh(callback: CallbackQuery):
    """Обновление данных"""
    await callback.answer("🔄 Обновление...")
    
    # Определяем, что обновлять по тексту сообщения
    message_text = callback.message.text or ""
    
    if "СЕГОДНЯ" in message_text:
        await handle_today_matches(
            CallbackQuery(
                id=callback.id,
                from_user=callback.from_user,
                chat_instance=callback.chat_instance,
                message=callback.message,
                data="today_1"
            )
        )
    elif "ЗАВТРА" in message_text:
        await handle_tomorrow_matches(
            CallbackQuery(
                id=callback.id,
                from_user=callback.from_user,
                chat_instance=callback.chat_instance,
                message=callback.message,
                data="tomorrow_1"
            )
        )
    elif "LIVE" in message_text:
        await handle_live_matches(
            CallbackQuery(
                id=callback.id,
                from_user=callback.from_user,
                chat_instance=callback.chat_instance,
                message=callback.message,
                data="live_1"
            )
        )
    elif "БЛИЖАЙШИЕ" in message_text:
        await handle_upcoming_matches(
            CallbackQuery(
                id=callback.id,
                from_user=callback.from_user,
                chat_instance=callback.chat_instance,
                message=callback.message,
                data="upcoming_1"
            )
        )
    else:
        # По умолчанию показываем сегодняшние матчи
        await handle_today_matches(
            CallbackQuery(
                id=callback.id,
                from_user=callback.from_user,
                chat_instance=callback.chat_instance,
                message=callback.message,
                data="today_1"
            )
        )

@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    try:
        await callback.message.edit_text(
            "🎮 <b>CS2 MATCHES BOT</b>\n\n"
            "Выберите нужный раздел:",
            reply_markup=create_main_keyboard()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "🎮 <b>CS2 MATCHES BOT</b>\n\n"
            "Выберите нужный раздел:",
            reply_markup=create_main_keyboard()
        )
    await callback.answer()

@router.callback_query(F.data == "help")
async def handle_help(callback: CallbackQuery):
    """Помощь"""
    await cmd_help(callback.message)
    await callback.answer()

@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery):
    """Пустой обработчик для кнопок-заглушек"""
    await callback.answer()

# Дополнительные команды
@router.message(Command("today"))
async def cmd_today(message: types.Message):
    """Команда /today"""
    await handle_today_matches(
        CallbackQuery(
            id="cmd",
            from_user=message.from_user,
            chat_instance="cmd",
            message=message,
            data="today_1"
        )
    )

@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    """Команда /tomorrow"""
    await handle_tomorrow_matches(
        CallbackQuery(
            id="cmd",
            from_user=message.from_user,
            chat_instance="cmd",
            message=message,
            data="tomorrow_1"
        )
    )

@router.message(Command("live"))
async def cmd_live(message: types.Message):
    """Команда /live"""
    await handle_live_matches(
        CallbackQuery(
            id="cmd",
            from_user=message.from_user,
            chat_instance="cmd",
            message=message,
            data="live_1"
        )
    )

@router.message(Command("upcoming"))
async def cmd_upcoming(message: types.Message):
    """Команда /upcoming - ближайшие матчи"""
    await handle_upcoming_matches(
        CallbackQuery(
            id="cmd",
            from_user=message.from_user,
            chat_instance="cmd",
            message=message,
            data="upcoming_1"
        )
    )

@router.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    """Команда /refresh"""
    await message.answer("🔄 Обновление данных...")
    await cmd_today(message)

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю CS2 MATCHES BOT...")
    
    if not PANDASCORE_TOKEN or not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Не установлены токены!")
        return
    
    # Инициализация Redis
    await panda_api.init_redis()
    
    try:
        # Команды для меню бота
        await bot.set_my_commands([
            types.BotCommand(command="start", description="Запустить бота"),
            types.BotCommand(command="today", description="Матчи на сегодня"),
            types.BotCommand(command="tomorrow", description="Матчи на завтра"),
            types.BotCommand(command="live", description="Live матчи"),
            types.BotCommand(command="upcoming", description="Ближайшие матчи"),
            types.BotCommand(command="refresh", description="Обновить данные"),
            types.BotCommand(command="help", description="Помощь")
        ])
        
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await panda_api.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())