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
    
    async def get_cs2_matches(self, days_ahead: int = 2):
        """Получить матчи на ближайшие дни"""
        try:
            session = await self.get_session()
            
            # Берем матчи на указанное количество дней вперед
            all_matches = []
            page = 1
            
            while True:
                url = f"{self.base_url}/csgo/matches"
                params = {
                    "per_page": 50,
                    "sort": "scheduled_at",
                    "page": page,
                    "filter[status]": "not_started,running"
                }
                
                logger.info(f"Запрос страницы {page} матчей...")
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        matches = await response.json()
                        if not matches:
                            break
                        
                        # Фильтруем по дате
                        now = datetime.utcnow()
                        cutoff_date = now + timedelta(days=days_ahead)
                        
                        filtered_matches = []
                        for match in matches:
                            scheduled_at = match.get("scheduled_at")
                            if scheduled_at:
                                try:
                                    match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                    if match_time <= cutoff_date:
                                        filtered_matches.append(match)
                                except:
                                    continue
                        
                        all_matches.extend(filtered_matches)
                        
                        # Если нашли достаточно матчей или это последняя страница
                        if len(matches) < 50 or len(all_matches) >= 30:
                            break
                        
                        page += 1
                    else:
                        logger.error(f"Ошибка {response.status}")
                        break
                        
            logger.info(f"Получено матчей: {len(all_matches)}")
            return all_matches
            
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
            return []
    
    async def get_cs2_live(self):
        """Получить live матчи - упрощенный запрос"""
        try:
            session = await self.get_session()
            
            # Простой запрос к running матчам
            url = f"{self.base_url}/csgo/matches"
            params = {
                "filter[status]": "running",
                "per_page": 10,
                "sort": "-begin_at"
            }
            
            logger.info("Запрос live матчей...")
            
            async with session.get(url, params=params) as response:
                logger.info(f"Статус live: {response.status}")
                
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Найдено live матчей: {len(matches)}")
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка live: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== ПРОФЕССИОНАЛЬНЫЙ ДИЗАЙН ==========

def create_main_keyboard():
    """Главное меню - только сегодня, завтра, live"""
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
    """Форматирование времени"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        # Форматируем время
        return dt_msk.strftime("%H:%M")
            
    except:
        return "Скоро"

def get_match_score(match: Dict) -> tuple:
    """Получить счет матча - упрощенная версия"""
    opponents = match.get("opponents", [])
    
    if len(opponents) >= 2:
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        # Пытаемся получить счет из разных мест
        team1_score = team1.get("score", 0)
        team2_score = team2.get("score", 0)
        
        # Если нет в opponent, ищем в других местах
        if team1_score == 0 and team2_score == 0:
            results = match.get("results", [])
            if results and len(results) >= 2:
                team1_score = results[0].get("score", 0)
                team2_score = results[1].get("score", 0)
        
        # Получаем карту
        map_data = match.get("map", {})
        if isinstance(map_data, dict):
            map_name = map_data.get("name", "")
        else:
            map_name = str(map_data) if map_data else ""
        
        if not map_name:
            map_name = "?"
        
        return team1_score, team2_score, map_name
    
    return 0, 0, "?"

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
        return f"{team1_emoji} <b>{team1_name}</b>  vs  {team2_emoji} <b>{team2_name}</b>\n   ⏰ {time_str}  |  🏆 {league}"
    
    return "Матч не определен"

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
        
        # Получаем счет
        score1, score2, map_name = get_match_score(match)
        league = match.get("league", {}).get("name", "")
        
        return f"{team1_emoji} <b>{team1_name}</b>  {score1}:{score2}  {team2_emoji} <b>{team2_name}</b>\n   🗺️ {map_name}  |  🏆 {league}"
    
    return "Матч не определен"

def create_today_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на сегодня"""
    today = datetime.utcnow() + timedelta(hours=3)
    today_date = today.date()
    
    # Фильтруем матчи на сегодня
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
    
    # Сортируем по времени
    today_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    if not today_matches:
        return f"""
📅 <b>МАТЧИ НА СЕГОДНЯ ({today.strftime('%d.%m')})</b>

📭 Сегодня нет запланированных матчей CS2.

👉 <i>Проверьте матчи на завтра</i>
"""
    
    lines = [
        f"📅 <b>МАТЧИ НА СЕГОДНЯ ({today.strftime('%d.%m')})</b>",
        "",
        f"📊 <i>Найдено матчей: {len(today_matches)}</i>",
        "─" * 35,
        ""
    ]
    
    for i, match in enumerate(today_matches, 1):
        lines.append(f"{i}. {format_upcoming_match(match, i)}")
        lines.append("")
    
    lines.append(f"⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_tomorrow_message(matches: List[Dict]) -> str:
    """Создать сообщение с матчами на завтра"""
    today = datetime.utcnow() + timedelta(hours=3)
    tomorrow_date = today.date() + timedelta(days=1)
    
    # Фильтруем матчи на завтра
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
    
    # Сортируем по времени
    tomorrow_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    tomorrow_str = tomorrow_date.strftime('%d.%m')
    
    if not tomorrow_matches:
        return f"""
📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>

📭 Завтра нет запланированных матчей CS2.

👉 <i>Проверьте матчи на сегодня</i>
"""
    
    lines = [
        f"📅 <b>МАТЧИ НА ЗАВТРА ({tomorrow_str})</b>",
        "",
        f"📊 <i>Найдено матчей: {len(tomorrow_matches)}</i>",
        "─" * 35,
        ""
    ]
    
    for i, match in enumerate(tomorrow_matches, 1):
        lines.append(f"{i}. {format_upcoming_match(match, i)}")
        lines.append("")
    
    lines.append(f"⏱️ <i>Все время указано в MSK</i>")
    
    return "\n".join(lines)

def create_live_message(matches: List[Dict]) -> str:
    """Создать сообщение с live матчами"""
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
        "─" * 35,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        lines.append(f"{i}. {format_live_match(match, i)}")
        
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
    await callback.answer("✅ Обновлено")

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
    matches = await panda_api.get_cs2_matches(days_ahead=1)  # Только сегодня
    
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
    matches = await panda_api.get_cs2_matches(days_ahead=2)  # Сегодня и завтра
    
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
    matches = await panda_api.get_cs2_live()
    
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
    logger.info("📅 Показываю только сегодня/завтра")
    logger.info("🔥 Упрощенный live запрос")
    
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