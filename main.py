import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

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

# Константы
GAMES = {
    "cs2": {"name": "Counter-Strike 2", "slug": "csgo", "emoji": "🎯"},
    "dota2": {"name": "Dota 2", "slug": "dota-2", "emoji": "⚔️"}
}

class PandaScoreAPI:
    """Класс для работы с PandaScore API"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.pandascore.co"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def get_upcoming_matches(self, game_slug: str, limit: int = 10):
        """Получение предстоящих матчей"""
        try:
            session = await self.get_session()
            url = f"{self.base_url}/{game_slug}/matches/upcoming"
            
            async with session.get(url, params={
                "per_page": limit,
                "sort": "scheduled_at",
                "page": 1
            }) as response:
                
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"API Error: {response.status} - {await response.text()}")
                    return []
                    
        except Exception as e:
            logger.error(f"Request error: {e}")
            return []
    
    async def get_running_matches(self, game_slug: str):
        """Получение текущих матчей"""
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
    
    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()

# Инициализация API клиента
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)

def create_main_keyboard():
    """Создание основной клавиатуры в стиле бара"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 КС2 СЕГОДНЯ", callback_data="matches_cs2"),
            InlineKeyboardButton(text="⚔️ ДОТА СЕГОДНЯ", callback_data="matches_dota2")
        ],
        [
            InlineKeyboardButton(text="🔴 LIVE ЭФИР", callback_data="live_all"),
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh")
        ]
    ])
    return keyboard

def format_time_display(scheduled_at: str) -> str:
    """Форматирует время для отображения"""
    try:
        # PandaScore время в UTC
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        
        # Конвертируем в MSK (+3)
        dt_msk = dt_utc + timedelta(hours=3)
        
        # Форматируем
        today = datetime.utcnow() + timedelta(hours=3)
        
        if dt_msk.date() == today.date():
            # Сегодня
            return f"🕐 СЕГОДНЯ в {dt_msk.strftime('%H:%M')}"
        elif dt_msk.date() == today.date() + timedelta(days=1):
            # Завтра
            return f"🕐 ЗАВТРА в {dt_msk.strftime('%H:%M')}"
        else:
            # Другой день
            weekday = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"][dt_msk.weekday()]
            return f"🕐 {dt_msk.strftime('%d.%m')} ({weekday}) в {dt_msk.strftime('%H:%M')}"
            
    except Exception as e:
        logger.error(f"Time error: {e}")
        return "🕐 ВРЕМЯ УТОЧНЯЕТСЯ"

def format_match_bar_style(match: dict, game_info: dict) -> str:
    """Форматирование матча в стиле бара"""
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Время
    scheduled_at = match.get("scheduled_at", "")
    time_display = format_time_display(scheduled_at) if scheduled_at else "🕐 СКОРО"
    
    # Турнир
    league = match.get("league", {}).get("name", "ТУРНИР")
    
    # Стиль бара
    message = (
        f"┌{'─' * 35}┐\n"
        f"│ 🍻 {game_info['emoji']} {game_info['name']} 🍻 │\n"
        f"└{'─' * 35}┘\n\n"
        
        f"🏆 <b>{league}</b>\n\n"
        
        f"🎮 <b>{team1}</b>\n"
        f"   ⚡️ vs ⚡️\n"
        f"🎮 <b>{team2}</b>\n\n"
        
        f"{time_display}\n\n"
        
        f"📍 <i>Экран у барной стойки</i>\n"
        f"🎧 <i>Звук включен</i>"
    )
    
    return message

def format_live_match(match: dict, game_info: dict) -> str:
    """Форматирование live матча"""
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    league = match.get("league", {}).get("name", "ТУРНИР")
    
    message = (
        f"┌{'─' * 35}┐\n"
        f"│ 🔴 {game_info['emoji']} LIVE! 🔴 │\n"
        f"└{'─' * 35}┘\n\n"
        
        f"🏆 <b>{league}</b>\n\n"
        
        f"⚡️ <b>{team1}</b>\n"
        f"   🆚\n"
        f"⚡️ <b>{team2}</b>\n\n"
        
        f"🔥 <b>ПРЯМО СЕЙЧАС НА ЭКРАНЕ!</b>\n\n"
        
        f"🍻 <i>Бармен рекомендует: IPA</i>\n"
        f"🎯 <i>Счет обновляется в реальном времени</i>"
    )
    
    return message

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = (
        f"┌{'─' * 35}┐\n"
        f"│       🍻 КИБЕРБАР 🍻       │\n"
        f"└{'─' * 35}┘\n\n"
        f"Что сегодня показываем на экранах?\n\n"
        f"🎯 CS2 матчи\n"
        f"⚔️ Dota 2 баталии\n\n"
        f"<i>Все время — московское</i>"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=create_main_keyboard()
    )

@dp.message(Command("cs2"))
async def cmd_cs2(message: types.Message):
    """Матчи CS2"""
    await show_matches(message, "cs2")

@dp.message(Command("dota2"))
async def cmd_dota2(message: types.Message):
    """Матчи Dota 2"""
    await show_matches(message, "dota2")

@dp.message(Command("live"))
async def cmd_live(message: types.Message):
    """Текущие матчи"""
    await show_all_live_matches_standalone(message)

@dp.callback_query(F.data.startswith("matches_"))
async def handle_matches_callback(callback: types.CallbackQuery):
    """Обработчик кнопок с матчами"""
    game = callback.data.split("_")[1]
    await show_matches_callback(callback, game)

@dp.callback_query(F.data.startswith("live_"))
async def handle_live_callback(callback: types.CallbackQuery):
    """Обработчик кнопок с live матчами"""
    if callback.data == "live_all":
        await show_all_live_matches(callback)

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновление главного меню"""
    await callback.message.edit_text(
        f"┌{'─' * 35}┐\n"
        f"│       🍻 КИБЕРБАР 🍻       │\n"
        f"└{'─' * 35}┘\n\n"
        f"Что сегодня показываем на экранах?\n\n"
        f"🎯 CS2 матчи\n"
        f"⚔️ Dota 2 баталии\n\n"
        f"<i>Все время — московское</i>",
        reply_markup=create_main_keyboard()
    )
    await callback.answer("✅ Меню обновлено")

# ========== ФУНКЦИИ ПОКАЗА МАТЧЕЙ ==========

async def show_matches(message_or_callback, game: str):
    """Показать матчи для игры"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    if game not in GAMES:
        return
    
    game_info = GAMES[game]
    
    if is_callback:
        await message_or_callback.message.edit_text(f"🍻 Ищу матчи {game_info['name']}...")
    else:
        await message_or_callback.answer(f"🍻 Ищу матчи {game_info['name']}...")
    
    matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=5)
    
    if not matches:
        no_matches = (
            f"┌{'─' * 35}┐\n"
            f"│   🎮 {game_info['name']}   │\n"
            f"└{'─' * 35}┘\n\n"
            f"📭 Сегодня матчей нет\n\n"
            f"<i>Возможно, позже добавят расписание</i>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ", callback_data=f"matches_{game}")],
            [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="refresh")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(no_matches, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, no_matches, reply_markup=keyboard)
        return
    
    # Отправляем заголовок
    header = (
        f"┌{'─' * 35}┐\n"
        f"│   🎮 {game_info['name']} МАТЧИ   │\n"
        f"└{'─' * 35}┘\n\n"
        f"📅 Ближайшие игры:\n"
    )
    
    if is_callback:
        await message_or_callback.message.edit_text(header)
    else:
        await bot.send_message(chat_id, header)
    
    # Отправляем матчи
    for match in matches[:5]:
        match_text = format_match_bar_style(match, game_info)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=f"matches_{game}")],
            [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="refresh")]
        ])
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.3)
    
    if is_callback:
        await callback.answer(f"✅ {len(matches)} матчей")

async def show_matches_callback(callback: types.CallbackQuery, game: str):
    """Показать матчи через callback"""
    await show_matches(callback, game)

async def show_all_live_matches(callback: types.CallbackQuery):
    """Показать все live матчи"""
    await callback.message.edit_text("🍻 Смотрю что сейчас в эфире...")
    
    all_matches = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_matches.append(match)
    
    if not all_matches:
        no_live = (
            f"┌{'─' * 35}┐\n"
            f"│     🔴 LIVE ЭФИР     │\n"
            f"└{'─' * 35}┘\n\n"
            f"📭 Прямо сейчас live матчей нет\n\n"
            f"<i>Следи за расписанием выше</i>"
        )
        
        await callback.message.edit_text(
            no_live,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 КС2 РАСПИСАНИЕ", callback_data="matches_cs2")],
                [InlineKeyboardButton(text="⚔️ ДОТА РАСПИСАНИЕ", callback_data="matches_dota2")],
                [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="refresh")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(f"🔴 Нашел {len(all_matches)} live матчей:")
    
    for match in all_matches[:3]:
        game_info = match.pop("game_info")
        match_text = format_live_match(match, game_info)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="live_all")],
            [InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="refresh")]
        ])
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=match_text,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.3)
    
    await callback.answer(f"🔴 {len(all_matches)} в эфире")

async def show_all_live_matches_standalone(message: types.Message):
    """Live матчи через команду"""
    await message.answer("🍻 Смотрю что сейчас в эфире...")
    
    all_matches = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_matches.append(match)
    
    if not all_matches:
        no_live = (
            f"┌{'─' * 35}┐\n"
            f"│     🔴 LIVE ЭФИР     │\n"
            f"└{'─' * 35}┘\n\n"
            f"📭 Прямо сейчас live матчей нет"
        )
        
        await message.answer(no_live)
        return
    
    await message.answer(f"🔴 Live матчи на экранах:")
    
    for match in all_matches[:3]:
        game_info = match.pop("game_info")
        match_text = format_live_match(match, game_info)
        
        await message.answer(match_text)
        await asyncio.sleep(0.3)

# ========== ЗАПУСК БОТА ==========

async def main():
    """Основная функция запуска"""
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await panda_api.close()

if __name__ == "__main__":
    # Проверка токенов
    if not PANDASCORE_TOKEN:
        logger.error("PANDASCORE_TOKEN не установлен!")
        exit(1)
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        exit(1)
    
    logger.info("🍻 Запускаю КиберБар бота...")
    logger.info("🎯 CS2 | ⚔️ Dota 2")
    
    # Запуск бота
    asyncio.run(main())