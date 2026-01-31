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
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Константы
GAMES = {
    "cs2": {"name": "Counter-Strike 2", "slug": "csgo", "emoji": "🎯", "hashtag": "#CS2"},
    "dota2": {"name": "Dota 2", "slug": "dota-2", "emoji": "⚔️", "hashtag": "#DOTA2"}
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
            InlineKeyboardButton(text="🎯 КС2 МАТЧИ", callback_data="matches_cs2"),
            InlineKeyboardButton(text="⚔️ ДОТА 2 МАТЧИ", callback_data="matches_dota2")
        ],
        [
            InlineKeyboardButton(text="🔥 СЕЙЧАС В ЭФИРЕ", callback_data="live_all"),
            InlineKeyboardButton(text="📊 РАСПИСАНИЕ", callback_data="schedule")
        ],
        [
            InlineKeyboardButton(text="🍻 ЗАКАЗАТЬ ПИВО", url="https://t.me/username"),
            InlineKeyboardButton(text="📞 БРОНЬ СТОЛИКА", url="https://t.me/username")
        ],
        [
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh"),
            InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")
        ]
    ])
    return keyboard

def format_time_to_msk(scheduled_at: str) -> tuple:
    """Конвертирует время в MSK и возвращает строку с оставшимся временем"""
    try:
        # Конвертируем UTC в MSK (+3 часа)
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        
        # Форматируем время
        date_str = dt_msk.strftime("%d.%m")
        time_str = dt_msk.strftime("%H:%M")
        weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][dt_msk.weekday()]
        
        # Считаем оставшееся время
        now = datetime.utcnow() + timedelta(hours=3)  # Текущее время в MSK
        time_diff = dt_msk - now
        
        if time_diff.total_seconds() < 0:
            return f"{date_str} ({weekday}) {time_str} MSK", "УЖЕ НАЧАЛСЯ!"
        
        if time_diff.days > 0:
            remaining = f"ЧЕРЕЗ {time_diff.days} ДНЕЙ"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            remaining = f"ЧЕРЕЗ {hours} ЧАСОВ"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            remaining = f"ЧЕРЕЗ {minutes} МИНУТ"
        else:
            remaining = "СКОРО"
        
        return f"{date_str} ({weekday}) {time_str} MSK", remaining
        
    except Exception as e:
        logger.error(f"Time formatting error: {e}")
        return "СКОРО", "ВРЕМЯ УТОЧНЯЕТСЯ"

def format_match_bar_style(match: dict, game_info: dict, match_type: str = "UPCOMING") -> str:
    """Форматирование матча в стиле спортивного бара"""
    # Заголовок бара
    header = "╔══════════════════════════════╗\n"
    header += "║     🍻 SPORTS BAR TV 🍻     ║\n"
    header += "╚══════════════════════════════╝\n\n"
    
    # Информация о матче
    league = match.get("league", {}).get("name", "UNKNOWN LEAGUE")
    series = match.get("serie", {}).get("full_name", "")
    
    # Команды
    opponents = match.get("opponents", [])
    team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
    team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
    
    # Логотип игры
    game_line = f"🎮 {game_info['name']} {game_info['hashtag']}\n"
    
    # Время матча
    scheduled_at = match.get("scheduled_at")
    if scheduled_at:
        time_str, remaining = format_time_to_msk(scheduled_at)
        time_line = f"🕐 {time_str}\n"
        remaining_line = f"⏳ {remaining}\n"
    else:
        time_line = "🕐 ВРЕМЯ УТОЧНЯЕТСЯ\n"
        remaining_line = ""
    
    # Турнир
    tournament_line = f"🏆 {league}\n"
    if series:
        tournament_line += f"📋 {series}\n"
    
    # Противоборство
    vs_line = f"⚔️  {team1}\n"
    vs_line += f"   vs\n"
    vs_line += f"⚔️  {team2}\n"
    
    # Статус
    if match_type == "LIVE":
        status_line = "\n🔴 🔴 🔴 ПРЯМОЙ ЭФИР! 🔴 🔴 🔴\n"
    else:
        status_line = "\n📺 СКОРО НА НАШИХ ЭКРАНАХ\n"
    
    # Подвал
    footer = "\n" + "─" * 35 + "\n"
    footer += "📍 Ул. Киберспортивная, 13\n"
    footer += "📞 Бронь: +7 (XXX) XXX-XX-XX\n"
    footer += "🍻 Пиво от 150₽, закуски от 200₽\n"
    
    # Собираем все вместе
    message = header + game_line + tournament_line + vs_line + "\n" + time_line + remaining_line + status_line + footer
    
    return message

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = (
        "╔══════════════════════════════╗\n"
        "║     🍻 ДОБРО ПОЖАЛОВАТЬ     ║\n"
        "║     В SPORTS BAR TV! 🍻     ║\n"
        "╚══════════════════════════════╝\n\n"
        "🎮 Следим за лучшими киберспортивными матчами!\n"
        "📺 Трансляции на больших экранах\n"
        "🍻 Вкусное пиво и закуски\n"
        "🎯 КС2 | ⚔️ Dota 2 | 🎪 Другие игры\n\n"
        "👇 Выбирай что интересует:"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
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
    await message.answer(
        "🔥 СЕЙЧАС В ЭФИРЕ В НАШЕМ БАРЕ:\n\n"
        "Выбери игру для просмотра live-матчей:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 КС2 LIVE", callback_data="live_cs2"),
                InlineKeyboardButton(text="⚔️ DOTA 2 LIVE", callback_data="live_dota2")
            ],
            [InlineKeyboardButton(text="👀 ВСЕ LIVE МАТЧИ", callback_data="live_all")],
            [InlineKeyboardButton(text="🏠 В ГЛАВНОЕ МЕНЮ", callback_data="refresh")]
        ])
    )

@dp.message(Command("bar"))
async def cmd_bar_info(message: types.Message):
    """Информация о баре"""
    bar_info = (
        "╔══════════════════════════════╗\n"
        "║   🍻 SPORTS BAR TV INFO 🍻  ║\n"
        "╚══════════════════════════════╝\n\n"
        "📍 Адрес: Ул. Киберспортивная, 13\n"
        "🚇 Метро: Геймерская\n"
        "⏰ Часы работы: 12:00 - 06:00\n\n"
        "🎮 ЧТО У НАС ЕСТЬ:\n"
        "• 10 больших экранов с трансляциями\n"
        "• Зал на 150 человек\n"
        "• Профессиональная звуковая система\n"
        "• PlayStation 5 / Xbox Series X\n"
        "• Кикер и настольный хоккей\n\n"
        "🍻 МЕНЮ:\n"
        "• Крафтовое пиво от 150₽\n"
        "• Коктейли от 250₽\n"
        "• Бургеры, крылышки, картофель\n"
        "• Специальные киберспортивные сеты\n\n"
        "📞 Бронь столика: +7 (XXX) XXX-XX-XX\n"
        "📱 Telegram: @sportsbar_tv"
    )
    await message.answer(bar_info)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь"""
    help_text = (
        "╔══════════════════════════════╗\n"
        "║        🆘 ПОМОЩЬ 🆘         ║\n"
        "╚══════════════════════════════╝\n\n"
        "🎮 КОМАНДЫ БАРА:\n"
        "/start - Главное меню\n"
        "/cs2 - Матчи Counter-Strike 2\n"
        "/dota2 - Матчи Dota 2\n"
        "/live - Сейчас в эфире\n"
        "/bar - Информация о нашем баре\n"
        "/help - Эта справка\n\n"
        "🍻 О БАРЕ:\n"
        "• Все время в формате MSK (Москва)\n"
        "• Актуальное расписание матчей\n"
        "• Уведомления о начале трансляций\n"
        "• Информация о текущих турнирах\n\n"
        "📞 СВЯЗЬ С БАРОМ:\n"
        "• Бронь: +7 (XXX) XXX-XX-XX\n"
        "• Telegram: @sportsbar_tv\n"
        "• Адрес: Ул. Киберспортивная, 13"
    )
    await message.answer(help_text, disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("matches_"))
async def handle_matches_callback(callback: types.CallbackQuery):
    """Обработчик кнопок с матчами"""
    game = callback.data.split("_")[1]  # cs2 или dota2
    await show_matches_callback(callback, game)

@dp.callback_query(F.data.startswith("live_"))
async def handle_live_callback(callback: types.CallbackQuery):
    """Обработчик кнопок с live матчами"""
    if callback.data == "live_all":
        await show_all_live_matches(callback)
    else:
        game = callback.data.split("_")[1]  # cs2 или dota2
        await show_live_matches(callback, game)

@dp.callback_query(F.data == "schedule")
async def handle_schedule(callback: types.CallbackQuery):
    """Расписание на сегодня"""
    await show_today_schedule(callback)

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновление главного меню"""
    await callback.message.edit_text(
        "╔══════════════════════════════╗\n"
        "║     🍻 SPORTS BAR TV 🍻     ║\n"
        "╚══════════════════════════════╝\n\n"
        "🎮 Следим за лучшими киберспортивными матчами!\n"
        "👇 Выбирай что интересует:",
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )
    await callback.answer("Меню обновлено! 🍻")

@dp.callback_query(F.data == "help")
async def handle_help_callback(callback: types.CallbackQuery):
    """Помощь через callback"""
    await cmd_help(callback.message)
    await callback.answer()

# ========== ФУНКЦИИ ПОКАЗА МАТЧЕЙ ==========

async def show_matches(message_or_callback, game: str):
    """Показать матчи для игры"""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    chat_id = message_or_callback.message.chat.id if is_callback else message_or_callback.chat.id
    
    if game not in GAMES:
        error_msg = "🚫 Эту игру мы пока не показываем в баре!"
        if is_callback:
            await message_or_callback.answer(error_msg)
        else:
            await message_or_callback.answer(error_msg)
        return
    
    game_info = GAMES[game]
    
    # Показываем "загрузку"
    loading_text = (
        f"🍻 Загружаю матчи {game_info['emoji']} {game_info['name']}...\n"
        f"⏳ Ищу актуальное расписание..."
    )
    
    if is_callback:
        await message_or_callback.message.edit_text(loading_text)
    else:
        msg = await message_or_callback.answer(loading_text)
    
    # Получаем матчи
    matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=7)
    
    if not matches:
        no_matches_text = (
            f"📭 Сегодня нет матчей по {game_info['name']}\n\n"
            f"🍻 Но в баре всегда есть:\n"
            f"• Холодное пиво\n"
            f"• Вкусные закуски\n"
            f"• Повторы лучших матчей\n\n"
            f"Загляни к нам в любом случае! 😉"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🍻 МЕНЮ БАРА", callback_data="bar_menu")],
            [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ СНОВА", callback_data=f"matches_{game}")],
            [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
        ])
        
        if is_callback:
            await message_or_callback.message.edit_text(
                no_matches_text,
                reply_markup=keyboard
            )
        else:
            await msg.edit_text(no_matches_text, reply_markup=keyboard)
        return
    
    # Отправляем заголовок
    header_text = (
        f"╔══════════════════════════════╗\n"
        f"║   🎮 {game_info['name'].upper()} МАТЧИ   ║\n"
        f"╚══════════════════════════════╝\n\n"
        f"📅 Расписание на ближайшие дни:\n"
    )
    
    if is_callback:
        await message_or_callback.message.edit_text(header_text)
    else:
        await msg.edit_text(header_text)
    
    # Отправляем каждый матч отдельным сообщением
    for i, match in enumerate(matches[:5]):
        match_text = format_match_bar_style(match, game_info, "UPCOMING")
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 НАПОМНИТЬ", callback_data=f"remind_{game}_{match['id']}"),
                InlineKeyboardButton(text="📍 КАК ДОЕХАТЬ", url="https://yandex.ru/maps")
            ],
            [
                InlineKeyboardButton(text="🔄 ДРУГИЕ МАТЧИ", callback_data=f"matches_{game}"),
                InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")
            ]
        ])
        
        await bot.send_message(
            chat_id=chat_id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.5)
    
    # Отправляем итоговое сообщение
    final_text = (
        f"✅ Найдено {len(matches)} матчей по {game_info['name']}\n\n"
        f"🍻 Приходи в наш бар смотреть трансляции!\n"
        f"📞 Бронь столика: +7 (XXX) XXX-XX-XX"
    )
    
    final_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 ЗАБРОНИРОВАТЬ", url="https://t.me/username")],
        [InlineKeyboardButton(text="🍻 ПОСМОТРЕТЬ МЕНЮ", callback_data="bar_menu")],
        [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
    ])
    
    await bot.send_message(
        chat_id=chat_id,
        text=final_text,
        reply_markup=final_keyboard
    )
    
    if is_callback:
        await callback.answer(f"✅ Загружено {len(matches)} матчей!")

async def show_matches_callback(callback: types.CallbackQuery, game: str):
    """Показать матчи через callback"""
    await show_matches(callback, game)

async def show_live_matches(callback: types.CallbackQuery, game: str):
    """Показать текущие матчи"""
    if game not in GAMES:
        await callback.answer("🚫 Эту игру мы пока не показываем!")
        return
    
    game_info = GAMES[game]
    
    await callback.message.edit_text(
        f"🍻 Ищу live матчи {game_info['emoji']} {game_info['name']}...\n"
        f"🔍 Проверяю эфиры..."
    )
    
    matches = await panda_api.get_running_matches(game_info["slug"])
    
    if not matches:
        no_live_text = (
            f"📭 Сейчас нет live матчей по {game_info['name']}\n\n"
            f"🍻 Но в баре всегда есть:\n"
            f"• Повторы вчерашних матчей\n"
            f"• Специальные предложения\n"
            f"• Уютная атмосфера\n\n"
            f"Приходи в любое время!"
        )
        
        await callback.message.edit_text(
            no_live_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📅 БУДУЩИЕ МАТЧИ", callback_data=f"matches_{game}")],
                [InlineKeyboardButton(text="🍻 МЕНЮ БАРА", callback_data="bar_menu")],
                [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
            ])
        )
        await callback.answer()
        return
    
    # Заголовок для live матчей
    header = (
        f"╔══════════════════════════════╗\n"
        f"║   🔴 {game_info['name'].upper()} LIVE 🔴   ║\n"
        f"╚══════════════════════════════╝\n\n"
        f"🍻 ПРЯМО СЕЙЧАС В НАШЕМ БАРЕ:\n"
    )
    
    await callback.message.edit_text(header)
    
    # Отправляем каждый live матч
    for i, match in enumerate(matches[:3]):
        match_text = format_match_bar_style(match, game_info, "LIVE")
        
        # Пытаемся получить ссылку на трансляцию
        stream_url = match.get("official_stream_url") or match.get("live_url")
        
        keyboard_buttons = []
        if stream_url:
            keyboard_buttons.append(
                InlineKeyboardButton(text="📺 СМОТРЕТЬ ОНЛАЙН", url=stream_url)
            )
        
        keyboard_buttons.append(
            InlineKeyboardButton(text="📍 ПРИЙТИ В БАР", url="https://yandex.ru/maps")
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            keyboard_buttons,
            [
                InlineKeyboardButton(text="🍻 ЗАКАЗАТЬ СЕТ", callback_data="order_set"),
                InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")
            ]
        ])
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.5)
    
    await callback.answer("✅ Live матчи загружены! 🍻")

async def show_all_live_matches(callback: types.CallbackQuery):
    """Показать все live матчи"""
    await callback.message.edit_text(
        "🔍 Ищу все live матчи...\n"
        "🍻 Проверяю что сейчас в эфире..."
    )
    
    all_matches = []
    
    # Получаем матчи для всех игр
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_running_matches(game_info["slug"])
        for match in matches:
            match["game_info"] = game_info
            all_matches.append(match)
    
    if not all_matches:
        await callback.message.edit_text(
            "📭 Прямо сейчас нет live матчей\n\n"
            "🍻 Но у нас в баре:\n"
            "• Повторы лучших моментов\n"
            "• Специальные киберспортные сеты\n"
            "• Уютная атмосфера для общения\n\n"
            "Ждем тебя в любое время!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📅 РАСПИСАНИЕ", callback_data="schedule")],
                [InlineKeyboardButton(text="🍻 МЕНЮ БАРА", callback_data="bar_menu")],
                [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
            ])
        )
        await callback.answer()
        return
    
    # Сортируем по времени начала
    all_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    header = (
        "╔══════════════════════════════╗\n"
        "║     🔴 СЕЙЧАС В ЭФИРЕ 🔴     ║\n"
        "╚══════════════════════════════╝\n\n"
        "🍻 ПРЯМЫЕ ТРАНСЛЯЦИИ В НАШЕМ БАРЕ:\n"
    )
    
    await callback.message.edit_text(header)
    
    # Показываем все live матчи
    for match in all_matches[:5]:
        game_info = match.pop("game_info")
        match_text = format_match_bar_style(match, game_info, "LIVE")
        
        stream_url = match.get("official_stream_url") or match.get("live_url")
        
        keyboard_buttons = []
        if stream_url:
            keyboard_buttons.append(
                InlineKeyboardButton(text="📺 СМОТРЕТЬ ОНЛАЙН", url=stream_url)
            )
        
        keyboard_buttons.append(
            InlineKeyboardButton(text="📍 ПРИЙТИ СМОТРЕТЬ", url="https://yandex.ru/maps")
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            keyboard_buttons,
            [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
        ])
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=match_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.5)
    
    await callback.answer(f"✅ Найдено {len(all_matches)} live матчей! 🍻")

async def show_today_schedule(callback: types.CallbackQuery):
    """Показать расписание на сегодня"""
    await callback.message.edit_text(
        "📅 Составляю расписание на сегодня...\n"
        "🍻 Ищу все матчи которые будем показывать..."
    )
    
    # Получаем матчи для всех игр
    today_matches = []
    
    for game_key, game_info in GAMES.items():
        matches = await panda_api.get_upcoming_matches(game_info["slug"], limit=10)
        for match in matches:
            # Фильтруем только сегодняшние матчи
            scheduled_at = match.get("scheduled_at")
            if scheduled_at:
                try:
                    dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                    dt_msk = dt + timedelta(hours=3)
                    now_msk = datetime.utcnow() + timedelta(hours=3)
                    
                    # Если матч сегодня
                    if dt_msk.date() == now_msk.date():
                        match["game_info"] = game_info
                        today_matches.append(match)
                except:
                    continue
    
    if not today_matches:
        await callback.message.edit_text(
            "📭 На сегодня матчей не запланировано\n\n"
            "🍻 Но это не повод не зайти в бар!\n"
            "• Специальные предложения\n"
            "• Кино на больших экранах\n"
            "• Настольные игры\n\n"
            "Ждем тебя в любое время!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🍻 ПОСМОТРЕТЬ МЕНЮ", callback_data="bar_menu")],
                [InlineKeyboardButton(text="🎮 ДРУГИЕ ИГРЫ", callback_data="refresh")],
                [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
            ])
        )
        await callback.answer()
        return
    
    # Сортируем по времени
    today_matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    header = (
        "╔══════════════════════════════╗\n"
        "║   📅 РАСПИСАНИЕ НА СЕГОДНЯ  ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🍻 СЕГОДНЯ В НАШЕМ БАРЕ: {len(today_matches)} МАТЧЕЙ\n\n"
    )
    
    await callback.message.edit_text(header)
    
    # Группируем по времени
    time_slots = {}
    for match in today_matches:
        scheduled_at = match.get("scheduled_at")
        if scheduled_at:
            try:
                dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                dt_msk = dt + timedelta(hours=3)
                time_slot = dt_msk.strftime("%H:00")
                
                if time_slot not in time_slots:
                    time_slots[time_slot] = []
                time_slots[time_slot].append(match)
            except:
                continue
    
    # Выводим по временным слотам
    for time_slot, matches in sorted(time_slots.items()):
        slot_text = f"⏰ В {time_slot}:\n"
        
        for match in matches:
            game_info = match["game_info"]
            opponents = match.get("opponents", [])
            team1 = opponents[0].get("opponent", {}).get("name", "TBA") if len(opponents) > 0 else "TBA"
            team2 = opponents[1].get("opponent", {}).get("name", "TBA") if len(opponents) > 1 else "TBA"
            
            slot_text += f"  {game_info['emoji']} {team1} vs {team2}\n"
        
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=slot_text
        )
        await asyncio.sleep(0.3)
    
    # Финальное сообщение
    final_text = (
        "\n🍻 ЖДЕМ ТЕБЯ В НАШЕМ БАРЕ!\n\n"
        "📍 Адрес: Ул. Киберспортивная, 13\n"
        "⏰ Работаем: 12:00 - 06:00\n"
        "📞 Бронь: +7 (XXX) XXX-XX-XX"
    )
    
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=final_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 КАК ДОЕХАТЬ", url="https://yandex.ru/maps")],
            [InlineKeyboardButton(text="📞 ЗАБРОНИРОВАТЬ", url="https://t.me/username")],
            [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
        ])
    )
    
    await callback.answer(f"✅ Расписание на сегодня готово! 🍻")

@dp.callback_query(F.data == "bar_menu")
async def handle_bar_menu(callback: types.CallbackQuery):
    """Меню бара"""
    menu_text = (
        "╔══════════════════════════════╗\n"
        "║       🍻 МЕНЮ БАРА 🍻       ║\n"
        "╚══════════════════════════════╝\n\n"
        "🍺 ПИВО (0.5л):\n"
        "• Светлое крафтовое - 150₽\n"
        "• Темное портер - 180₽\n"
        "• IPA - 200₽\n"
        "• Пшеничное - 170₽\n\n"
        "🍸 КОКТЕЙЛИ:\n"
        "• Мохито - 250₽\n"
        "• Лонг Айленд - 300₽\n"
        "• Космополитен - 280₽\n"
        "• Киберспортный сет (3 коктейля) - 700₽\n\n"
        "🍔 ЗАКУСКИ:\n"
        "• Крылья Buffalo - 350₽\n"
        "• Начос с сыром - 280₽\n"
        "• Бургер 'Headshot' - 450₽\n"
        "• Картофель фри - 200₽\n\"🎮 КИБЕРСПОРТНЫЕ СЕТЫ:\n"
        "• 'Победа в раунде' - 1200₽\n"
        "   (пиво + крылья + начос)\n"
        "• 'Клановая война' - 2500₽\n"
        "   (3 пива + 2 закуски на выбор)\n"
        "• 'Гранд-финал' - 5000₽\n"
        "   (шампанское + сет закусок)\n\n"
        "🎯 АКЦИИ И ПРЕДЛОЖЕНИЯ:\n"
        "• Каждый головой удар - скидка 10%\n"
        "• При бронировании столика - фри начос\n"
        "• В день матча - спец. цены на пиво\n\n"
        "🍻 ЖДЕМ ТЕБЯ В НАШЕМ БАРЕ!"
    )
    
    await callback.message.edit_text(
        menu_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📞 ЗАБРОНИРОВАТЬ СТОЛИК", url="https://t.me/username")],
            [InlineKeyboardButton(text="📍 КАК ДОЕХАТЬ", url="https://yandex.ru/maps")],
            [InlineKeyboardButton(text="🎮 ПОСМОТРЕТЬ МАТЧИ", callback_data="refresh")],
            [InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="refresh")]
        ])
    )
    await callback.answer("🍻 Наше меню!")

# ========== ЗАПУСК БОТА ==========

async def on_startup():
    """Действия при запуске бота"""
    logger.info("Бот Sports Bar TV запущен!")
    
    # Уведомление админам
    startup_msg = (
        "╔══════════════════════════════╗\n"
        "║     🍻 БАР ЗАПУЩЕН! 🍻      ║\n"
        "╚══════════════════════════════╝\n\n"
        "✅ Sports Bar TV Bot готов к работе!\n"
        f"🎮 Отслеживаем игры: {', '.join([g['name'] for g in GAMES.values()])}\n"
        "🍻 Ожидаем гостей в баре!"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, startup_msg)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def on_shutdown():
    """Действия при выключении бота"""
    logger.info("Закрываем бар на сегодня...")
    await panda_api.close()
    await bot.session.close()

async def main():
    """Основная функция запуска"""
    await on_startup()
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    # Проверка обязательных переменных
    if not PANDASCORE_TOKEN:
        logger.error("PANDASCORE_TOKEN не установлен! Не сможем показывать матчи!")
        exit(1)
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен! Бот не сможет запуститься!")
        exit(1)
    
    logger.info("=" * 50)
    logger.info("🍻 ЗАПУСКАЕМ SPORTS BAR TV BOT...")
    logger.info("🎮 Отслеживаем CS2 и Dota 2 матчи")
    logger.info("🍻 Все время в формате MSK (Москва)")
    logger.info("=" * 50)
    
    # Запуск бота
    asyncio.run(main())
