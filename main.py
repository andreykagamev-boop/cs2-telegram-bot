import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import aiohttp
from aiogram import Bot, Dispatcher, types, F, Router
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
router = Router()
dp.include_router(router)

# Константы игр
GAMES: Dict[str, Dict[str, Any]] = {
    "cs2": {
        "name": "CS2",
        "slug": "csgo", 
        "emoji": "🔫",
        "hashtag": "#CS2"
    },
    "dota2": {
        "name": "DOTA 2",
        "slug": "dota-2",
        "emoji": "⚔️",
        "hashtag": "#DOTA2"
    }
}

class PandaScoreAPI:
    """Клиент для PandaScore API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Получение сессии"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def make_request(self, url: str, params: Optional[Dict] = None) -> Any:
        """Универсальный запрос"""
        try:
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API Error {response.status}: {await response.text()}")
                    return []
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_upcoming_matches(self, game_slug: str, limit: int = 5) -> List[Dict]:
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
        params = {"per_page": 3}
        return await self.make_request(url, params)
    
    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

# ========== HTML ШАБЛОНЫ ==========

def html_wrap(content: str, title: str = "Каппер Бармен") -> str:
    """Обертка HTML"""
    return f"""
<b>{title}</b>
{content}
<code>────────────────────</code>
"""

def create_header(icon: str, title: str) -> str:
    """Создание заголовка"""
    return f"""
{icon} <b>{title}</b>
<code>────────────────────</code>
"""

def create_match_card(match: Dict, game_info: Dict, is_live: bool = False) -> str:
    """Создание карточки матча"""
    # Данные
    league = match.get("league", {}).get("name", "ТУРНИР")
    opponents = match.get("opponents", [])
    
    # Команды
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_str = ""
    
    if scheduled_at:
        try:
            dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            dt_msk = dt_utc + timedelta(hours=3)
            
            today = datetime.utcnow() + timedelta(hours=3)
            
            if dt_msk.date() == today.date():
                time_str = f"🕐 <b>Сегодня в {dt_msk.strftime('%H:%M')}</b>"
            elif dt_msk.date() == today.date() + timedelta(days=1):
                time_str = f"🕐 <b>Завтра в {dt_msk.strftime('%H:%M')}</b>"
            else:
                weekday = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][dt_msk.weekday()]
                time_str = f"🕐 <b>{dt_msk.strftime('%d.%m')} ({weekday}) {dt_msk.strftime('%H:%M')}</b>"
        except:
            time_str = "🕐 <b>Время уточняется</b>"
    else:
        time_str = "🕐 <b>Скоро</b>"
    
    # Статус
    if is_live:
        status = "🔴 <b>LIVE СЕЙЧАС</b>"
        time_str = "🔥 <b>ПРЯМОЙ ЭФИР</b>"
    else:
        status = "🟢 <b>СКОРО НАЧНЕТСЯ</b>"
    
    # Игра и хэштег
    game_tag = f"{game_info['emoji']} {game_info['name']} {game_info['hashtag']}"
    
    # Формируем HTML
    html = f"""
{create_header(game_info['emoji'], game_tag)}

🏆 <i>{league}</i>

<b>{team1}</b>
   ⚔️  vs  ⚔️
<b>{team2}</b>

{time_str}
{status}

<code>┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄</code>
🍻 <i>Бармен рекомендует: Cold Brew</i>
    """
    
    return html_wrap(html.strip(), "Каппер Бармен")

# ========== КЛАВИАТУРЫ ==========

def create_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 CS2 МАТЧИ", callback_data="cs2_matches"),
            InlineKeyboardButton(text="⚔️ DOTA 2 МАТЧИ", callback_data="dota2_matches")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE ТРАНСЛЯЦИИ", callback_data="live_matches"),
            InlineKeyboardButton(text="📅 ВСЕ МАТЧИ", callback_data="all_matches")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh")
        ]
    ])

def create_back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ НАЗАД", callback_data="back_to_main")]
    ])

def create_match_keyboard(match_data: Dict, game: str) -> InlineKeyboardMarkup:
    """Клавиатура для матча"""
    buttons = []
    
    # Ссылка на трансляцию если есть
    stream_url = match_data.get("official_stream_url") or match_data.get("live_url")
    if stream_url:
        buttons.append([InlineKeyboardButton(text="📺 СМОТРЕТЬ СТРИМ", url=stream_url)])
    
    # Основные кнопки
    buttons.append([
        InlineKeyboardButton(text="🔄 ЕЩЕ МАТЧИ", callback_data=f"{game}_matches"),
        InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Стартовая команда"""
    welcome_html = html_wrap("""
🍻 <b>Добро пожаловать в Каппер Бармен!</b>

Я твой виртуальный бармен в мире киберспорта.
Покажу все самые горячие матчи CS2 и Dota 2.

👇 <b>Выбери что интересует:</b>
""", "🍸 Каппер Бармен")
    
    await message.answer(
        welcome_html,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """CS2 матчи"""
    await load_and_show_matches(message, "cs2")

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Dota 2 матчи"""
    await load_and_show_matches(message, "dota2")

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Live матчи"""
    await show_live_matches(message)

# ========== CALLBACK ОБРАБОТЧИКИ ==========

@dp.callback_query(F.data == "back_to_main")
async def handle_back(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    welcome_html = html_wrap("""
🍻 <b>Снова в главном меню!</b>

👇 <b>Выбери что интересует:</b>
""", "🍸 Каппер Бармен")
    
    await callback.message.edit_text(
        welcome_html,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновление главного меню"""
    welcome_html = html_wrap("""
🔄 <b>Меню обновлено!</b>

👇 <b>Выбери что интересует:</b>
""", "🍸 Каппер Бармен")
    
    await callback.message.edit_text(
        welcome_html,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer("✅ Обновлено")

@dp.callback_query(F.data == "cs2_matches")
async def handle_cs2_matches(callback: types.CallbackQuery):
    """CS2 матчи"""
    await callback.answer("⏳ Загружаю CS2 матчи...")
    await load_and_show_matches_callback(callback, "cs2")

@dp.callback_query(F.data == "dota2_matches")
async def handle_dota2_matches(callback: types.CallbackQuery):
    """Dota 2 матчи"""
    await callback.answer("⏳ Загружаю Dota 2 матчи...")
    await load_and_show_matches_callback(callback, "dota2")

@dp.callback_query(F.data == "all_matches")
async def handle_all_matches(callback: types.CallbackQuery):
    """Все матчи"""
    await callback.answer("⏳ Загружаю все матчи...")
    await show_all_matches(callback)

@dp.callback_query(F.data == "live_matches")
async def handle_live_matches(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("⏳ Ищу live трансляции...")
    await show_live_matches_callback(callback)

# ========== ЛОГИКА ПОКАЗА МАТЧЕЙ ==========

async def load_and_show_matches(message_or_callback, game: str, is_callback: bool = False):
    """Загрузка и показ матчей"""
    if game not in GAMES:
        error_msg = html_wrap("❌ <b>Игра не найдена</b>")
        
        if is_callback:
            await message_or_callback.message.edit_text(
                error_msg,
                reply_markup=create_back_keyboard()
            )
        else:
            await message_or_callback.answer(
                error_msg,
                reply_markup=create_back_keyboard()
            )
        return
    
    game_info = GAMES[game]
    
    # Сообщение о загрузке
    loading_msg = html_wrap(f"""
⏳ <b>Ищу матчи {game_info['emoji']} {game_info['name']}...</b>

<i>Спрашиваю у бармена последние новости...</i>
""")
    
    chat_id = None
    if is_callback:
        chat_id = message_or_callback.message.chat.id
        await message_or_callback.message.edit_text(loading_msg)
    else:
        chat_id = message_or_callback.chat.id
        msg = await message_or_callback.answer(loading_msg)
    
    # Загружаем матчи
    matches = await panda_api.get_upcoming_matches(game_info["slug"])
    
    if not matches:
        no_matches_msg = html_wrap(f"""
📭 <b>Матчей {game_info['name']} не найдено</b>

<i>Бармен говорит: "Пока тихо, загляни позже!"</i>
""")
        
        if is_callback:
            await message_or_callback.message.edit_text(
                no_matches_msg,
                reply_markup=create_back_keyboard()
            )
        else:
            if 'msg' in locals():
                await msg.edit_text(no_matches_msg, reply_markup=create_back_keyboard())
            else:
                await message_or_callback.answer(no_matches_msg, reply_markup=create_back_keyboard())
        return
    
    # Показываем заголовок
    header_msg = html_wrap(f"""
🎮 <b>{game_info['emoji']} {game_info['name']} - БЛИЖАЙШИЕ МАТЧИ</b>

🏆 <i>Найдено {len(matches)} матчей</i>
""")
    
    if is_callback:
        await message_or_callback.message.edit_text(header_msg)
    else:
        if 'msg' in locals():
            await msg.edit_text(header_msg)
        else:
            await message_or_callback.answer(header_msg)
    
    # Показываем каждый матч
    for match in matches[:5]:  # Ограничиваем 5 матчами
        match_html = create_match_card(match, game_info)
        keyboard = create_match_keyboard(match, game)
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_html,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)

async def load_and_show_matches_callback(callback: types.CallbackQuery, game: str):
    """Загрузка матчей через callback"""
    await load_and_show_matches(callback, game, is_callback=True)

async def show_all_matches(callback: types.CallbackQuery):
    """Показать все матчи"""
    await callback.message.edit_text(html_wrap("""
🎮 <b>Собираю все матчи...</b>

<i>Проверяю расписание на всех экранах бара</i>
"""))
    
    all_matches = []
    
    # Собираем матчи со всех игр
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=3)
        for match in matches:
            match["game_info"] = game_info
            all_matches.append(match)
    
    if not all_matches:
        await callback.message.edit_text(
            html_wrap("""
📭 <b>Нет запланированных матчей</b>

<i>Бармен предлагает: "Давай просто выпьем!"</i>
"""),
            reply_markup=create_back_keyboard()
        )
        return
    
    # Сортируем по времени
    all_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    # Заголовок
    await callback.message.edit_text(html_wrap(f"""
📅 <b>ВСЕ МАТЧИ НА СЕГОДНЯ</b>

🏆 <i>Всего {len(all_matches)} матчей</i>
"""))
    
    # Показываем матчи
    for match in all_matches[:6]:
        game_info = match.pop("game_info")
        match_html = create_match_card(match, game_info)
        keyboard = create_match_keyboard(match, game_info["slug"])
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=match_html,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)

async def show_live_matches(message_or_callback, is_callback: bool = False):
    """Показать live матчи"""
    if is_callback:
        await message_or_callback.message.edit_text(html_wrap("""
🔍 <b>Ищу live трансляции...</b>

<i>Смотрю на все экраны в баре...</i>
"""))
        chat_id = message_or_callback.message.chat.id
    else:
        msg = await message_or_callback.answer(html_wrap("""
🔍 <b>Ищу live трансляции...</b>
"""))
        chat_id = message_or_callback.chat.id
    
    # Ищем live матчи
    live_matches = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            live_matches.append(match)
    
    if not live_matches:
        no_live_msg = html_wrap("""
📭 <b>Сейчас нет live трансляций</b>

<i>Бармен говорит: "Пока тишина, но мы готовим напитки!"</i>
""")
        
        if is_callback:
            await message_or_callback.message.edit_text(
                no_live_msg,
                reply_markup=create_back_keyboard()
            )
        else:
            await message_or_callback.answer(no_live_msg, reply_markup=create_back_keyboard())
        return
    
    # Заголовок
    header_msg = html_wrap(f"""
🔥 <b>LIVE ТРАНСЛЯЦИИ ПРЯМО СЕЙЧАС</b>

🎮 <i>В эфире: {len(live_matches)} матчей</i>
""")
    
    if is_callback:
        await message_or_callback.message.edit_text(header_msg)
    else:
        await message_or_callback.answer(header_msg)
    
    # Показываем live матчи
    for match in live_matches:
        game_info = match.pop("game_info")
        
        # Создаем live карточку
        live_html = create_match_card(match, game_info, is_live=True)
        
        # Клавиатура со ссылкой на стрим
        keyboard = create_match_keyboard(match, game_info["slug"])
        
        await bot.send_message(
            chat_id=chat_id,
            text=live_html,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.3)
    
    if is_callback:
        await message_or_callback.answer(f"🔥 Найдено {len(live_matches)} live")

async def show_live_matches_callback(callback: types.CallbackQuery):
    """Live матчи через callback"""
    await show_live_matches(callback, is_callback=True)

# ========== ЗАПУСК ==========

async def main():
    """Запуск бота"""
    logger.info("🚀 Запускаю Каппер Бармен...")
    
    # Проверяем токены
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