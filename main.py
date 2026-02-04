import os
import asyncio
import logging
import json
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== DEEPSEEK НЕЙРОСЕТЬ ==========
try:
    from openai import AsyncOpenAI
    DEEPSEEK_AVAILABLE = True
    logger.info("✅ OpenAI/DeepSeek библиотека доступна")
except ImportError:
    DEEPSEEK_AVAILABLE = False
    logger.warning("❌ OpenAI библиотека не установлена")

class DeepSeekNeuralNetwork:
    """Настоящая нейросеть DeepSeek для анализа CS2 матчей"""
    
    def __init__(self):
        self.active = False
        
        logger.info("🧠 Инициализация нейросети DeepSeek...")
        
        if DEEPSEEK_AVAILABLE and DEEPSEEK_API_KEY:
            try:
                # Создаем клиент DeepSeek
                self.client = AsyncOpenAI(
                    api_key=DEEPSEEK_API_KEY,
                    base_url="https://api.deepseek.com"
                )
                self.active = True
                logger.info("✅ DeepSeek нейросеть активирована")
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации DeepSeek: {e}")
                self.active = False
        else:
            if not DEEPSEEK_AVAILABLE:
                logger.warning("⚠️ Библиотека openai не установлена")
            if not DEEPSEEK_API_KEY:
                logger.warning("⚠️ DEEPSEEK_API_KEY не найден")
            self.active = False
    
    async def analyze_match(self, team1: str, team2: str, tournament: str = "", 
                          match_time: str = "") -> Dict:
        """Анализ матча настоящей нейросетью DeepSeek"""
        
        if not self.active:
            raise Exception("Нейросеть не активирована. Проверьте DEEPSEEK_API_KEY")
        
        try:
            # Строим промпт для анализа в стиле БАРА
            prompt = self._build_bar_analysis_prompt(team1, team2, tournament, match_time)
            
            logger.info(f"🍺 Бармен анализирует матч: {team1} vs {team2}")
            
            # Запрос к нейросети
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system", 
                        "content": """Ты опытный бармен и аналитик киберспорта. Ты работаешь в CS2-баре и даешь 
                        экспертные прогнозы на матчи. Твои анализы всегда точные, с юмором и в стиле бара. 
                        Отвечай строго в JSON формате."""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,  # Немного креативности для бара
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            # Парсинг ответа
            result = json.loads(response.choices[0].message.content)
            logger.info(f"✅ Бармен завершил анализ")
            
            # Добавляем метаданные
            result["source"] = "Барный аналитик DeepSeek"
            result["analysis_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            result["bar_name"] = "CS2 Бар 'HeadShot'"
            
            return result
            
        except asyncio.TimeoutError:
            raise Exception("🕐 Бармен слишком занят, попробуйте позже")
        except json.JSONDecodeError as e:
            raise Exception("🍻 Бармен перебрал и написал неразборчиво")
        except Exception as e:
            raise Exception(f"🍺 Ошибка в баре: {str(e)}")
    
    def _build_bar_analysis_prompt(self, team1: str, team2: str, tournament: str, 
                                 match_time: str) -> str:
        """Построение промпта для анализа в стиле БАРА"""
        return f"""
        Дорогой бармен-аналитик!

        У нас в баре "HeadShot" спорят о предстоящем матче CS2.
        
        🎯 МАТЧ: {team1} vs {team2}
        🏆 ТУРНИР: {tournament if tournament else 'Обычная вечеринка'}
        🕐 ВРЕМЯ: {match_time if match_time else 'Когда бар будет полон'}
        
        Как опытный бармен и знаток CS2, проанализируй этот матч и дай:
        1. Силу команд (сколько "кружек пива" каждая команда заслуживает)
        2. Прогноз победителя и счета
        3. Ключевые моменты матча
        4. Рекомендации по ставкам (какой "коктейль" выбрать)
        5. Забавный анализ в стиле бара
        
        Верни ответ в следующем JSON формате:
        {{
          "bar_intro": "забавное вступление о матче в стиле бара",
          "team1_analysis": {{
            "strength": "число от 0 до 100 (сколько кружек пива)",
            "current_form": "описание формы в стиле бара",
            "key_strengths": ["сильные стороны как у напитков"],
            "weaknesses": ["слабые стороны как у плохого пива"],
            "bar_nickname": "забавное прозвище команды в баре"
          }},
          "team2_analysis": {{ ... }},
          "match_prediction": {{
            "likely_winner": "название команды",
            "probability": "число от 0 до 100",
            "score_prediction": "2:0, 2:1 и т.д.",
            "confidence": "число от 0 до 100 (уверенность бармена)",
            "risk_level": "LOW/MEDIUM/HIGH (риск как у напитков)",
            "bar_metaphor": "сравнение матча с коктейлем"
          }},
          "key_factors": ["ключевые моменты в стиле бара", "еще момент"],
          "recommended_bets": [
            {{
              "type": "тип ставки (например: П1, Тотал)",
              "reason": "обоснование в стиле бара",
              "confidence": "LOW/MEDIUM/HIGH",
              "bar_drink": "рекомендуемый напиток для этой ставки"
            }}
          ],
          "detailed_analysis": "развернутый анализ на 3-5 предложений в стиле бара",
          "bar_tip": "совет бармена на матч",
          "funny_comment": "забавный комментарий о матче"
        }}
        
        Будь креативным, забавным и точным! Добавь барного юмора!
        """

# ========== ПАРСИНГ МАТЧЕЙ ==========
class PandaScoreAPI:
    """API клиент для CS2"""
    
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
    
    async def get_today_matches(self):
        """Получить матчи на сегодня"""
        try:
            session = await self.get_session()
            
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today.isoformat()},{tomorrow.isoformat()}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started,running"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    all_matches = await response.json()
                    
                    # Фильтруем по точной дате
                    today_matches = []
                    for match in all_matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                if 'Z' in scheduled_at:
                                    match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                else:
                                    match_time = datetime.fromisoformat(scheduled_at)
                                
                                if match_time.date() == today:
                                    today_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"🍺 Найдено матчей на сегодня: {len(today_matches)}")
                    return today_matches
                else:
                    logger.error(f"API error: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"🍻 Ошибка при получении матчей: {e}")
            return []
    
    async def get_tomorrow_matches(self):
        """Получить матчи на завтра"""
        try:
            session = await self.get_session()
            
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after = today + timedelta(days=2)
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{tomorrow.isoformat()},{day_after.isoformat()}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    all_matches = await response.json()
                    
                    tomorrow_matches = []
                    for match in all_matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                if 'Z' in scheduled_at:
                                    match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                else:
                                    match_time = datetime.fromisoformat(scheduled_at)
                                
                                if match_time.date() == tomorrow:
                                    tomorrow_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"🍺 Найдено матчей на завтра: {len(tomorrow_matches)}")
                    return tomorrow_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"🍻 Ошибка: {e}")
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
                    logger.info(f"🔥 Найдено live матчей: {len(matches)}")
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"🍻 Ошибка: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_match_time(scheduled_at: str) -> str:
    """Форматирование времени в MSK"""
    try:
        if 'Z' in scheduled_at:
            dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        else:
            dt_utc = datetime.fromisoformat(scheduled_at)
        
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%H:%M")
    except:
        return "Скоро"

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд"""
    if not team_name:
        return "🍺"
    
    team_lower = team_name.lower()
    
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
        return "🐆"
    elif "mouz" in team_lower:
        return "🐭"
    
    return "🎮"

def get_drink_emoji(drink_type: str) -> str:
    """Эмодзи для напитков"""
    drink_emojis = {
        "пиво": "🍺",
        "вино": "🍷",
        "виски": "🥃",
        "коктейль": "🍸",
        "шампанское": "🍾",
        "водка": "🥂",
        "ром": "🏝️",
        "джин": "🍶",
        "текила": "🌵",
        "кофе": "☕",
        "чай": "🫖",
        "энергетик": "⚡",
        "смузи": "🥤",
        "вода": "💧"
    }
    
    for drink, emoji in drink_emojis.items():
        if drink in drink_type.lower():
            return emoji
    
    return "🥤"

# ========== КЛАВИАТУРЫ ==========
def create_main_keyboard():
    """Главное меню бара"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍺 МАТЧИ СЕГОДНЯ", callback_data="today"),
            InlineKeyboardButton(text="🍻 МАТЧИ ЗАВТРА", callback_data="tomorrow")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE МАТЧИ", callback_data="live"),
            InlineKeyboardButton(text="🎯 АНАЛИЗ ОТ БАРМЕНА", callback_data="analyze_bar")
        ],
        [
            InlineKeyboardButton(text="⚙️ НАСТРОЙКИ БАРА", callback_data="settings"),
            InlineKeyboardButton(text="ℹ️ О БАРЕ", callback_data="about")
        ],
        [
            InlineKeyboardButton(text="🍸 ЗАКАЗАТЬ АНАЛИЗ", callback_data="custom_analysis")
        ]
    ])
    return keyboard

def create_match_selection_keyboard(matches: List[Dict], prefix: str = "analyze"):
    """Клавиатура для выбора матча"""
    buttons = []
    
    for i, match in enumerate(matches[:8]):  # Максимум 8 матчей
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            time_str = format_match_time(match.get("scheduled_at", ""))
            
            button_text = f"{team1_name} 🆚 {team2_name} ({time_str})"
            if len(button_text) > 40:
                button_text = button_text[:37] + "..."
            
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"{prefix}_{i}"
            )])
    
    buttons.append([
        InlineKeyboardButton(text="🍺 В БАР", callback_data="back"),
        InlineKeyboardButton(text="🏠 ГЛАВНАЯ", callback_data="home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_analysis_keyboard(match_index: int):
    """Клавиатура для анализа матча"""
    buttons = [
        [
            InlineKeyboardButton(text="🎯 ДЕТАЛЬНЫЙ АНАЛИЗ", callback_data=f"full_analysis_{match_index}"),
            InlineKeyboardButton(text="🍸 РЕКОМЕНДАЦИИ", callback_data=f"recommendations_{match_index}")
        ],
        [
            InlineKeyboardButton(text="⚡ БЫСТРЫЙ ПРОГНОЗ", callback_data=f"quick_pred_{match_index}"),
            InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data=f"stats_{match_index}")
        ],
        [
            InlineKeyboardButton(text="🍻 ВЫБРАТЬ ДРУГОЙ МАТЧ", callback_data="analyze_bar"),
            InlineKeyboardButton(text="🍺 В БАР", callback_data="back")
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)
neural_network = DeepSeekNeuralNetwork()

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт - вход в бар"""
    neural_status = "✅ БАРМЕН НА МЕСТЕ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    
    welcome = f"""
{get_drink_emoji("пиво")} <b>ДОБРО ПОЖАЛОВАТЬ В CS2 БАР "HEADSHOT"!</b>

<i>Здесь анализируют киберспорт с бокалом пенного!</i>

<b>{get_drink_emoji("коктейль")} Ваш бармен-аналитик:</b> {neural_status}
<b>📊 Источник матчей:</b> PandaScore API
<b>🕐 Время:</b> MSK (Москва)

<b>{get_drink_emoji("виски")} Что предлагает бар:</b>
• 🍺 Расписание матчей на сегодня/завтра
• 🔥 LIVE трансляции с комментариями
• 🎯 Экспертный анализ от бармена
• 📈 Прогнозы с "вкусом" победы
• ⚡ Быстрые и креативные отчеты

{get_drink_emoji("шампанское")} <b>Специальное предложение:</b>
Закажи анализ матча и получи рекомендацию по напитку!

{"⚠️ <b>Бармен отдыхает! Добавьте DEEPSEEK_API_KEY для активации</b>" if not neural_network.active else "✅ <b>Бар готов к работе! Заказывайте анализы!</b>"}

👇 <b>Выберите действие:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "today")
async def handle_today(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("🍺 Смотрю расписание на сегодня...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            f"🍻 <b>СЕГОДНЯ В БАРЕ ТИХО</b>\n\n"
            f"На {datetime.now().strftime('%d.%m.%Y')} нет запланированных матчей CS2.\n\n"
            f"<i>Может, заглянем на завтра или посмотрим live трансляции?</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"{get_drink_emoji('пиво')} <b>МАТЧИ В БАРЕ СЕГОДНЯ</b>",
        f"<i>{datetime.now().strftime('%d.%m.%Y')}</i>",
        f"",
        f"📊 Найдено матчей: {len(matches)}",
        "─" * 40,
        f""
    ]
    
    for i, match in enumerate(matches[:10], 1):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            
            team1_emoji = get_team_emoji(team1_name)
            team2_emoji = get_team_emoji(team2_name)
            
            time_str = format_match_time(match.get("scheduled_at", ""))
            league = match.get("league", {}).get("name", "")
            
            lines.append(f"{i}. {team1_emoji} <b>{team1_name}</b> 🆚 {team2_emoji} <b>{team2_name}</b>")
            lines.append(f"   🕐 {time_str} | 🏆 {league[:20]}" + ("..." if len(league) > 20 else ""))
            lines.append(f"")
    
    lines.append(f"<i>🕐 Время указано в MSK</i>")
    lines.append(f"<i>🍸 Выберите матч для анализа барменом</i>")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 АНАЛИЗ ОТ БАРМЕНА", callback_data="analyze_bar")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "tomorrow")
async def handle_tomorrow(callback: types.CallbackQuery):
    """Матчи завтра"""
    await callback.answer("🍻 Смотрю расписание на завтра...")
    
    matches = await panda_api.get_tomorrow_matches()
    
    if not matches:
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
        await callback.message.edit_text(
            f"🍺 <b>ЗАВТРА БАР ЗАКРЫТ НА САНИТАРНЫЙ ДЕНЬ</b>\n\n"
            f"На {tomorrow_date} нет запланированных матчей CS2.\n\n"
            f"<i>Загляните сегодня или отдохните с нами!</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
    lines = [
        f"{get_drink_emoji('вино')} <b>МАТЧИ В БАРЕ ЗАВТРА</b>",
        f"<i>{tomorrow_date}</i>",
        f"",
        f"📊 Найдено матчей: {len(matches)}",
        "─" * 40,
        f""
    ]
    
    for i, match in enumerate(matches[:6], 1):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            
            team1_emoji = get_team_emoji(team1_name)
            team2_emoji = get_team_emoji(team2_name)
            
            time_str = format_match_time(match.get("scheduled_at", ""))
            league = match.get("league", {}).get("name", "")
            
            lines.append(f"{i}. {team1_emoji} <b>{team1_name}</b> 🆚 {team2_emoji} <b>{team2_name}</b>")
            lines.append(f"   🕐 {time_str} | 🏆 {league[:20]}" + ("..." if len(league) > 20 else ""))
            lines.append(f"")
    
    lines.append(f"<i>🕐 Время указано в MSK</i>")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "live")
async def handle_live(callback: types.CallbackQuery):
    """Live матчи"""
    await callback.answer("🔥 Ищу live матчи...")
    
    matches = await panda_api.get_live_matches()
    
    if not matches:
        await callback.message.edit_text(
            f"🍻 <b>В БАРЕ СЕЙЧАС ТИШИНА</b>\n\n"
            f"В данный момент нет live матчей CS2.\n\n"
            f"<i>Проверьте расписание или закажите анализ будущих матчей!</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    lines = [
        f"🔥 <b>LIVE МАТЧИ В БАРЕ</b>",
        f"",
        f"📊 Матчей в эфире: {len(matches)}",
        "─" * 40,
        f""
    ]
    
    for i, match in enumerate(matches, 1):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            
            # Счет
            results = match.get("results", [])
            score1 = results[0].get("score", 0) if len(results) > 0 else 0
            score2 = results[1].get("score", 0) if len(results) > 1 else 0
            
            team1_emoji = get_team_emoji(team1_name)
            team2_emoji = get_team_emoji(team2_name)
            
            league = match.get("league", {}).get("name", "")
            
            lines.append(f"{i}. 🔴 {team1_emoji} <b>{team1_name}</b> {score1}:{score2} <b>{team2_name}</b> {team2_emoji}")
            lines.append(f"   🏆 {league}")
            
            # Ссылка на трансляцию если есть
            stream_url = match.get("official_stream_url")
            if stream_url:
                lines.append(f"   📺 <a href='{stream_url}'>Смотреть в баре</a>")
            
            lines.append(f"")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "analyze_bar")
async def handle_analyze_bar(callback: types.CallbackQuery):
    """Выбор матча для анализа барменом"""
    await callback.answer("🎯 Бармен готовит инструменты...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            f"🍻 <b>БАРМЕНУ НЕЧЕГО АНАЛИЗИРОВАТЬ</b>\n\n"
            f"Сегодня нет матчей для анализа.\n\n"
            f"<i>Загляните завтра или отдохните с напитком!</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    neural_status = "✅ БАРМЕН ГОТОВ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    
    await callback.message.edit_text(
        f"{get_drink_emoji('коктейль')} <b>ВЫБЕРИТЕ МАТЧ ДЛЯ АНАЛИЗА</b>\n\n"
        f"🍺 Найдено матчей на сегодня: {len(matches)}\n"
        f"🎯 Состояние бармена: {neural_status}\n\n"
        f"{'🍸 Бармен приготовит для вас экспертный анализ с юмором!' if neural_network.active else '⚠️ Бармен отдыхает. Активируйте нейросеть для анализа.'}",
        reply_markup=create_match_selection_keyboard(matches, "bar_analyze")
    )

@dp.callback_query(F.data.startswith("bar_analyze_"))
async def handle_bar_analysis(callback: types.CallbackQuery):
    """Анализ матча барменом"""
    match_index = int(callback.data.split("_")[2])
    await callback.answer("🎯 Бармен анализирует матч...")
    
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.message.edit_text(
            f"🍻 <b>МАТЧ НЕ НАЙДЕН</b>\n\n"
            f"<i>Возможно, матч уже завершился или отменен.</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    match = matches[match_index]
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        await callback.message.edit_text(
            f"🍺 <b>НЕДОСТАТОЧНО ИНГРЕДИЕНТОВ</b>\n\n"
            f"<i>Бармену нужны данные обеих команд для анализа.</i>",
            reply_markup=create_main_keyboard()
        )
        return
    
    team1 = opponents[0].get("opponent", {})
    team2 = opponents[1].get("opponent", {})
    
    team1_name = team1.get("acronym") or team1.get("name", "TBA")
    team2_name = team2.get("acronym") or team2.get("name", "TBA")
    tournament = match.get("league", {}).get("name", "")
    time_str = format_match_time(match.get("scheduled_at", ""))
    
    # Показываем статус анализа
    await callback.message.edit_text(
        f"{get_drink_emoji('виски')} <b>АНАЛИЗ МАТЧА ОТ БАРМЕНА</b>\n\n"
        f"🎯 <b>{team1_name} vs {team2_name}</b>\n"
        f"🕐 {time_str} MSK | 🏆 {tournament}\n\n"
        f"🍸 <b>Статус:</b> Бармен готовит для вас особый анализ...",
        disable_web_page_preview=True
    )
    
    # Получаем анализ от нейросети
    try:
        if not neural_network.active:
            raise Exception("Бармен отдыхает. Активируйте нейросеть!")
        
        analysis = await neural_network.analyze_match(
            team1_name, team2_name, tournament, time_str
        )
        
        # Формируем результат в стиле бара
        prediction = analysis.get("match_prediction", {})
        team1_analysis = analysis.get("team1_analysis", {})
        team2_analysis = analysis.get("team2_analysis", {})
        
        lines = [
            f"{get_drink_emoji('шампанское')} <b>АНАЛИЗ ОТ БАРМЕНА</b>",
            f"<i>Бар «HeadShot», {analysis.get('analysis_time', '')}</i>",
            f"",
            f"{analysis.get('bar_intro', '🎯 Интересный матч в нашем баре!')}",
            f"",
            f"🎯 <b>МАТЧ:</b> {team1_name} 🆚 {team2_name}",
            f"🕐 {time_str} MSK | 🏆 {tournament}",
            f"",
            f"🍺 <b>БАРНЫЙ ПРОГНОЗ:</b>",
            f"• Победитель: <b>{prediction.get('likely_winner', '?')}</b>",
            f"• Вероятность: <b>{prediction.get('probability', 0):.1f}%</b>",
            f"• Счет: <b>{prediction.get('score_prediction', '?')}</b>",
            f"• Уверенность бармена: <b>{prediction.get('confidence', 0):.1f}%</b>",
            f"• Риск: <b>{prediction.get('risk_level', 'MEDIUM')}</b>",
            f"• {prediction.get('bar_metaphor', 'Крепкий матч как хороший виски')}",
            f"",
            f"⚡ <b>СИЛА КОМАНД (в кружках пива):</b>",
            f"• {team1_analysis.get('bar_nickname', team1_name)}: {team1_analysis.get('strength', 0):.0f}/100",
            f"• {team2_analysis.get('bar_nickname', team2_name)}: {team2_analysis.get('strength', 0):.0f}/100",
            f"",
            f"🍸 <b>БАРНЫЕ РЕКОМЕНДАЦИИ:</b>"
        ]
        
        # Добавляем рекомендации
        recommended_bets = analysis.get("recommended_bets", [])
        if recommended_bets:
            for bet in recommended_bets[:2]:
                drink_emoji = get_drink_emoji(bet.get('bar_drink', 'коктейль'))
                lines.append(f"• {drink_emoji} <b>{bet.get('type', 'Нет данных')}</b>")
                if bet.get('reason'):
                    lines.append(f"  <i>{bet['reason']}</i>")
                lines.append(f"  Уверенность: {bet.get('confidence', 'MEDIUM')}")
        else:
            lines.append("• Пока отдыхайте и наблюдайте за игрой")
        
        lines.extend([
            f"",
            f"🎯 <b>КЛЮЧЕВЫЕ МОМЕНТЫ:</b>"
        ])
        
        # Добавляем ключевые факторы
        key_factors = analysis.get("key_factors", [])
        for factor in key_factors[:3]:
            lines.append(f"• {factor}")
        
        # Забавный комментарий
        if analysis.get('funny_comment'):
            lines.extend([
                f"",
                f"😄 <b>КОММЕНТАРИЙ БАРМЕНА:</b>",
                f"{analysis.get('funny_comment')}"
            ])
        
        lines.extend([
            f"",
            f"💡 <b>СОВЕТ БАРМЕНА:</b> {analysis.get('bar_tip', 'Наслаждайтесь игрой!')}",
            f"",
            f"⚠️ <i>Анализ от бармена. Играйте ответственно и с удовольствием!</i>"
        ])
        
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=create_analysis_keyboard(match_index),
            disable_web_page_preview=True
        )
        
    except Exception as e:
        error_message = str(e)
        await callback.message.edit_text(
            f"🍻 <b>ОШИБКА В БАРЕ</b>\n\n"
            f"Бармен не смог проанализировать матч:\n"
            f"<code>{error_message}</code>\n\n"
            f"<i>Попробуйте другой матч или загляните позже!</i>",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data.startswith("full_analysis_"))
async def handle_full_analysis(callback: types.CallbackQuery):
    """Полный анализ матча"""
    match_index = int(callback.data.split("_")[2])
    
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.answer("🍺 Матч не найден")
        return
    
    match = matches[match_index]
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        await callback.answer("🍻 Недостаточно данных")
        return
    
    team1 = opponents[0].get("opponent", {})
    team2 = opponents[1].get("opponent", {})
    
    team1_name = team1.get("acronym") or team1.get("name", "TBA")
    team2_name = team2.get("acronym") or team2.get("name", "TBA")
    tournament = match.get("league", {}).get("name", "")
    time_str = format_match_time(match.get("scheduled_at", ""))
    
    # Получаем анализ
    try:
        if not neural_network.active:
            raise Exception("Бармен отдыхает")
        
        analysis = await neural_network.analyze_match(
            team1_name, team2_name, tournament, time_str
        )
        
        # Форматируем полный анализ
        lines = [
            f"{get_drink_emoji('виски')} <b>ПОЛНЫЙ АНАЛИЗ ОТ БАРМЕНА</b>",
            f"",
            f"🎯 <b>{team1_name} 🆚 {team2_name}</b>",
            f"🕐 {time_str} MSK | 🏆 {tournament}",
            f"",
            f"🍺 <b>АНАЛИЗ {team1_analysis.get('bar_nickname', team1_name)}:</b>",
            f"• Сила: {analysis.get('team1_analysis', {}).get('strength', 0):.0f}/100 кружек",
            f"• Форма: {analysis.get('team1_analysis', {}).get('current_form', 'Нет данных')}",
            f"• Сильные стороны (как у хорошего напитка):",
        ]
        
        strengths1 = analysis.get('team1_analysis', {}).get('key_strengths', [])
        for strength in strengths1[:3]:
            lines.append(f"  - {strength}")
        
        lines.extend([
            f"• Слабые стороны (как у плохого пива):",
        ])
        
        weaknesses1 = analysis.get('team1_analysis', {}).get('weaknesses', [])
        for weakness in weaknesses1[:3]:
            lines.append(f"  - {weakness}")
        
        lines.extend([
            f"",
            f"🍻 <b>АНАЛИЗ {team2_analysis.get('bar_nickname', team2_name)}:</b>",
            f"• Сила: {analysis.get('team2_analysis', {}).get('strength', 0):.0f}/100 кружек",
            f"• Форма: {analysis.get('team2_analysis', {}).get('current_form', 'Нет данных')}",
            f"• Сильные стороны:",
        ])
        
        strengths2 = analysis.get('team2_analysis', {}).get('key_strengths', [])
        for strength in strengths2[:3]:
            lines.append(f"  - {strength}")
        
        lines.extend([
            f"• Слабые стороны:",
        ])
        
        weaknesses2 = analysis.get('team2_analysis', {}).get('weaknesses', [])
        for weakness in weaknesses2[:3]:
            lines.append(f"  - {weakness}")
        
        lines.extend([
            f"",
            f"🎯 <b>ДЕТАЛЬНЫЙ АНАЛИЗ БАРМЕНА:</b>",
            f"{analysis.get('detailed_analysis', 'Нет детального анализа')}",
            f"",
            f"📊 <b>Источник:</b> {analysis.get('source', 'Бармен')}",
            f"🕒 <b>Время анализа:</b> {analysis.get('analysis_time', 'Неизвестно')}",
            f"🍸 <b>Бар:</b> {analysis.get('bar_name', 'CS2 Бар «HeadShot»')}",
        ])
        
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=create_analysis_keyboard(match_index),
            disable_web_page_preview=True
        )
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"🍻 Ошибка: {str(e)[:30]}...")

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    """Настройки бара"""
    neural_status = "✅ БАРМЕН НА МЕСТЕ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    
    lines = [
        f"{get_drink_emoji('коктейль')} <b>НАСТРОЙКИ БАРА</b>",
        f"",
        f"🍸 <b>Состояние бармена:</b> {neural_status}",
        f"📊 <b>Источник матчей:</b> PandaScore API",
        f"🕐 <b>Часовой пояс:</b> MSK (UTC+3)",
        f"",
        f"⚙️ <b>КАК АКТИВИРОВАТЬ БАРМЕНА:</b>",
        f"1. Получите API ключ на https://platform.deepseek.com",
        f"2. Добавьте в Railway Variables: DEEPSEEK_API_KEY",
        f"3. Перезапустите бар",
        f"",
        f"🎯 <b>ПРЕИМУЩЕСТВА БАРМЕНА:</b>",
        f"• Анализ с юмором и креативом",
        f"• Учет формы, состава, тактики",
        f"• Прогнозы с барными метафорами",
        f"• Рекомендации по напиткам",
        f"",
        f"💡 <b>ТЕКУЩИЙ СТАТУС:</b>",
        f"{'🍸 Бармен готов к работе! Заказывайте анализы!' if neural_network.active else '🍺 Бармен отдыхает. Активируйте для полного функционала.'}"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ БАРМЕНА", callback_data="check_bartender")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "check_bartender")
async def handle_check_bartender(callback: types.CallbackQuery):
    """Проверка состояния бармена"""
    # Переинициализируем нейросеть
    neural_network.__init__()
    
    neural_status = "✅ БАРМЕН ГОТОВ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    await callback.answer(f"Статус: {neural_status}")
    
    lines = [
        f"{get_drink_emoji('шампанское')} <b>ПРОВЕРКА БАРМЕНА</b>",
        f"",
        f"🍸 <b>Состояние бармена:</b> {neural_status}",
        f"🕒 <b>Время проверки:</b> {datetime.now().strftime('%H:%M:%S')}",
        f"",
        f"{'🎯 Бармен успешно проверен и готов к работе!' if neural_network.active else '🍺 Бармен не доступен. Проверьте DEEPSEEK_API_KEY'}",
        f"",
        f"<i>Бар «HeadShot» всегда к вашим услугам!</i>"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍸 ЗАКАЗАТЬ АНАЛИЗ", callback_data="analyze_bar")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "about")
async def handle_about(callback: types.CallbackQuery):
    """О баре"""
    about_text = f"""
{get_drink_emoji('пиво')} <b>О БАРЕ «HEADSHOT»</b>

<i>Где киберспорт встречается с хорошими напитками!</i>

{get_drink_emoji('коктейль')} <b>НАША ФИЛОСОФИЯ:</b>
Анализируем CS2 с бокалом в руке и юмором в сердце!

{get_drink_emoji('виски')} <b>ЧТО МЫ ДЕЛАЕМ:</b>
• 🎯 Анализируем матчи с помощью AI
• 📊 Даем экспертные прогнозы
• 🍸 Рекомендуем напитки под настроение
• 😄 Добавляем юмора и креатива

{get_drink_emoji('вино')} <b>НАШ БАРМЕН:</b>
Опытный аналитик с нейросетью DeepSeek, который знает о CS2 всё и даже больше!

{get_drink_emoji('шампанское')} <b>ПОЧЕМУ МЫ:</b>
• Уникальный барный стиль анализа
• Креативные метафоры и сравнения
• Честные и объективные прогнозы
• Атмосфера настоящего киберспорт-бара

{get_drink_emoji('энергетик')} <b>ВАЖНО:</b>
• Анализы для удовольствия и информации
• Играйте ответственно (21+)
• Наслаждайтесь игрой и хорошей компанией

<i>Заходите к нам чаще - в баре всегда интересно! 🍻</i>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍸 ЗАКАЗАТЬ АНАЛИЗ", callback_data="analyze_bar")],
        [InlineKeyboardButton(text="⚙️ НАСТРОЙКИ БАРА", callback_data="settings")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        about_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "custom_analysis")
async def handle_custom_analysis(callback: types.CallbackQuery):
    """Заказ анализа"""
    await callback.answer("🎯 Готовим бланк заказа...")
    
    lines = [
        f"{get_drink_emoji('коктейль')} <b>ЗАКАЗ АНАЛИЗА ОТ БАРМЕНА</b>",
        f"",
        f"🍸 <b>Как заказать анализ:</b>",
        f"1. Используйте команду /analyze Team1 Team2",
        f"2. Укажите турнир (опционально)",
        f"",
        f"🎯 <b>Примеры:</b>",
        f"<code>/analyze NAVI Vitality</code>",
        f"<code>/analyze FaZe G2 ESL Pro League</code>",
        f"",
        f"🍺 <b>Что вы получите:</b>",
        f"• Экспертный анализ матча",
        f"• Прогноз победителя и счета",
        f"• Рекомендации по ставкам",
        f"• Советы по напиткам",
        f"• Забавный комментарий от бармена",
        f"",
        f"<i>Бармен готовится к вашему заказу! 🎯</i>"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 ПРОАНАЛИЗИРОВАТЬ", callback_data="analyze_bar")],
        [InlineKeyboardButton(text="🍺 В БАР", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "back")
@dp.callback_query(F.data == "home")
async def handle_back(callback: types.CallbackQuery):
    """Назад в главное меню"""
    await cmd_start(callback.message)
    await callback.answer()

# ========== КОМАНДЫ ==========
@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Проверка статуса бара"""
    neural_status = "✅ БАРМЕН НА МЕСТЕ" if neural_network.active else "❌ БАРМЕН ОТДЫХАЕТ"
    
    status_text = (
        f"{get_drink_emoji('пиво')} <b>СТАТУС БАРА «HEADSHOT»</b>\n\n"
        f"• Бармен: {neural_status}\n"
        f"• API PandaScore: {'✅' if PANDASCORE_TOKEN else '❌'}\n"
        f"• Бар: ✅ ОТКРЫТ\n"
        f"• Время: {datetime.now().strftime('%d.%m.%Y %H:%M MSK')}\n\n"
    )
    
    if neural_network.active:
        status_text += f"{get_drink_emoji('шампанское')} <b>Бармен готов к работе!</b>\n"
        status_text += f"Используйте /analyze для заказа анализа"
    else:
        status_text += f"{get_drink_emoji('пиво')} <b>Для активации бармена:</b>\n"
        status_text += f"1. Получите ключ на platform.deepseek.com\n"
        status_text += f"2. Добавьте DEEPSEEK_API_KEY в Railway Variables\n"
        status_text += f"3. Перезапустите бар"
    
    await message.answer(status_text)

@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    """Быстрый анализ через команду"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            f"🍻 <b>ИСПОЛЬЗУЙТЕ:</b> <code>/analyze NAVI Vitality</code>\n"
            f"или <code>/analyze NAVI Vitality ESL Pro League</code>"
        )
        return
    
    team1 = args[1]
    team2 = args[2]
    tournament = " ".join(args[3:]) if len(args) > 3 else ""
    
    status_msg = await message.answer(f"{get_drink_emoji('коктейль')} <b>Бармен анализирует: {team1} vs {team2}...</b>")
    
    try:
        if not neural_network.active:
            raise Exception("Бармен отдыхает. Активируйте нейросеть!")
        
        analysis = await neural_network.analyze_match(team1, team2, tournament)
        prediction = analysis.get("match_prediction", {})
        
        result = (
            f"{get_drink_emoji('шампанское')} <b>АНАЛИЗ ОТ БАРМЕНА</b>\n\n"
            f"🎯 <b>{team1} 🆚 {team2}</b>\n"
            f"{'🏆 ' + tournament if tournament else ''}\n\n"
            f"🍺 <b>ПРОГНОЗ БАРМЕНА:</b>\n"
            f"• Победитель: <b>{prediction.get('likely_winner', '?')}</b>\n"
            f"• Вероятность: <b>{prediction.get('probability', 0):.1f}%</b>\n"
            f"• Счет: <b>{prediction.get('score_prediction', '?')}</b>\n"
            f"• Риск: <b>{prediction.get('risk_level', 'MEDIUM')}</b>\n"
            f"• {prediction.get('bar_metaphor', 'Интересный матч!')}\n\n"
            f"🍸 <i>Анализ от бармена с нейросетью DeepSeek</i>"
        )
        
        await status_msg.edit_text(result)
        
    except Exception as e:
        await status_msg.edit_text(
            f"🍻 <b>ОШИБКА В БАРЕ</b>\n\n"
            f"Бармен не смог проанализировать:\n"
            f"<code>{str(e)}</code>"
        )

@dp.message(Command("bar"))
async def cmd_bar(message: types.Message):
    """Информация о баре"""
    await cmd_start(message)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь"""
    help_text = f"""
{get_drink_emoji('пиво')} <b>ПОМОЩЬ ПО БАРУ «HEADSHOT»</b>

{get_drink_emoji('коктейль')} <b>КОМАНДЫ:</b>
• /start - Вход в бар
• /status - Статус бара
• /analyze Team1 Team2 - Анализ матча
• /bar - Главное меню бара
• /help - Эта справка

{get_drink_emoji('виски')} <b>ВОЗМОЖНОСТИ:</b>
• Просмотр расписания матчей
• Live трансляции
• Анализ от бармена с AI
• Прогнозы и рекомендации
• Барный юмор и креатив

{get_drink_emoji('вино')} <b>КАК РАБОТАЕТ БАРМЕН:</b>
1. Получает данные о матчах
2. Анализирует с помощью нейросети DeepSeek
3. Добавляет барный стиль и юмор
4. Дает экспертные рекомендации

{get_drink_emoji('энергетик')} <b>ВАЖНО:</b>
• Для работы бармена нужен DEEPSEEK_API_KEY
• Анализы для информации и удовольствия
• Играйте ответственно
• Наслаждайтесь атмосферой бара!

<i>Заходите чаще - у нас всегда интересно! 🍻</i>
"""
    
    await message.answer(help_text, disable_web_page_preview=True)

# ========== ЗАПУСК БАРА ==========

async def main():
    """Запуск бара"""
    logger.info("=" * 50)
    logger.info("🍺 ЗАПУСК CS2 БАРА «HEADSHOT»")
    logger.info("=" * 50)
    
    # Проверка конфигурации
    logger.info(f"🎯 Состояние бармена: {'✅ НА МЕСТЕ' if neural_network.active else '❌ ОТДЫХАЕТ'}")
    logger.info(f"📊 PandaScore API: {'✅' if PANDASCORE_TOKEN else '❌'}")
    logger.info(f"🔑 Telegram Bot: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")
    logger.info("🕐 Часовой пояс: MSK (UTC+3)")
    
    if not PANDASCORE_TOKEN:
        logger.error("❌ Нет токена PandaScore! Добавьте PANDASCORE_TOKEN в Railway Variables")
        return
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Нет токена Telegram! Добавьте TELEGRAM_BOT_TOKEN в Railway Variables")
        return
    
    if not neural_network.active:
        logger.warning("⚠️ Бармен отдыхает. Активируйте нейросеть для полного функционала.")
        logger.info("💡 Для активации добавьте DEEPSEEK_API_KEY в Railway Variables")
    else:
        logger.info("✅ Бармен готов к работе!")
    
    try:
        logger.info("🚀 Открываю бар...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бара: {e}")
    finally:
        await panda_api.close()
        logger.info("🛑 Бар закрыт")

if __name__ == "__main__":
    asyncio.run(main())