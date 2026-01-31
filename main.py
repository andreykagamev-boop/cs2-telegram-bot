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

# Только нужные игры
GAMES = {
    "cs2": {
        "name": "Counter-Strike 2",
        "slug": "csgo",
        "emoji": "🔫",
        "id": 1  # Предполагаемый ID CS:GO
    },
    "dota2": {
        "name": "Dota 2",
        "slug": "dota-2",
        "emoji": "⚔️",
        "id": 4  # Предполагаемый ID Dota 2
    }
}

class PandaScoreAPI:
    """Улучшенный клиент для PandaScore API"""
    
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
        """Универсальный метод запроса с логированием"""
        try:
            session = await self.get_session()
            
            # Логируем запрос
            logger.info(f"Making request to: {url}")
            if params:
                logger.info(f"Params: {params}")
            
            async with session.get(url, params=params) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Success: {len(data) if isinstance(data, list) else 'object'} items")
                    return data
                else:
                    logger.error(f"API Error {response.status}: {response_text[:200]}")
                    
                    # Пробуем другой endpoint если 404
                    if response.status == 404:
                        logger.warning(f"Endpoint not found: {url}")
                    
                    return []
                    
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_upcoming_matches_by_slug(self, game_slug: str, limit: int = 5):
        """Получить матчи по slug игры"""
        url = f"{self.base_url}/{game_slug}/matches/upcoming"
        params = {
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        return await self.make_request(url, params)
    
    async def get_upcoming_matches_by_id(self, game_id: int, limit: int = 5):
        """Получить матчи по ID игры - альтернативный метод"""
        url = f"{self.base_url}/matches/upcoming"
        params = {
            "filter[videogame_id]": game_id,
            "per_page": limit,
            "sort": "scheduled_at",
            "page": 1
        }
        return await self.make_request(url, params)
    
    async def get_running_matches_by_slug(self, game_slug: str):
        """Получить live матчи по slug"""
        url = f"{self.base_url}/{game_slug}/matches/running"
        params = {"per_page": 5}
        return await self.make_request(url, params)
    
    async def get_running_matches_by_id(self, game_id: int):
        """Получить live матчи по ID игры"""
        url = f"{self.base_url}/matches/running"
        params = {
            "filter[videogame_id]": game_id,
            "per_page": 5
        }
        return await self.make_request(url, params)
    
    async def get_today_matches(self, game_slug: str):
        """Получить матчи на сегодня"""
        url = f"{self.base_url}/{game_slug}/matches"
        today = datetime.utcnow().date()
        
        params = {
            "filter[begin_at]": today.isoformat(),
            "per_page": 10,
            "sort": "scheduled_at"
        }
        return await self.make_request(url, params)
    
    async def search_matches(self, game_name: str):
        """Поиск матчей по названию игры"""
        url = f"{self.base_url}/matches"
        params = {
            "search[name]": game_name,
            "per_page": 5,
            "sort": "scheduled_at"
        }
        return await self.make_request(url, params)
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

def create_main_keyboard():
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 CS2 Матчи", callback_data="matches_cs2"),
            InlineKeyboardButton(text="⚔️ Dota 2 Матчи", callback_data="matches_dota2")
        ],
        [
            InlineKeyboardButton(text="🔥 Live Матчи", callback_data="live_matches")
        ]
    ])
    return keyboard

def create_match_keyboard(match: Dict, game: str):
    """Клавиатура для матча"""
    buttons = []
    
    # Ссылка на трансляцию
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="📺 Смотреть трансляцию", url=stream_url)])
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"matches_{game}"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_live_keyboard(match: Dict):
    """Клавиатура для live матча"""
    buttons = []
    
    # Обязательно ссылка для live
    stream_url = match.get("official_stream_url") or match.get("live_url") or match.get("stream_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="🔥 Смотреть LIVE", url=stream_url)])
    else:
        # Пробуем другие поля
        for key in ["video_url", "url", "twitch_url", "youtube_url"]:
            if match.get(key):
                buttons.append([InlineKeyboardButton(text="🔥 Смотреть LIVE", url=match.get(key))])
                break
    
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="live_matches"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_time(scheduled_at: str) -> str:
    """Форматирование времени"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        now_msk = datetime.utcnow() + timedelta(hours=3)
        
        # Если сегодня
        if dt_msk.date() == now_msk.date():
            return f"Сегодня в {dt_msk.strftime('%H:%M')} MSK"
        # Если завтра
        elif dt_msk.date() == now_msk.date() + timedelta(days=1):
            return f"Завтра в {dt_msk.strftime('%H:%M')} MSK"
        # Если в течение недели
        elif dt_msk.date() <= now_msk.date() + timedelta(days=7):
            days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            return f"{days[dt_msk.weekday()]} {dt_msk.strftime('%d.%m')} в {dt_msk.strftime('%H:%M')} MSK"
        else:
            return f"{dt_msk.strftime('%d.%m.%Y')} в {dt_msk.strftime('%H:%M')} MSK"
    except:
        return "Скоро"

def format_match(match: Dict, game_info: Dict, is_live: bool = False) -> str:
    """Форматирование матча"""
    # Основные данные
    league = match.get("league", {}).get("name", "Турнир")
    tournament = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_str = format_time(scheduled_at) if scheduled_at else "Скоро"
    
    # Статус
    status = "🔥 <b>LIVE СЕЙЧАС</b>" if is_live else f"🕐 {time_str}"
    
    # Формируем сообщение
    message = f"""
<b>{game_info['emoji']} {game_info['name']}</b>

🏆 <b>{league}</b>
{tournament and f'📋 {tournament}' or ''}

⚔️ <b>{team1}</b>
   vs
⚔️ <b>{team2}</b>

{status}
"""
    
    return message.strip()

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
<b>🎮 Каппер Бармен</b>

Следим за лучшими киберспортивными матчами:

🎯 Counter-Strike 2
⚔️ Dota 2

👇 Выбери что интересует:
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
    await show_live_matches_standalone(message)

@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Тестовая команда для Dota 2"""
    await message.answer("🔍 Тестирую Dota 2 API...")
    
    # Пробуем разные методы
    test_results = []
    
    # 1. По slug
    matches_slug = await panda_api.get_upcoming_matches_by_slug("dota-2", limit=3)
    test_results.append(f"📌 По slug 'dota-2': {len(matches_slug)} матчей")
    
    # 2. По ID (предполагаемый ID 4)
    matches_id = await panda_api.get_upcoming_matches_by_id(4, limit=3)
    test_results.append(f"📌 По ID 4: {len(matches_id)} матчей")
    
    # 3. Матчи на сегодня
    matches_today = await panda_api.get_today_matches("dota-2")
    test_results.append(f"📌 На сегодня: {len(matches_today)} матчей")
    
    # 4. Поиск
    matches_search = await panda_api.search_matches("Dota")
    test_results.append(f"📌 Поиск 'Dota': {len(matches_search)} матчей")
    
    # 5. Live матчи
    live_matches = await panda_api.get_running_matches_by_slug("dota-2")
    test_results.append(f"📌 Live матчи: {len(live_matches)} матчей")
    
    result_message = "<b>🔧 Результаты теста Dota 2:</b>\n\n"
    result_message += "\n".join(test_results)
    
    # Показываем первый матч если есть
    all_matches = []
    if matches_slug:
        all_matches.extend(matches_slug)
    if matches_id:
        all_matches.extend(matches_id)
    
    if all_matches:
        result_message += f"\n\n<b>Пример матча:</b>"
        match = all_matches[0]
        result_message += f"\nID: {match.get('id')}"
        result_message += f"\nНазвание: {match.get('name', 'N/A')}"
        result_message += f"\nВремя: {match.get('scheduled_at', 'N/A')}"
        result_message += f"\nЛига: {match.get('league', {}).get('name', 'N/A')}"
    
    await message.answer(result_message, disable_web_page_preview=True)

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: types.CallbackQuery):
    """Главное меню"""
    welcome = """
<b>🎮 Каппер Бармен</b>

👇 Выбери что интересует:
"""
    
    await callback.message.edit_text(
        welcome,
        reply_markup=create_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "matches_cs2")
async def handle_cs2_matches(callback: types.CallbackQuery):
    """CS2 матчи"""
    await callback.answer("🎯 Загружаю CS2...")
    await show_cs2_matches(callback)

@dp.callback_query(F.data == "matches_dota2")
async def handle_dota2_matches(callback: types.CallbackQuery):
    """Dota 2 матчи"""
    await callback.answer("⚔️ Загружаю Dota 2...")
    await show_dota2_matches(callback)

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live...")
    await show_live_matches_callback(callback)

# ========== ФУНКЦИИ ДЛЯ КАЖДОЙ ИГРЫ ==========

async def show_cs2_matches(message_or_callback):
    """Показать CS2 матчи"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    game_info = GAMES["cs2"]
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text(f"🎯 Ищу матчи {game_info['name']}...")
    else:
        msg = await message_or_callback.answer(f"🎯 Ищу матчи {game_info['name']}...")
    
    # Пробуем разные методы для CS2
    matches = []
    
    # 1. Основной метод по slug
    matches = await panda_api.get_upcoming_matches_by_slug(game_info["slug"], limit=5)
    
    # 2. Если не нашли, пробуем по ID
    if not matches:
        matches = await panda_api.get_upcoming_matches_by_id(game_info["id"], limit=5)
    
    if not matches:
        no_matches = f"📭 Нет предстоящих матчей {game_info['name']}"
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches)
        else:
            await msg.edit_text(no_matches)
        return
    
    # Заголовок
    header = f"<b>{game_info['emoji']} {game_info['name']}</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Матчи
    for match in matches[:5]:
        match_text = format_match(match, game_info)
        keyboard = create_match_keyboard(match, "cs2")
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

async def show_dota2_matches(message_or_callback):
    """Показать Dota 2 матчи"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    game_info = GAMES["dota2"]
    
    # Загрузка
    if is_callback:
        await message_or_callback.message.edit_text(f"⚔️ Ищу матчи {game_info['name']}...")
    else:
        msg = await message_or_callback.answer(f"⚔️ Ищу матчи {game_info['name']}...")
    
    # Пробуем ВСЕ методы для Dota 2
    all_matches = []
    
    logger.info(f"🔍 Поиск матчей Dota 2...")
    
    # 1. По slug dota-2
    logger.info("Пробую slug: dota-2")
    matches1 = await panda_api.get_upcoming_matches_by_slug("dota-2", limit=5)
    logger.info(f"Найдено по slug: {len(matches1)}")
    all_matches.extend(matches1)
    
    # 2. По slug dota2 (без дефиса)
    logger.info("Пробую slug: dota2")
    matches2 = await panda_api.get_upcoming_matches_by_slug("dota2", limit=5)
    logger.info(f"Найдено по slug dota2: {len(matches2)}")
    all_matches.extend(matches2)
    
    # 3. По ID 4
    logger.info("Пробую ID: 4")
    matches3 = await panda_api.get_upcoming_matches_by_id(4, limit=5)
    logger.info(f"Найдено по ID 4: {len(matches3)}")
    all_matches.extend(matches3)
    
    # 4. По ID 14 (другой возможный ID)
    logger.info("Пробую ID: 14")
    matches4 = await panda_api.get_upcoming_matches_by_id(14, limit=5)
    logger.info(f"Найдено по ID 14: {len(matches4)}")
    all_matches.extend(matches4)
    
    # 5. Матчи на сегодня
    logger.info("Пробую матчи на сегодня")
    matches5 = await panda_api.get_today_matches("dota-2")
    logger.info(f"Найдено на сегодня: {len(matches5)}")
    all_matches.extend(matches5)
    
    # 6. Поиск
    logger.info("Пробую поиск")
    matches6 = await panda_api.search_matches("Dota")
    logger.info(f"Найдено поиском: {len(matches6)}")
    all_matches.extend(matches6)
    
    # Убираем дубликаты по ID
    unique_matches = []
    seen_ids = set()
    
    for match in all_matches:
        if match and match.get("id") and match["id"] not in seen_ids:
            seen_ids.add(match["id"])
            unique_matches.append(match)
    
    logger.info(f"Всего уникальных матчей Dota 2: {len(unique_matches)}")
    
    if not unique_matches:
        no_matches = f"📭 К сожалению, матчей {game_info['name']} не найдено\n\n"
        no_matches += "Возможно, нет запланированных турниров в ближайшее время."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="matches_dota2")],
            [InlineKeyboardButton(text="🎯 CS2 Матчи", callback_data="matches_cs2")],
            [InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=keyboard)
        else:
            await msg.edit_text(no_matches, reply_markup=keyboard)
        return
    
    # Сортируем по времени
    unique_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    # Заголовок
    header = f"<b>{game_info['emoji']} {game_info['name']}</b>\n"
    header += f"Найдено матчей: {len(unique_matches)}\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем матчи
    for match in unique_matches[:5]:
        match_text = format_match(match, game_info)
        keyboard = create_match_keyboard(match, "dota2")
        
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

async def show_live_matches_standalone(message: types.Message):
    """Live матчи через команду"""
    await show_live_matches(message, is_callback=False)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    if is_callback:
        await message_or_callback.message.edit_text("🔥 Ищу live матчи...")
    else:
        msg = await message_or_callback.answer("🔥 Ищу live матчи...")
    
    # Ищем live для обеих игр
    all_live = []
    
    # CS2 live
    cs2_live = await panda_api.get_running_matches_by_slug("csgo")
    for match in cs2_live:
        match["game_info"] = GAMES["cs2"]
        all_live.append(match)
    
    # Dota 2 live - пробуем разные методы
    dota_methods = [
        ("dota-2", "slug dota-2"),
        ("dota2", "slug dota2"),
        (4, "ID 4"),
        (14, "ID 14")
    ]
    
    for method, desc in dota_methods:
        if isinstance(method, str):
            matches = await panda_api.get_running_matches_by_slug(method)
        else:
            matches = await panda_api.get_running_matches_by_id(method)
        
        if matches:
            logger.info(f"Найдено live Dota 2 через {desc}: {len(matches)}")
            for match in matches:
                match["game_info"] = GAMES["dota2"]
                all_live.append(match)
            break
    
    if not all_live:
        no_live = "📭 Сейчас нет live матчей"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 CS2 Матчи", callback_data="matches_cs2")],
            [InlineKeyboardButton(text="⚔️ Dota 2 Матчи", callback_data="matches_dota2")],
            [InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_live, reply_markup=keyboard)
        else:
            await msg.edit_text(no_live, reply_markup=keyboard)
        return
    
    # Заголовок
    header = "<b>🔥 LIVE МАТЧИ СЕЙЧАС</b>\n"
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await msg.edit_text(header)
    
    # Показываем live матчи
    for match in all_live[:5]:
        game_info = match.pop("game_info")
        match_text = format_match(match, game_info, is_live=True)
        keyboard = create_live_keyboard(match)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.2)

# ========== ЗАПУСК ==========

async def main():
    """Запуск бота"""
    logger.info("🚀 Запускаю Каппер Бармен...")
    
    if not PANDASCORE_TOKEN or not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Не установлены токены!")
        return
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    asyncio.run(main())