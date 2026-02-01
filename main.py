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
    """API клиент с пагинацией"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    async def get_all_cs2_matches(self, days_ahead: int = 7):
        """Получить ВСЕ предстоящие матчи на неделю вперед"""
        all_matches = []
        page = 1
        
        try:
            session = await self.get_session()
            
            while True:
                url = f"{self.base_url}/csgo/matches/upcoming"
                params = {
                    "per_page": 100,  # Максимальное количество на странице
                    "sort": "scheduled_at",
                    "page": page
                }
                
                logger.info(f"Запрос страницы {page} матчей...")
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        matches = await response.json()
                        if not matches:
                            break
                        
                        all_matches.extend(matches)
                        logger.info(f"Получено {len(matches)} матчей со страницы {page}")
                        
                        # Если на странице меньше 100 матчей, значит это последняя
                        if len(matches) < 100:
                            break
                        
                        page += 1
                    else:
                        logger.error(f"Ошибка {response.status}")
                        break
                        
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
        
        logger.info(f"Всего получено матчей: {len(all_matches)}")
        return all_matches
    
    async def get_cs2_live(self):
        """Получить live матчи - исправленная версия"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/csgo/matches/running"
            
            params = {
                "per_page": 20,
                "sort": "-begin_at"
            }
            
            logger.info("Запрос live матчей...")
            
            async with session.get(url, params=params) as response:
                logger.info(f"Статус live запроса: {response.status}")
                
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Найдено live матчей: {len(matches)}")
                    return matches
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка live: {response.status} - {error_text[:200]}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при запросе live: {e}")
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
            InlineKeyboardButton(text="📊 ВСЕ МАТЧИ", callback_data="all_matches"),
            InlineKeyboardButton(text="🔥 LIVE", callback_data="live_matches")
        ],
        [
            InlineKeyboardButton(text="📅 СЕГОДНЯ", callback_data="today_matches"),
            InlineKeyboardButton(text="📅 ЗАВТРА", callback_data="tomorrow_matches")
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
                return f"🕐 {mins} мин"
            return f"🕐 {dt_msk.strftime('%H:%M')}"
        
        # Если завтра
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return f"📅 {dt_msk.strftime('%H:%M')}"
        
        # Другой день
        else:
            days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "Сб", "ВС"]
            return f"📅 {dt_msk.strftime('%d.%m')} {days[dt_msk.weekday()]} {dt_msk.strftime('%H:%M')}"
            
    except:
        return "⏳ Скоро"

def get_match_score(match: Dict) -> tuple:
    """Получить счет и информацию о картах"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1_score = opponents[0].get("opponent", {}).get("score", 0)
        team2_score = opponents[1].get("opponent", {}).get("score", 0)
        
        # Карта
        map_info = match.get("map", {})
        if isinstance(map_info, dict):
            map_name = map_info.get("name", "")
        else:
            map_name = str(map_info) if map_info else ""
        
        if not map_name:
            map_name = "?"
        
        return team1_score, team2_score, map_name
    
    return 0, 0, "?"

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд"""
    team_lower = team_name.lower()
    
    emoji_map = {
        "navi": "🟡", "natus": "🟡",
        "vitality": "🐝", "vita": "🐝",
        "faze": "⚡", 
        "g2": "👑",
        "virtus": "🐻", "vp": "🐻",
        "spirit": "🐉",
        "cloud9": "☁️", "c9": "☁️",
        "heroic": "⚔️",
        "astralis": "⭐",
        "nip": "👑", "ninjas": "👑",
        "mouz": "🐭", "mouse": "🐭",
        "ence": "🇫🇮",
        "furia": "🔥",
        "imperial": "👑",
        "big": "🇩🇪",
        "complexity": "🌀",
        "liquid": "💧",
        "fnatic": "🦊",
        "og": "🟢"
    }
    
    for key, emoji in emoji_map.items():
        if key in team_lower:
            return emoji
    
    return "🎮"

def format_match_line(match: Dict, index: int, is_live: bool = False) -> str:
    """Форматирование строки матча"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        
        team1_emoji = get_team_emoji(team1_name)
        team2_emoji = get_team_emoji(team2_name)
        
        league = match.get("league", {}).get("name", "")
        
        if is_live:
            score1, score2, map_name = get_match_score(match)
            return f"{index}. 🔴 {team1_emoji} <b>{team1_name}</b> {score1}:{score2} {team2_emoji} <b>{team2_name}</b>\n   ├─ 🗺️ {map_name}\n   └─ 🏆 {league}"
        else:
            scheduled_at = match.get("scheduled_at", "")
            time_str = format_match_time(scheduled_at)
            return f"{index}. {team1_emoji} <b>{team1_name}</b> vs {team2_emoji} <b>{team2_name}</b>\n   ├─ {time_str}\n   └─ 🏆 {league}"
    
    return f"{index}. Матч не определен"

def create_all_matches_message(matches: List[Dict]) -> str:
    """Создать сообщение со всеми матчами"""
    if not matches:
        return """
🎯 <b>ПРЕДСТОЯЩИЕ МАТЧИ CS2</b>

📭 На данный момент нет запланированных матчей.

🔄 <i>Попробуйте обновить позже</i>
"""
    
    # Сортируем по времени
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        "🎯 <b>ВСЕ ПРЕДСТОЯЩИЕ МАТЧИ CS2</b>",
        "",
        f"📊 <i>Всего матчей: {len(matches)}</i>",
        "─" * 30,
        ""
    ]
    
    for i, match in enumerate(matches[:50], 1):  # Показываем первые 50
        lines.append(format_match_line(match, i))
        lines.append("")
    
    if len(matches) > 50:
        lines.append(f"\n📈 <i>... и еще {len(matches) - 50} матчей</i>")
    
    lines.append("\n⏱️ <i>Все время указано в MSK (Москва)</i>")
    
    return "\n".join(lines)

def create_live_message(matches: List[Dict]) -> str:
    """Создать сообщение с live матчами"""
    if not matches:
        return """
🔥 <b>LIVE МАТЧИ CS2</b>

📭 В данный момент нет матчей в прямом эфире.

📊 <i>Проверьте предстоящие матчи</i>
"""
    
    lines = [
        "🔥 <b>LIVE МАТЧИ CS2</b>",
        "",
        f"📡 <i>Матчей в эфире: {len(matches)}</i>",
        "─" * 30,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        lines.append(format_match_line(match, i, is_live=True))
        
        # Ссылка на стрим если есть
        stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
        if stream_url:
            lines.append(f"   └─ 📺 <a href='{stream_url}'>Смотреть трансляцию</a>")
        
        lines.append("")
    
    return "\n".join(lines)

def create_today_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на сегодня"""
    today = datetime.utcnow() + timedelta(hours=3)
    today_date = today.date()
    
    today_matches = []
    for match in matches:
        scheduled_at = match.get("scheduled_at")
        if scheduled_at:
            try:
                dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                dt_msk = dt_utc + timedelta(hours=3)
                if dt_msk.date() == today_date:
                    today_matches.append(match)
            except:
                continue
    
    if not today_matches:
        return """
📅 <b>МАТЧИ НА СЕГОДНЯ</b>

📭 Сегодня нет запланированных матчей.

🔄 <i>Проверьте матчи на завтра</i>
"""
    
    today_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА СЕГОДНЯ ({today.strftime('%d.%m')})</b>",
        "",
        f"📊 <i>Матчей сегодня: {len(today_matches)}</i>",
        "─" * 30,
        ""
    ]
    
    for i, match in enumerate(today_matches, 1):
        lines.append(format_match_line(match, i))
        lines.append("")
    
    return "\n".join(lines)

def create_tomorrow_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на завтра"""
    today = datetime.utcnow() + timedelta(hours=3)
    tomorrow_date = today.date() + timedelta(days=1)
    
    tomorrow_matches = []
    for match in matches:
        scheduled_at = match.get("scheduled_at")
        if scheduled_at:
            try:
                dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                dt_msk = dt_utc + timedelta(hours=3)
                if dt_msk.date() == tomorrow_date:
                    tomorrow_matches.append(match)
            except:
                continue
    
    if not tomorrow_matches:
        tomorrow_str = tomorrow_date.strftime('%d.%m')
        return f"""
📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>

📭 Завтра нет запланированных матчей.

🔄 <i>Проверьте другие дни</i>
"""
    
    tomorrow_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    tomorrow_str = tomorrow_date.strftime('%d.%m')
    lines = [
        f"📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>",
        "",
        f"📊 <i>Матчей завтра: {len(tomorrow_matches)}</i>",
        "─" * 30,
        ""
    ]
    
    for i, match in enumerate(tomorrow_matches, 1):
        lines.append(format_match_line(match, i))
        lines.append("")
    
    return "\n".join(lines)

# ========== ГЛОБАЛЬНЫЙ КЭШ МАТЧЕЙ ==========
matches_cache = []
cache_time = None
CACHE_TIMEOUT = 300  # 5 минут

async def get_cached_matches():
    """Получить матчи из кэша или загрузить новые"""
    global matches_cache, cache_time
    
    now = datetime.now()
    if cache_time and (now - cache_time).seconds < CACHE_TIMEOUT and matches_cache:
        logger.info("Использую кэшированные матчи")
        return matches_cache
    
    logger.info("Загрузка матчей с API...")
    matches_cache = await panda_api.get_all_cs2_matches()
    cache_time = now
    logger.info(f"Загружено {len(matches_cache)} матчей в кэш")
    
    return matches_cache

# ========== КОМАНДЫ БОТА ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
🎮 <b>CS2 PRO TRACKER</b>

Профессиональное отслеживание матчей Counter-Strike 2.
Актуальная информация, live трансляции, точное время.

👇 <b>Выберите раздел:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("matches"))
async def cmd_matches(message: types.Message):
    """Все матчи"""
    await show_all_matches(message)

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches_standalone(message)

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Матчи сегодня"""
    await show_today_matches(message)

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    """Матчи завтра"""
    await show_tomorrow_matches(message)

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
    """Обновить кэш"""
    global matches_cache, cache_time
    matches_cache = []
    cache_time = None
    
    await callback.answer("🔄 Кэш очищен, загружаю свежие данные...")
    await cmd_start(callback.message)

@dp.callback_query(F.data == "info")
async def handle_info(callback: types.CallbackQuery):
    """Информация"""
    info_text = """
ℹ️ <b>ИНФОРМАЦИЯ</b>

🎮 <b>CS2 PRO TRACKER</b>
Профессиональный бот для отслеживания всех матчей Counter-Strike 2.

📊 <b>Особенности:</b>
• Все предстоящие матчи (неограниченное количество)
• Live трансляции со счетом и картами
• Фильтрация по дням (сегодня/завтра)
• Автоматическое обновление данных

⚙️ <b>Техническая информация:</b>
• Источник: PandaScore API
• Кэширование: 5 минут
• Пагинация: до 100+ матчей
• Время: MSK (Москва)

📈 <b>Для профессионального использования</b>
"""
    
    await callback.message.edit_text(
        info_text,
        reply_markup=create_back_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "all_matches")
async def handle_all_matches(callback: types.CallbackQuery):
    """Все матчи"""
    await callback.answer("📊 Загружаю все матчи...")
    await show_all_matches_callback(callback)

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live матчи...")
    await show_live_matches_callback(callback)

@dp.callback_query(F.data == "today_matches")
async def handle_today_matches(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("📅 Смотрю расписание на сегодня...")
    await show_today_matches_callback(callback)

@dp.callback_query(F.data == "tomorrow_matches")
async def handle_tomorrow_matches(callback: types.CallbackQuery):
    """Матчи завтра"""
    await callback.answer("📅 Смотрю расписание на завтра...")
    await show_tomorrow_matches_callback(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_all_matches_callback(callback: types.CallbackQuery):
    """Все матчи через callback"""
    await show_all_matches(callback, is_callback=True)

async def show_all_matches(message_or_callback, is_callback: bool = False):
    """Показать все матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📊 <b>Загружаю все предстоящие матчи...</b>\n<i>Это может занять несколько секунд</i>")
    else:
        msg = await message_or_callback.answer("📊 <b>Загружаю все предстоящие матчи...</b>\n<i>Это может занять несколько секунд</i>")
    
    # Получаем матчи
    matches = await get_cached_matches()
    
    # Создаем сообщение
    message_text = create_all_matches_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="all_matches")],
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
    """Live матчи через callback"""
    await show_live_matches(callback, is_callback=True)

async def show_live_matches_standalone(message: types.Message):
    """Live матчи через команду"""
    await show_live_matches(message, is_callback=False)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("🔥 <b>Ищу матчи в прямом эфире...</b>")
    else:
        msg = await message_or_callback.answer("🔥 <b>Ищу матчи в прямом эфире...</b>")
    
    # Получаем live матчи
    matches = await panda_api.get_cs2_live()
    
    # Создаем сообщение
    message_text = create_live_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="live_matches")],
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

async def show_today_matches_callback(callback: types.CallbackQuery):
    """Матчи сегодня через callback"""
    await show_today_matches(callback, is_callback=True)

async def show_today_matches(message_or_callback, is_callback: bool = False):
    """Показать матчи на сегодня"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📅 <b>Смотрю расписание на сегодня...</b>")
    else:
        msg = await message_or_callback.answer("📅 <b>Смотрю расписание на сегодня...</b>")
    
    # Получаем матчи
    matches = await get_cached_matches()
    
    # Создаем сообщение
    message_text = create_today_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="today_matches")],
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

async def show_tomorrow_matches_callback(callback: types.CallbackQuery):
    """Матчи завтра через callback"""
    await show_tomorrow_matches(callback, is_callback=True)

async def show_tomorrow_matches(message_or_callback, is_callback: bool = False):
    """Показать матчи на завтра"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Статус загрузки
    if is_callback:
        await message_or_callback.message.edit_text("📅 <b>Смотрю расписание на завтра...</b>")
    else:
        msg = await message_or_callback.answer("📅 <b>Смотрю расписание на завтра...</b>")
    
    # Получаем матчи
    matches = await get_cached_matches()
    
    # Создаем сообщение
    message_text = create_tomorrow_message(matches)
    
    # Клавиатура
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="tomorrow_matches")],
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
    logger.info("🎮 Запускаю CS2 PRO TRACKER...")
    logger.info("📊 Загрузка всех предстоящих матчей")
    logger.info("🔥 Исправленный live запрос")
    
    if not PANDASCORE_TOKEN:
        logger.error("❌ Нет токена PandaScore!")
        return
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет токена Telegram!")
        return
    
    try:
        # Предварительная загрузка матчей
        logger.info("Предварительная загрузка матчей в кэш...")
        await get_cached_matches()
        
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())