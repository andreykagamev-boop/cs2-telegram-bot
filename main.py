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

# Константы игр - проверенные slug
GAMES = {
    "cs2": {
        "name": "Counter-Strike 2",
        "slug": "csgo",  # PandaScore использует csgo для CS2
        "emoji": "🔫",
        "color": "#e74c3c"
    },
    "dota2": {
        "name": "Dota 2",
        "slug": "dota-2",  # Правильный slug для Dota 2
        "emoji": "⚔️",
        "color": "#3498db"
    }
}

class PandaScoreAPI:
    """Клиент для работы с PandaScore API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def get_upcoming_matches(self, game_slug: str, limit: int = 5):
        """Получить предстоящие матчи"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{game_slug}/matches/upcoming"
            
            async with session.get(url, params={
                "per_page": limit,
                "sort": "scheduled_at",
                "page": 1
            }) as response:
                
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    logger.warning(f"Game not found: {game_slug}")
                    return []
                else:
                    logger.error(f"API Error {response.status}: {await response.text()}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting matches: {e}")
            return []
    
    async def get_running_matches(self, game_slug: str):
        """Получить текущие матчи"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{game_slug}/matches/running"
            
            async with session.get(url, params={"per_page": 5}) as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            logger.error(f"Error getting running matches: {e}")
            return []
    
    async def get_videogames(self):
        """Получить список всех доступных игр (для дебага)"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/videogames"
            
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            logger.error(f"Error getting games: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

def create_main_keyboard():
    """Создание главного меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 CS2 Матчи", callback_data="matches_cs2"),
            InlineKeyboardButton(text="⚔️ Dota 2 Матчи", callback_data="matches_dota2")
        ],
        [
            InlineKeyboardButton(text="🔥 Live Матчи", callback_data="live_matches")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")
        ]
    ])
    return keyboard

def create_match_keyboard(match: Dict, game: str):
    """Создание клавиатуры для матча"""
    buttons = []
    
    # Добавляем ссылку на трансляцию если есть
    stream_url = match.get("official_stream_url") or match.get("live_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="📺 Смотреть трансляцию", url=stream_url)])
    
    # Основные кнопки
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"matches_{game}"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_live_keyboard(match: Dict):
    """Создание клавиатуры для live матча"""
    buttons = []
    
    # Обязательно добавляем ссылку на трансляцию для live
    stream_url = match.get("official_stream_url") or match.get("live_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="🔥 Смотреть LIVE", url=stream_url)])
    else:
        # Если нет ссылки, пытаемся найти в других полях
        for key in ["stream_url", "video_url", "url"]:
            if match.get(key):
                buttons.append([InlineKeyboardButton(text="🔥 Смотреть LIVE", url=match.get(key))])
                break
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="live_matches"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time(scheduled_at: str) -> str:
    """Форматирование времени в MSK"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)  # Конвертируем в MSK
        
        today = datetime.utcnow() + timedelta(hours=3)
        
        # Определяем день
        if dt_msk.date() == today.date():
            day_str = "Сегодня"
        elif dt_msk.date() == today.date() + timedelta(days=1):
            day_str = "Завтра"
        else:
            weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            day_str = f"{dt_msk.strftime('%d.%m')} ({weekdays[dt_msk.weekday()]})"
        
        time_str = dt_msk.strftime("%H:%M")
        return f"{day_str} в {time_str} MSK"
        
    except Exception as e:
        logger.error(f"Time formatting error: {e}")
        return "Скоро"

def format_match(match: Dict, game_info: Dict, is_live: bool = False) -> str:
    """Форматирование информации о матче"""
    # Основная информация
    league = match.get("league", {}).get("name", "Турнир")
    tournament = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_display = format_time(scheduled_at) if scheduled_at else "Скоро"
    
    # Статус
    if is_live:
        status = "🟢 <b>LIVE СЕЙЧАС</b>"
        time_display = "🔥 <b>ПРЯМОЙ ЭФИР</b>"
    else:
        status = "🕐 <b>Будет скоро</b>"
    
    # Формируем сообщение
    message = f"""
<b>{game_info['emoji']} {game_info['name']}</b>

🏆 <b>{league}</b>
{tournament and f'📋 {tournament}' or ''}

⚔️ <b>{team1}</b>
   vs
⚔️ <b>{team2}</b>

🕐 {time_display}
{status}
"""
    
    return message.strip()

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    welcome_text = """
<b>🎮 Каппер Бармен</b>

Привет! Я помогу тебе следить за киберспортивными матчами.

📊 <b>Доступные игры:</b>
• Counter-Strike 2 (CS2)
• Dota 2

👇 <b>Выбери что интересует:</b>
"""
    
    await message.answer(
        welcome_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """CS2 матчи"""
    await show_matches(message, "cs2")

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Dota 2 матчи"""
    await show_matches(message, "dota2")

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches_standalone(message)

@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    """Дебаг команда - проверка доступных игр"""
    await message.answer("🔄 Проверяю доступные игры...")
    
    games = await panda_api.get_videogames()
    
    if not games:
        await message.answer("❌ Не удалось получить список игр. Проверь токен.")
        return
    
    # Ищем CS2 и Dota 2
    cs2_found = False
    dota_found = False
    available_games = []
    
    for game in games:
        slug = game.get("slug", "")
        name = game.get("name", "")
        
        if "csgo" in slug or "counter-strike" in name.lower():
            cs2_found = True
            available_games.append(f"✅ CS2: {name} (slug: {slug})")
        
        if "dota" in slug.lower() or "dota" in name.lower():
            dota_found = True
            available_games.append(f"✅ Dota 2: {name} (slug: {slug})")
        
        # Добавляем другие игры для информации
        if len(available_games) < 10:  # Ограничиваем список
            available_games.append(f"📌 {name} (slug: {slug})")
    
    debug_message = "<b>🔧 Результат проверки:</b>\n\n"
    
    if cs2_found:
        debug_message += "🎯 CS2: <b>ДОСТУПНО</b>\n"
    else:
        debug_message += "🎯 CS2: <b>НЕ ДОСТУПНО</b>\n"
    
    if dota_found:
        debug_message += "⚔️ Dota 2: <b>ДОСТУПНО</b>\n"
    else:
        debug_message += "⚔️ Dota 2: <b>НЕ ДОСТУПНО</b>\n"
    
    debug_message += f"\n📊 Всего игр в API: {len(games)}\n\n"
    debug_message += "<b>Доступные игры:</b>\n"
    debug_message += "\n".join(available_games[:8])  # Показываем первые 8
    
    await message.answer(debug_message, disable_web_page_preview=True)

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    welcome_text = """
<b>🎮 Каппер Бармен</b>

👇 <b>Выбери что интересует:</b>
"""
    
    await callback.message.edit_text(
        welcome_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновление главного меню"""
    await handle_main_menu(callback)
    await callback.answer("✅ Обновлено")

@dp.callback_query(F.data == "matches_cs2")
async def handle_cs2_matches(callback: types.CallbackQuery):
    """CS2 матчи через callback"""
    await callback.answer("🎯 Загружаю CS2 матчи...")
    await show_matches_callback(callback, "cs2")

@dp.callback_query(F.data == "matches_dota2")
async def handle_dota2_matches(callback: types.CallbackQuery):
    """Dota 2 матчи через callback"""
    await callback.answer("⚔️ Загружаю Dota 2 матчи...")
    await show_matches_callback(callback, "dota2")

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи через callback"""
    await callback.answer("🔥 Ищу live матчи...")
    await show_live_matches_callback(callback)

# ========== ФУНКЦИИ ПОКАЗА МАТЧЕЙ ==========

async def show_matches(message_or_callback, game: str):
    """Показать матчи для игры"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    if game not in GAMES:
        error_msg = "❌ Игра не найдена"
        if is_callback:
            await message_or_callback.message.edit_text(error_msg)
        else:
            await message_or_callback.answer(error_msg)
        return
    
    game_info = GAMES[game]
    
    # Показываем загрузку
    loading_text = f"🔄 Загружаю матчи {game_info['emoji']} {game_info['name']}..."
    
    if is_callback:
        await message_or_callback.message.edit_text(loading_text)
    else:
        msg = await message_or_callback.answer(loading_text)
    
    # Получаем матчи
    matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=5)
    
    if not matches:
        no_matches_text = f"📭 Нет предстоящих матчей по {game_info['name']}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"matches_{game}")],
            [InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches_text, reply_markup=keyboard)
        else:
            await msg.edit_text(no_matches_text, reply_markup=keyboard)
        return
    
    # Показываем заголовок
    header = f"<b>{game_info['emoji']} {game_info['name']} - Ближайшие матчи</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем каждый матч
    for i, match in enumerate(matches[:5]):
        match_text = format_match(match, game_info)
        keyboard = create_match_keyboard(match, game)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)
    
    if is_callback:
        await callback.answer(f"✅ Загружено {len(matches)} матчей")

async def show_matches_callback(callback: types.CallbackQuery, game: str):
    """Показать матчи через callback"""
    await show_matches(callback, game)

async def show_live_matches_callback(callback: types.CallbackQuery):
    """Показать live матчи через callback"""
    await show_live_matches(callback, is_callback=True)

async def show_live_matches_standalone(message: types.Message):
    """Показать live матчи через команду"""
    await show_live_matches(message, is_callback=False)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    # Показываем загрузку
    loading_text = "🔍 Ищу live матчи..."
    
    if is_callback:
        await message_or_callback.message.edit_text(loading_text)
    else:
        msg = await message_or_callback.answer(loading_text)
    
    # Ищем live матчи для всех игр
    all_live_matches = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_live_matches.append(match)
    
    if not all_live_matches:
        no_live_text = "📭 Сейчас нет live матчей"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data="live_matches")],
            [InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_live_text, reply_markup=keyboard)
        else:
            await msg.edit_text(no_live_text, reply_markup=keyboard)
        return
    
    # Показываем заголовок
    header = f"<b>🔥 LIVE МАТЧИ ПРЯМО СЕЙЧАС</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем live матчи
    for match in all_live_matches[:5]:
        game_info = match.pop("game_info")
        match_text = format_match(match, game_info, is_live=True)
        keyboard = create_live_keyboard(match)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)
    
    if is_callback:
        await callback.answer(f"🔥 Найдено {len(all_live_matches)} live матчей")

# ========== ЗАПУСК БОТА ==========

async def main():
    """Основная функция запуска"""
    logger.info("🚀 Запускаю Каппер Бармен...")
    
    # Проверяем доступные игры при запуске
    logger.info("🔍 Проверяю доступные игры...")
    games = await panda_api.get_videogames()
    
    if games:
        logger.info(f"📊 Найдено игр: {len(games)}")
        
        # Ищем CS2 и Dota 2
        cs2_slugs = []
        dota_slugs = []
        
        for game in games:
            slug = game.get("slug", "").lower()
            name = game.get("name", "").lower()
            
            if "csgo" in slug or "counter-strike" in name:
                cs2_slugs.append(f"{game.get('name')} (slug: {game.get('slug')})")
            
            if "dota" in slug or "dota" in name:
                dota_slugs.append(f"{game.get('name')} (slug: {game.get('slug')})")
        
        if cs2_slugs:
            logger.info(f"✅ CS2 доступен: {cs2_slugs[0]}")
        else:
            logger.warning("❌ CS2 не найден в доступных играх")
        
        if dota_slugs:
            logger.info(f"✅ Dota 2 доступен: {dota_slugs[0]}")
        else:
            logger.warning("❌ Dota 2 не найден в доступных играх")
            
            # Показываем какие игры есть
            other_games = [g.get('slug') for g in games[:5]]
            logger.info(f"📌 Доступные игры: {', '.join(other_games)}")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    # Проверка токенов
    if not PANDASCORE_TOKEN:
        logger.error("❌ PANDASCORE_TOKEN не установлен!")
        exit(1)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        exit(1)
    
    # Запуск
    asyncio.run(main())