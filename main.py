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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Константы игр
GAMES: Dict[str, Dict[str, Any]] = {
    "cs2": {
        "name": "CS2",
        "slug": "csgo",
        "emoji": "🔫",
        "color": "#FF6B00"
    },
    "dota2": {
        "name": "DOTA 2",
        "slug": "dota-2",
        "emoji": "⚔️",
        "color": "#E60000"
    }
}

class PandaScoreAPI:
    """Умный клиент для PandaScore API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Any] = {}
        self.cache_timeout = 60  # секунды
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Получение или создание сессии"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    async def make_request(self, url: str, params: Optional[Dict] = None) -> Any:
        """Универсальный метод запроса"""
        cache_key = f"{url}:{params}"
        
        # Проверяем кэш
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if (datetime.now() - timestamp).seconds < self.cache_timeout:
                return cached_data
        
        try:
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Сохраняем в кэш
                    self.cache[cache_key] = (data, datetime.now())
                    return data
                elif response.status == 404:
                    logger.warning(f"404 Not Found: {url}")
                    return []
                else:
                    logger.error(f"API Error {response.status}: {await response.text()}")
                    return []
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_upcoming_matches(self, game_slug: str, limit: int = 6) -> List[Dict]:
        """Получение предстоящих матчей"""
        url = f"{self.base_url}/{game_slug}/matches/upcoming"
        params = {
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        return await self.make_request(url, params)
    
    async def get_running_matches(self, game_slug: str) -> List[Dict]:
        """Получение текущих матчей"""
        url = f"{self.base_url}/{game_slug}/matches/running"
        params = {"per_page": 5}
        return await self.make_request(url, params)
    
    async def get_videogames(self) -> List[Dict]:
        """Получение списка всех игр (для дебага)"""
        url = f"{self.base_url}/videogames"
        return await self.make_request(url)
    
    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API клиента
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

def create_main_menu() -> InlineKeyboardMarkup:
    """Создание главного меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔫 CS2 РАСПИСАНИЕ", callback_data="matches_cs2"),
            InlineKeyboardButton(text="⚔️ DOTA 2 РАСПИСАНИЕ", callback_data="matches_dota2")
        ],
        [
            InlineKeyboardButton(text="🎮 LIVE ТРАНСЛЯЦИИ", callback_data="live_all"),
            InlineKeyboardButton(text="📊 ВСЕ МАТЧИ", callback_data="all_matches")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh_main")
        ]
    ])

def create_match_keyboard(match_id: int, game: str, has_stream: bool = False, stream_url: str = "") -> InlineKeyboardMarkup:
    """Создание клавиатуры для матча"""
    buttons = []
    
    if has_stream and stream_url:
        buttons.append([
            InlineKeyboardButton(text="📺 СМОТРЕТЬ ТРАНСЛЯЦИЮ", url=stream_url)
        ])
    
    buttons.extend([
        [
            InlineKeyboardButton(text="🎮 ЕЩЕ МАТЧИ", callback_data=f"matches_{game}"),
            InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh_main")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_live_keyboard(stream_url: str = "") -> InlineKeyboardMarkup:
    """Создание клавиатуры для live матча"""
    buttons = []
    
    if stream_url:
        buttons.append([
            InlineKeyboardButton(text="🔥 ПЕРЕЙТИ К ТРАНСЛЯЦИИ", url=stream_url)
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🔴 ДРУГИЕ LIVE", callback_data="live_all"),
        InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time_remaining(scheduled_at: str) -> str:
    """Форматирование оставшегося времени"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        time_diff = dt_msk - now_msk
        
        if time_diff.total_seconds() <= 0:
            return "🔴 НАЧИНАЕТСЯ"
        
        days = time_diff.days
        hours = time_diff.seconds // 3600
        minutes = (time_diff.seconds % 3600) // 60
        
        if days > 0:
            return f"⏳ ЧЕРЕЗ {days} ДН."
        elif hours > 0:
            return f"⏳ ЧЕРЕЗ {hours} Ч."
        elif minutes > 0:
            return f"⏳ ЧЕРЕЗ {minutes} МИН."
        else:
            return "⏳ СКОРО"
            
    except Exception as e:
        logger.error(f"Time formatting error: {e}")
        return "⏳ СКОРО"

def format_match_time(scheduled_at: str) -> str:
    """Форматирование времени матча"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        today = datetime.utcnow() + timedelta(hours=3)
        
        if dt_msk.date() == today.date():
            day_str = "СЕГОДНЯ"
        elif dt_msk.date() == today.date() + timedelta(days=1):
            day_str = "ЗАВТРА"
        else:
            weekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
            day_str = f"{dt_msk.strftime('%d.%m')} ({weekdays[dt_msk.weekday()]})"
        
        time_str = dt_msk.strftime("%H:%M")
        return f"📅 {day_str} | 🕐 {time_str} МСК"
        
    except Exception as e:
        logger.error(f"Match time error: {e}")
        return "📅 ВРЕМЯ УТОЧНЯЕТСЯ"

def create_bar_header(title: str, emoji: str = "🍻") -> str:
    """Создание заголовка в стиле бара"""
    border = "═" * 35
    return f"""
╔{border}╗
║{emoji} {title.center(33)} {emoji}║
╚{border}╝
    """

def create_match_card(match: Dict, game_info: Dict, is_live: bool = False) -> str:
    """Создание карточки матча"""
    # Получаем данные
    league = match.get("league", {}).get("name", "ТУРНИР")
    opponents = match.get("opponents", [])
    
    # Команды
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_display = format_match_time(scheduled_at) if scheduled_at else "📅 ВРЕМЯ УТОЧНЯЕТСЯ"
    
    # Статус
    if is_live:
        status = "🔴 ПРЯМОЙ ЭФИР"
        remaining = "🔥 ИДЕТ СЕЙЧАС"
    else:
        status = "🟢 БУДЕТ СКОРО"
        remaining = format_time_remaining(scheduled_at) if scheduled_at else ""
    
    # Создаем карточку
    card = create_bar_header(f"{game_info['emoji']} {game_info['name']}")
    
    card += f"""
🎮 <b>{team1}</b>
   ⚔️  VS  ⚔️
🎮 <b>{team2}</b>

🏆 <i>{league}</i>

{time_display}
{remaining}
{status}

📺 <i>Трансляция на всех экранах бара</i>
    """
    
    return card.strip()

def create_live_card(match: Dict, game_info: Dict) -> str:
    """Создание карточки live матча"""
    league = match.get("league", {}).get("name", "LIVE ТУРНИР")
    opponents = match.get("opponents", [])
    
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    card = create_bar_header(f"🔴 LIVE {game_info['name']}", "🔥")
    
    card += f"""
⚡️ <b>{team1}</b>
   🆚  LIVE  🆚
⚡️ <b>{team2}</b>

🏆 <i>{league}</i>

🔥 <b>ПРЯМАЯ ТРАНСЛЯЦИЯ!</b>
🎧 <i>Звук включен на всех колонках</i>
🍻 <i>Бармен готовит напитки</i>

💬 <i>Комментарий в реальном времени</i>
    """
    
    return card.strip()

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветственное сообщение"""
    welcome = create_bar_header("КИБЕРСПОРТ БАР", "🎮")
    
    welcome += f"""

Добро пожаловать в киберспорт бар! 🍻

Здесь мы следим за лучшими матчами:
🔫 Counter-Strike 2
⚔️ Dota 2

📺 Наши экраны всегда показывают:
• Live трансляции
• Расписание матчей
• Повторы лучших моментов

👇 Выбери что тебя интересует:
    """
    
    await message.answer(
        welcome,
        reply_markup=create_main_menu(),
        disable_web_page_preview=True
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """CS2 матчи через команду"""
    await show_matches(message, "cs2")

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Dota 2 матчи через команду"""
    await show_matches(message, "dota2")

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live трансляции через команду"""
    await message.answer("🔍 Ищу live трансляции...")
    await show_all_live_matches_standalone(message)

@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    """Дебаг команда для проверки API"""
    await message.answer("🔄 Проверяю подключение к PandaScore...")
    
    # Проверяем доступные игры
    games = await panda_api.get_videogames()
    
    if not games:
        await message.answer("❌ Не удалось получить список игр. Проверь токен.")
        return
    
    games_list = []
    for game in games[:10]:  # Первые 10 игр
        games_list.append(f"{game.get('id')}: {game.get('name')} (slug: {game.get('slug')})")
    
    debug_msg = create_bar_header("DEBUG INFO", "🐛")
    debug_msg += f"\n\nНайдено игр: {len(games)}\n\n"
    debug_msg += "\n".join(games_list[:5])  # Показываем первые 5
    
    await message.answer(debug_msg, disable_web_page_preview=True)

@dp.callback_query(F.data == "refresh_main")
async def handle_refresh_main(callback: types.CallbackQuery):
    """Обновление главного меню"""
    welcome = create_bar_header("КИБЕРСПОРТ БАР", "🎮")
    welcome += "\n\n👇 Выбери что тебя интересует:"
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_menu(),
        disable_web_page_preview=True
    )
    await callback.answer("✅ Обновлено")

@dp.callback_query(F.data == "all_matches")
async def handle_all_matches(callback: types.CallbackQuery):
    """Показать все матчи (CS2 + Dota)"""
    await callback.message.edit_text("🎮 Собираю все матчи...")
    await show_all_matches(callback)

@dp.callback_query(F.data.startswith("matches_"))
async def handle_matches_callback(callback: types.CallbackQuery):
    """Обработчик матчей по играм"""
    game = callback.data.split("_")[1]
    await show_matches_callback(callback, game)

@dp.callback_query(F.data == "live_all")
async def handle_live_all(callback: types.CallbackQuery):
    """Все live трансляции"""
    await callback.message.edit_text("🔍 Ищу live трансляции...")
    await show_all_live_matches(callback)

# ========== ОСНОВНАЯ ЛОГИКА ==========

async def show_matches(message_or_callback, game: str):
    """Показать матчи для указанной игры"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    if game not in GAMES:
        error_msg = create_bar_header("ОШИБКА", "❌")
        error_msg += "\n\n❌ Игра не найдена в системе"
        await bot.send_message(chat_id, error_msg)
        return
    
    game_info = GAMES[game]
    
    # Статус загрузки
    loading_msg = create_bar_header(f"{game_info['emoji']} {game_info['name']}", "⏳")
    loading_msg += "\n\n📡 Загружаю расписание матчей..."
    
    if is_callback:
        await callback.message.edit_text(loading_msg)
    else:
        await message_or_callback.answer(loading_msg)
    
    # Получаем матчи
    matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=6)
    
    if not matches:
        no_matches = create_bar_header(f"{game_info['emoji']} {game_info['name']}", "📭")
        no_matches += "\n\n📭 Матчей не найдено\n\n"
        no_matches += "Попробуй позже или посмотри другие игры"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ", callback_data=f"matches_{game}")],
            [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh_main")]
        ])
        
        if is_callback:
            await callback.message.edit_text(no_matches, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, no_matches, reply_markup=keyboard)
        return
    
    # Отправляем заголовок
    header = create_bar_header(f"{game_info['emoji']} {game_info['name']} - РАСПИСАНИЕ", "📅")
    header += f"\n\nНайдено матчей: {len(matches)}\n"
    
    if is_callback:
        await callback.message.edit_text(header)
    else:
        await bot.send_message(chat_id, header)
    
    # Отправляем матчи
    for match in matches:
        match_card = create_match_card(match, game_info, is_live=False)
        
        # Ищем ссылку на стрим
        stream_url = match.get("official_stream_url") or match.get("live_url") or ""
        has_stream = bool(stream_url)
        
        keyboard = create_match_keyboard(
            match.get("id", 0),
            game,
            has_stream,
            stream_url
        )
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_card,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)
    
    if is_callback:
        await callback.answer(f"✅ {len(matches)} матчей")

async def show_matches_callback(callback: types.CallbackQuery, game: str):
    """Показать матчи через callback"""
    await show_matches(callback, game)

async def show_all_matches(callback: types.CallbackQuery):
    """Показать все матчи (CS2 + Dota)"""
    await callback.message.edit_text("🎮 Собираю все матчи...")
    
    all_matches = []
    
    # Собираем матчи со всех игр
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=3)
        for match in matches:
            match["game_info"] = game_info
            all_matches.append(match)
    
    if not all_matches:
        no_matches = create_bar_header("ВСЕ МАТЧИ", "📭")
        no_matches += "\n\n📭 Нет запланированных матчей"
        
        await callback.message.edit_text(
            no_matches,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="all_matches")],
                [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh_main")]
            ])
        )
        await callback.answer()
        return
    
    # Сортируем по времени
    all_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    # Заголовок
    header = create_bar_header("ВСЕ МАТЧИ", "🎮")
    header += f"\n\nВсего матчей: {len(all_matches)}\n"
    
    await callback.message.edit_text(header)
    
    # Показываем матчи
    for match in all_matches[:8]:  # Ограничиваем 8 матчами
        game_info = match.pop("game_info")
        match_card = create_match_card(match, game_info, is_live=False)
        
        stream_url = match.get("official_stream_url") or match.get("live_url") or ""
        has_stream = bool(stream_url)
        
        keyboard = create_match_keyboard(
            match.get("id", 0),
            game_info["slug"],
            has_stream,
            stream_url
        )
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=match_card,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)
    
    await callback.answer(f"🎮 {len(all_matches)} матчей")

async def show_all_live_matches(callback: types.CallbackQuery):
    """Показать все live трансляции"""
    all_live_matches = []
    
    # Проверяем все игры
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_live_matches.append(match)
    
    if not all_live_matches:
        no_live = create_bar_header("LIVE ТРАНСЛЯЦИИ", "📭")
        no_live += "\n\n📭 Сейчас нет live трансляций\n\n"
        no_live += "Проверь расписание матчей 👇"
        
        await callback.message.edit_text(
            no_live,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔫 CS2 РАСПИСАНИЕ", callback_data="matches_cs2")],
                [InlineKeyboardButton(text="⚔️ DOTA 2 РАСПИСАНИЕ", callback_data="matches_dota2")],
                [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh_main")]
            ])
        )
        await callback.answer()
        return
    
    # Заголовок
    header = create_bar_header("LIVE ТРАНСЛЯЦИИ", "🔴")
    header += f"\n\nСейчас в эфире: {len(all_live_matches)} матчей\n"
    
    await callback.message.edit_text(header)
    
    # Показываем live матчи
    for match in all_live_matches:
        game_info = match.pop("game_info")
        live_card = create_live_card(match, game_info)
        
        # Ищем ссылку на стрим
        stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url") or ""
        
        keyboard = create_live_keyboard(stream_url)
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=live_card,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)
    
    await callback.answer(f"🔴 {len(all_live_matches)} live")

async def show_all_live_matches_standalone(message: types.Message):
    """Live трансляции через команду"""
    all_live_matches = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_live_matches.append(match)
    
    if not all_live_matches:
        no_live = create_bar_header("LIVE ТРАНСЛЯЦИИ", "📭")
        no_live += "\n\n📭 Сейчас нет live трансляций"
        await message.answer(no_live)
        return
    
    header = create_bar_header("LIVE ТРАНСЛЯЦИИ", "🔴")
    header += f"\n\nСейчас в эфире: {len(all_live_matches)} матчей\n"
    
    await message.answer(header)
    
    for match in all_live_matches[:3]:  # Ограничиваем 3 матчами
        game_info = match.pop("game_info")
        live_card = create_live_card(match, game_info)
        
        stream_url = match.get("official_stream_url") or match.get("live_url") or ""
        
        keyboard = create_live_keyboard(stream_url)
        
        await message.answer(
            live_card,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

# ========== ЗАПУСК БОТА ==========

async def on_startup():
    """Действия при запуске"""
    logger.info("=" * 50)
    logger.info("🎮 КИБЕРСПОРТ БАР БОТ ЗАПУЩЕН")
    logger.info("=" * 50)
    
    # Проверяем доступные игры
    logger.info("🔍 Проверяю доступные игры...")
    games = await panda_api.get_videogames()
    
    if games:
        found_games = []
        for game in games:
            if game.get("slug") in ["csgo", "dota-2"]:
                found_games.append(f"{game.get('name')} (slug: {game.get('slug')})")
        
        if found_games:
            logger.info(f"✅ Найдены игры: {', '.join(found_games)}")
        else:
            logger.warning("⚠️ CS2/Dota 2 не найдены в списке игр")
            
            # Показываем что есть
            all_games = [f"{g.get('slug')}" for g in games[:5]]
            logger.info(f"Доступные игры: {', '.join(all_games)}")
    else:
        logger.error("❌ Не удалось получить список игр. Проверь токен.")

async def on_shutdown():
    """Действия при выключении"""
    logger.info("Выключаю бота...")
    await panda_api.close()

async def main():
    """Главная функция"""
    await on_startup()
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    # Проверка токенов
    if not PANDASCORE_TOKEN:
        logger.error("❌ PANDASCORE_TOKEN не установлен!")
        exit(1)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        exit(1)
    
    # Запуск бота
    asyncio.run(main())