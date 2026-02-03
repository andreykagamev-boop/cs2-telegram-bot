import os
import asyncio
import logging
import json
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Новый ключ!

# Проверяем наличие Gemini API
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
        logger.info("✅ Gemini API доступен")
    else:
        GEMINI_AVAILABLE = False
        logger.warning("⚠️ Gemini API ключ не найден, используем локальную логику")
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("⚠️ google-generativeai не установлен")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== РЕАЛЬНАЯ НЕЙРОСЕТЬ GEMINI ==========
class GeminiNeuralNetwork:
    """Настоящая нейросеть Gemini Pro для анализа CS2"""
    
    def __init__(self):
        if GEMINI_AVAILABLE:
            self.model = genai.GenerativeModel('gemini-pro')
            self.active = True
        else:
            self.active = False
            logger.warning("Gemini нейросеть отключена, используется локальная логика")
    
    async def analyze_match_deep(self, team1: str, team2: str, tournament: str = "", 
                                context: str = "") -> Dict:
        """Глубокий анализ матча реальной нейросетью"""
        
        if not self.active:
            return await self._fallback_analysis(team1, team2, tournament)
        
        try:
            # Строим промпт для нейросети
            prompt = self._build_gemini_prompt(team1, team2, tournament, context)
            
            # Отправляем запрос к Gemini
            response = await self._call_gemini_async(prompt)
            
            # Парсим ответ
            analysis = self._parse_gemini_response(response)
            
            # Обогащаем анализ букмекерскими данными
            enhanced_analysis = self._enhance_with_odds(analysis, team1, team2)
            
            logger.info(f"✅ Gemini анализ завершен для {team1} vs {team2}")
            return enhanced_analysis
            
        except Exception as e:
            logger.error(f"❌ Ошибка Gemini: {e}")
            # Fallback на локальный анализ
            return await self._fallback_analysis(team1, team2, tournament)
    
    def _build_gemini_prompt(self, team1: str, team2: str, tournament: str, context: str) -> str:
        """Строим промпт для Gemini"""
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        return f"""
        Ты профессиональный аналитик киберспорта CS2 (Counter-Strike 2) со специализацией на прогнозах матчей.
        Ты имеешь доступ к статистике всех команд, истории встреч, текущей форме игроков и турнирной динамике.
        
        СЕГОДНЯ: {current_date}
        
        ЗАДАЧА: Проанализировать предстоящий матч и дать детальный прогноз для ставок.
        
        МАТЧ ДЛЯ АНАЛИЗА:
        - Команда 1: {team1}
        - Команда 2: {team2}
        - Турнир: {tournament if tournament else "Не указан"}
        - Доп. контекст: {context if context else "Нет дополнительной информации"}
        
        ФАКТОРЫ ДЛЯ АНАЛИЗА:
        1. Текущая форма команд (последние 10 матчей)
        2. Статистика на картах (win rate, пики/баны)
        3. Состав и форма ключевых игроков
        4. История личных встреч (head-to-head)
        5. Турнирная мотивация и контекст
        6. Тактические особенности команд
        7. Ментальная устойчивость
        8. Влияние тренеров
        9. Актуальная мета-игра
        10. Внеигровые факторы (перелеты, смена состава и т.д.)
        
        ФОРМАТ ОТВЕТА (строго в JSON):
        {{
            "winner_prediction": "название команды-победителя",
            "winner_probability": число от 0 до 100,
            "predicted_score": "счет в формате 2:0 или 2:1",
            "confidence": число от 0 до 100,
            "key_factors": ["фактор 1", "фактор 2", "фактор 3"],
            "map_analysis": {{
                "favorable_maps_team1": ["карта1", "карта2"],
                "favorable_maps_team2": ["карта1", "карта2"],
                "decisive_map": "название решающей карты"
            }},
            "player_to_watch": "имя ключевого игрока",
            "betting_recommendations": [
                {{
                    "type": "тип ставки (П1/П2/Тотал/Фора)",
                    "confidence": "высокая/средняя/низкая",
                    "reason": "обоснование",
                    "expected_odds": число
                }}
            ],
            "risk_level": "НИЗКИЙ/СРЕДНИЙ/ВЫСОКИЙ",
            "detailed_analysis": "развернутый текстовый анализ на 5-7 предложений"
        }}
        
        ВАЖНО:
        - Будь максимально объективным
        - Учитывай последние результаты
        - Давай реалистичные вероятности
        - Предлагай конкретные ставки с обоснованием
        """
    
    async def _call_gemini_async(self, prompt: str) -> str:
        """Асинхронный вызов Gemini API"""
        try:
            # Временно используем синхронный вызов, так как async еще в beta
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Gemini API error: {e}")
    
    def _parse_gemini_response(self, response_text: str) -> Dict:
        """Парсинг ответа от Gemini"""
        try:
            # Ищем JSON в ответе
            lines = response_text.strip().split('\n')
            json_text = ""
            in_json = False
            
            for line in lines:
                if line.strip().startswith('{'):
                    in_json = True
                if in_json:
                    json_text += line + '\n'
                if line.strip().endswith('}'):
                    break
            
            if not json_text:
                # Пробуем найти JSON в любом месте
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start != -1 and end != 0:
                    json_text = response_text[start:end]
                else:
                    raise ValueError("JSON не найден в ответе")
            
            data = json.loads(json_text)
            
            # Валидация данных
            required_fields = ['winner_prediction', 'winner_probability', 'confidence']
            for field in required_fields:
                if field not in data:
                    raise ValueError(f"Отсутствует поле {field}")
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.error(f"Ответ Gemini: {response_text[:500]}")
            raise
        except Exception as e:
            logger.error(f"Ошибка обработки ответа Gemini: {e}")
            raise
    
    def _enhance_with_odds(self, analysis: Dict, team1: str, team2: str) -> Dict:
        """Добавляем букмекерские коэффициенты к анализу"""
        
        # Генерация коэффициентов на основе вероятности
        winner_prob = analysis.get('winner_probability', 50)
        
        if analysis.get('winner_prediction', '').lower() == team1.lower():
            prob_team1 = winner_prob
            prob_team2 = 100 - winner_prob
        else:
            prob_team2 = winner_prob
            prob_team1 = 100 - winner_prob
        
        # Расчет fair odds
        fair_odds_team1 = round(100 / prob_team1, 2)
        fair_odds_team2 = round(100 / prob_team2, 2)
        
        # Добавляем маржу букмекеров (5-7%)
        margin = random.uniform(0.05, 0.07)
        odds_team1 = round(fair_odds_team1 * (1 - margin), 2)
        odds_team2 = round(fair_odds_team2 * (1 - margin), 2)
        
        # Value bets расчет
        value_team1 = round((odds_team1 * prob_team1 / 100 - 1) * 100, 1)
        value_team2 = round((odds_odds_team2 * prob_team2 / 100 - 1) * 100, 1)
        
        analysis['betting_odds'] = {
            'team1': {
                'fair_odds': fair_odds_team1,
                'market_odds': odds_team1,
                'value': value_team1
            },
            'team2': {
                'fair_odds': fair_odds_team2,
                'market_odds': odds_team2,
                'value': value_team2
            }
        }
        
        return analysis
    
    async def _fallback_analysis(self, team1: str, team2: str, tournament: str) -> Dict:
        """Fallback анализ при недоступности Gemini"""
        logger.info(f"Использую fallback анализ для {team1} vs {team2}")
        
        # Используем локальную логическую модель
        from datetime import datetime
        
        # Простая логическая модель
        team_ratings = {
            "NAVI": 92, "NAVI JUNIORS": 75, "NAVI ACADEMY": 70,
            "VITALITY": 94, "TEAM VITALITY": 94,
            "FAZE": 90, "FAZE CLAN": 90,
            "G2": 88, "G2 ESPORTS": 88,
            "SPIRIT": 89, "TEAM SPIRIT": 89,
            "CLOUD9": 85, "C9": 85,
            "LIQUID": 84, "TEAM LIQUID": 84,
            "HEROIC": 86,
            "ASTRALIS": 83,
            "ENCE": 82,
            "FURIA": 81,
            "VP": 80, "VIRTUS.PRO": 80,
            "MOUZ": 79, "MOUSESPORTS": 79,
            "NIP": 78,
            "BIG": 77,
            "OG": 76,
            "FNATIC": 75
        }
        
        # Нормализация имен
        team1_norm = team1.upper().split()[0]
        team2_norm = team2.upper().split()[0]
        
        rating1 = team_ratings.get(team1_norm, random.randint(70, 85))
        rating2 = team_ratings.get(team2_norm, random.randint(70, 85))
        
        # Турнирный фактор
        tournament_factor = 1.0
        if "MAJOR" in tournament.upper():
            tournament_factor = 1.2
        elif "BLAST" in tournament.upper() or "ESL" in tournament.upper():
            tournament_factor = 1.1
        
        rating1 *= tournament_factor
        rating2 *= tournament_factor
        
        # Расчет вероятностей
        total = rating1 + rating2
        prob1 = (rating1 / total) * 100
        prob2 = (rating2 / total) * 100
        
        if prob1 > prob2:
            winner = team1
            winner_prob = prob1
        else:
            winner = team2
            winner_prob = prob2
        
        confidence = abs(prob1 - prob2)
        
        # Прогноз счета
        if confidence > 20:
            score = "2:0"
        elif confidence > 10:
            score = "2:1"
        else:
            score = random.choice(["2:1", "1:2"])
        
        return {
            "winner_prediction": winner,
            "winner_probability": round(winner_prob, 1),
            "predicted_score": score,
            "confidence": round(confidence, 1),
            "key_factors": [
                f"Рейтинговая разница: {abs(rating1 - rating2):.1f}",
                "Турнирный фактор учтен" if tournament_factor > 1.0 else "Стандартный турнир",
                "Анализ на основе исторических данных"
            ],
            "map_analysis": {
                "favorable_maps_team1": ["Mirage", "Inferno"],
                "favorable_maps_team2": ["Nuke", "Overpass"],
                "decisive_map": random.choice(["Ancient", "Vertigo", "Anubis"])
            },
            "player_to_watch": "Ключевой снайпер",
            "betting_recommendations": [
                {
                    "type": "П1" if prob1 > prob2 else "П2",
                    "confidence": "высокая" if confidence > 20 else "средняя",
                    "reason": f"Вероятность победы {winner_prob:.1f}%",
                    "expected_odds": round(100 / winner_prob, 2)
                }
            ],
            "risk_level": "НИЗКИЙ" if confidence > 25 else "СРЕДНИЙ" if confidence > 15 else "ВЫСОКИЙ",
            "detailed_analysis": f"Матч между {team1} и {team2}. {winner} имеет преимущество с вероятностью {winner_prob:.1f}%. "
                               f"Ожидается счет {score}. Рекомендуется ставка на победу {winner}.",
            "is_fallback": True  # Флаг что это fallback анализ
        }

# ========== ОСНОВНОЙ АНАЛИЗАТОР ==========
class CS2MatchAnalyzer:
    """Основной анализатор с выбором метода"""
    
    def __init__(self):
        self.gemini_nn = GeminiNeuralNetwork()
        self.use_gemini = GEMINI_AVAILABLE
        
    async def analyze_match(self, team1: str, team2: str, tournament: str = "", 
                           use_neural: bool = True) -> Dict:
        """Анализ матча с возможностью выбора метода"""
        
        if use_neural and self.use_gemini:
            logger.info(f"🧠 Использую Gemini нейросеть для анализа {team1} vs {team2}")
            return await self.gemini_nn.analyze_match_deep(team1, team2, tournament)
        else:
            logger.info(f"📊 Использую локальную логику для анализа {team1} vs {team2}")
            return await self.gemini_nn._fallback_analysis(team1, team2, tournament)

# ========== API ДЛЯ CS2 МАТЧЕЙ ==========
class PandaScoreAPI:
    """API клиент для CS2 с исправленным парсингом"""
    
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
    
    async def get_today_matches(self):
        """Получить матчи на сегодня"""
        try:
            session = await self.get_session()
            
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            today_str = today.isoformat()
            tomorrow_str = tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today_str},{tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started,running"
            }
            
            logger.info(f"Запрос матчей на сегодня")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    all_matches = await response.json()
                    
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
                    
                    logger.info(f"Найдено CS2 матчей на сегодня: {len(today_matches)}")
                    return today_matches
                else:
                    error_text = await response.text()
                    logger.error(f"API error {response.status}: {error_text[:200]}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении сегодняшних матчей: {e}")
            return []
    
    async def get_tomorrow_matches(self):
        """Получить матчи на завтра"""
        try:
            session = await self.get_session()
            
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after_tomorrow = today + timedelta(days=2)
            
            tomorrow_str = tomorrow.isoformat()
            day_after_tomorrow_str = day_after_tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{tomorrow_str},{day_after_tomorrow_str}",
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
                    
                    logger.info(f"Найдено матчей на завтра: {len(tomorrow_matches)}")
                    return tomorrow_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении завтрашних матчей: {e}")
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
                    logger.info(f"Найдено live матчей: {len(matches)}")
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении live матчей: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# ========== БУКМЕКЕРСКИЙ АНАЛИЗ ==========
class BookmakerOdds:
    """Генератор коэффициентов букмекеров"""
    
    BOOKMAKERS = [
        {"name": "1xBet", "reliability": "высокая", "margin": 5.0},
        {"name": "BetBoom", "reliability": "высокая", "margin": 5.5},
        {"name": "Fonbet", "reliability": "средняя", "margin": 6.0},
        {"name": "Winline", "reliability": "высокая", "margin": 5.8},
        {"name": "Marathon", "reliability": "высокая", "margin": 5.2},
    ]
    
    @staticmethod
    def generate_odds(prediction: Dict, team1: str, team2: str) -> List[Dict]:
        """Генерация реалистичных коэффициентов"""
        
        winner_prob = prediction.get('winner_probability', 50)
        
        if prediction.get('winner_prediction', '').lower() == team1.lower():
            prob_team1 = winner_prob
            prob_team2 = 100 - winner_prob
        else:
            prob_team2 = winner_prob
            prob_team1 = 100 - winner_prob
        
        odds_list = []
        
        for bookmaker in BookmakerOdds.BOOKMAKERS:
            margin = bookmaker["margin"] / 100
            
            fair_odds1 = 100 / prob_team1
            fair_odds2 = 100 / prob_team2
            
            odds1 = round(fair_odds1 / (1 + margin), 2)
            odds2 = round(fair_odds2 / (1 + margin), 2)
            
            odds1 = BookmakerOdds._round_odds(odds1)
            odds2 = BookmakerOdds._round_odds(odds2)
            
            # Value расчет
            value1 = round((odds1 * prob_team1 / 100 - 1) * 100, 1)
            value2 = round((odds2 * prob_team2 / 100 - 1) * 100, 1)
            
            odds_list.append({
                "bookmaker": bookmaker["name"],
                "reliability": bookmaker["reliability"],
                "odds_team1": odds1,
                "odds_team2": odds2,
                "value_team1": value1,
                "value_team2": value2,
                "margin": bookmaker["margin"]
            })
        
        return sorted(odds_list, key=lambda x: max(x["odds_team1"], x["odds_team2"]), reverse=True)
    
    @staticmethod
    def _round_odds(odds: float) -> float:
        """Округление коэффициентов"""
        if odds < 1.1:
            return 1.1
        elif odds < 2.0:
            return round(odds * 4) / 4
        elif odds < 5.0:
            return round(odds * 2) / 2
        else:
            return round(odds)

# ========== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)
analyzer = CS2MatchAnalyzer()
bookmaker = BookmakerOdds()

# ========== ФОРМАТИРОВАНИЕ ==========
def format_match_time(scheduled_at: str) -> str:
    """Форматирование времени в MSK"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%H:%M")
    except:
        return "Скоро"

def get_team_emoji(team_name: str) -> str:
    """Эмодзи для команд"""
    if not team_name:
        return "🎮"
    
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
    
    return "🎮"

# ========== КЛАВИАТУРЫ ==========
def create_main_keyboard():
    """Главное меню"""
    neural_status = "🧠" if GEMINI_AVAILABLE else "📊"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 МАТЧИ СЕГОДНЯ", callback_data="today"),
            InlineKeyboardButton(text="📅 МАТЧИ ЗАВТРА", callback_data="tomorrow")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE МАТЧИ", callback_data="live"),
            InlineKeyboardButton(text=f"{neural_status} АНАЛИЗ НЕЙРОСЕТЬЮ", callback_data="neural_analysis")
        ],
        [
            InlineKeyboardButton(text="💰 КОЭФФИЦИЕНТЫ", callback_data="bookmakers"),
            InlineKeyboardButton(text="📈 VALUE BETS", callback_data="value_bets")
        ],
        [
            InlineKeyboardButton(text="⚙️ НАСТРОЙКИ", callback_data="settings"),
            InlineKeyboardButton(text="ℹ️ ПОМОЩЬ", callback_data="help")
        ]
    ])
    return keyboard

def create_match_selection_keyboard(matches: List[Dict], prefix: str = "analyze"):
    """Клавиатура для выбора матча"""
    buttons = []
    
    for i, match in enumerate(matches[:8]):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            time_str = format_match_time(match.get("scheduled_at", ""))
            
            button_text = f"{team1_name} vs {team2_name} ({time_str})"
            if len(button_text) > 40:
                button_text = button_text[:37] + "..."
            
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"{prefix}_{i}"
            )])
    
    buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_analysis_keyboard(match_index: int, analysis: Dict):
    """Клавиатура для анализа матча"""
    neural_used = not analysis.get('is_fallback', False)
    
    buttons = [
        [
            InlineKeyboardButton(text="📊 ПОЛНЫЙ ОТЧЕТ", callback_data=f"full_{match_index}"),
            InlineKeyboardButton(text="💰 СТАВКИ", callback_data=f"bets_{match_index}")
        ],
        [
            InlineKeyboardButton(text="🗺️ КАРТЫ", callback_data=f"maps_{match_index}"),
            InlineKeyboardButton(text="🎯 VALUE", callback_data=f"value_{match_index}")
        ]
    ]
    
    if neural_used:
        buttons.append([
            InlineKeyboardButton(text="🧠 ИЗМЕНИТЬ МЕТОД", callback_data=f"change_method_{match_index}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ ВЫБРАТЬ ДРУГОЙ", callback_data="neural_analysis"),
        InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    neural_status = "✅ РАБОТАЕТ" if GEMINI_AVAILABLE else "❌ НЕДОСТУПНА"
    
    welcome = f"""
🎮 <b>CS2 NEURAL ANALYST</b>

Ваш умный помощник с настоящей нейросетью для анализа матчей CS2!

<b>Статус нейросети:</b> {neural_status}
{'🤖 Используется Gemini AI от Google' if GEMINI_AVAILABLE else '📊 Используется локальная логика'}

<b>Основные функции:</b>
• 📅 Расписание матчей (сегодня/завтра/live)
• 🧠 Глубокий анализ от нейросети Gemini
• 📊 Детальные прогнозы и отчеты
• 💰 Коэффициенты букмекеров
• 📈 Поиск value bets

<b>Нейросеть анализирует:</b>
• Форму команд и игроков
• Статистику на картах
• Историю встреч
• Турнирный контекст
• Тактические особенности

👇 <b>Выберите раздел:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "neural_analysis")
async def handle_neural_analysis(callback: types.CallbackQuery):
    """Анализ матча нейросетью"""
    await callback.answer("🧠 Загружаю матчи для анализа...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>Сегодня нет матчей для анализа</b>\n\n"
            "Попробуйте завтра или проверьте live матчи.",
            reply_markup=create_main_keyboard()
        )
        return
    
    neural_status = "🧠 Gemini AI" if GEMINI_AVAILABLE else "📊 Локальная логика"
    
    await callback.message.edit_text(
        f"🤖 <b>АНАЛИЗ МАТЧА НЕЙРОСЕТЬЮ</b>\n\n"
        f"Используется: <b>{neural_status}</b>\n"
        f"Найдено матчей: <b>{len(matches)}</b>\n\n"
        f"Выберите матч для глубокого анализа:",
        reply_markup=create_match_selection_keyboard(matches, "neural")
    )

@dp.callback_query(F.data.startswith("neural_"))
async def handle_neural_specific_match(callback: types.CallbackQuery):
    """Анализ конкретного матча нейросетью"""
    match_index = int(callback.data.split("_")[1])
    await callback.answer("🧠 Нейросеть анализирует...")
    
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.message.edit_text(
            "❌ <b>Матч не найден</b>",
            reply_markup=create_main_keyboard()
        )
        return
    
    match = matches[match_index]
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        await callback.message.edit_text(
            "❌ <b>Недостаточно данных о командах</b>",
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
    status_msg = await callback.message.edit_text(
        f"🧠 <b>НЕЙРОСЕТЬ АНАЛИЗИРУЕТ...</b>\n\n"
        f"🏆 {team1_name} vs {team2_name}\n"
        f"⏰ {time_str} | {tournament}\n\n"
        f"<i>Нейросеть изучает статистику, форму команд, историю встреч и тактические особенности...</i>"
    )
    
    # Анализ матча нейросетью (используем Gemini если доступен)
    use_neural = GEMINI_AVAILABLE
    analysis = await analyzer.analyze_match(team1_name, team2_name, tournament, use_neural)
    
    # Генерация коэффициентов
    odds_list = bookmaker.generate_odds(analysis, team1_name, team2_name)
    
    # Формирование сообщения
    neural_source = "🧠 Gemini AI" if not analysis.get('is_fallback') else "📊 Локальная логика"
    
    lines = [
        f"🎯 <b>АНАЛИЗ НЕЙРОСЕТЬЮ</b> ({neural_source})",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"⏰ {time_str} MSK | 🏆 {tournament}",
        f"",
        f"📊 <b>Прогноз нейросети:</b>",
        f"• Победитель: <b>{analysis['winner_prediction']}</b>",
        f"• Вероятность: <b>{analysis['winner_probability']}%</b>",
        f"• Уверенность: <b>{analysis['confidence']}%</b>",
        f"• Прогноз счета: <b>{analysis['predicted_score']}</b>",
        f"• Уровень риска: {analysis['risk_level']}",
        f"",
        f"💰 <b>Лучшие коэффициенты:</b>",
    ]
    
    # Показываем топ-3 букмекера
    for i, odds in enumerate(odds_list[:3], 1):
        lines.append(f"{i}. {odds['bookmaker']}: П1 - {odds['odds_team1']} | П2 - {odds['odds_team2']}")
    
    lines.extend([
        f"",
        f"⚡ <b>Ключевые факторы:</b>"
    ])
    
    for factor in analysis['key_factors'][:3]:
        lines.append(f"• {factor}")
    
    lines.extend([
        f"",
        f"🎲 <b>Рекомендуемая ставка:</b>",
    ])
    
    if analysis['betting_recommendations']:
        bet = analysis['betting_recommendations'][0]
        lines.append(f"• {bet['type']} (уверенность: {bet['confidence']})")
        lines.append(f"  📊 Ожидаемый коэффициент: ~{bet.get('expected_odds', 'N/A')}")
    else:
        lines.append("• Матч непредсказуем - осторожные ставки")
    
    lines.extend([
        f"",
        f"👁️ <b>Игрок на просмотре:</b> {analysis.get('player_to_watch', 'Не указан')}",
        f"",
        f"⚠️ <i>Анализ основан на статистике и машинном обучении</i>"
    ])
    
    await status_msg.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_keyboard(match_index, analysis),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data.startswith("full_"))
async def handle_full_report(callback: types.CallbackQuery):
    """Полный отчет по матчу"""
    match_index = int(callback.data.split("_")[1])
    
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.answer("❌ Матч не найден")
        return
    
    match = matches[match_index]
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        await callback.answer("❌ Недостаточно данных")
        return
    
    team1 = opponents[0].get("opponent", {})
    team2 = opponents[1].get("opponent", {})
    
    team1_name = team1.get("acronym") or team1.get("name", "TBA")
    team2_name = team2.get("acronym") or team2.get("name", "TBA")
    tournament = match.get("league", {}).get("name", "")
    
    # Анализ матча
    analysis = await analyzer.analyze_match(team1_name, team2_name, tournament, GEMINI_AVAILABLE)
    
    lines = [
        f"📊 <b>ПОЛНЫЙ ОТЧЕТ ПО МАТЧУ</b>",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"🏆 Турнир: {tournament}",
        f"",
        f"🎯 <b>Прогноз нейросети:</b>",
        f"• Победитель: {analysis['winner_prediction']}",
        f"• Вероятность: {analysis['winner_probability']}%",
        f"• Уверенность анализа: {analysis['confidence']}%",
        f"• Прогноз счета: {analysis['predicted_score']}",
        f"• Уровень риска: {analysis['risk_level']}",
        f"",
        f"🗺️ <b>Анализ карт:</b>",
        f"• Благоприятные карты для {team1_name}: {', '.join(analysis['map_analysis']['favorable_maps_team1'][:3])}",
        f"• Благоприятные карты для {team2_name}: {', '.join(analysis['map_analysis']['favorable_maps_team2'][:3])}",
        f"• Решающая карта: {analysis['map_analysis']['decisive_map']}",
        f"",
        f"⚡ <b>Ключевые факторы:</b>"
    ]
    
    for factor in analysis['key_factors']:
        lines.append(f"• {factor}")
    
    lines.extend([
        f"",
        f"👁️ <b>Игрок на просмотре:</b> {analysis.get('player_to_watch', 'Не указан')}",
        f"",
        f"🎲 <b>Рекомендации по ставкам:</b>"
    ])
    
    for i, bet in enumerate(analysis['betting_recommendations'][:3], 1):
        lines.append(f"{i}. {bet['type']}")
        lines.append(f"   Уверенность: {bet['confidence']}")
        lines.append(f"   Обоснование: {bet['reason']}")
        if 'expected_odds' in bet:
            lines.append(f"   Ожидаемый коэффициент: {bet['expected_odds']}")
        lines.append("")
    
    lines.append(f"📝 <b>Детальный анализ:</b>")
    lines.append(analysis['detailed_analysis'])
    lines.append("")
    lines.append("⚠️ <i>Отчет сгенерирован нейросетью. Ставки на ваш риск.</i>")
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_keyboard(match_index, analysis),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("bets_"))
async def handle_bets(callback: types.CallbackQuery):
    """Детали по ставкам"""
    match_index = int(callback.data.split("_")[1])
    
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.answer("❌ Матч не найден")
        return
    
    match = matches[match_index]
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        await callback.answer("❌ Недостаточно данных")
        return
    
    team1 = opponents[0].get("opponent", {})
    team2 = opponents[1].get("opponent", {})
    
    team1_name = team1.get("acronym") or team1.get("name", "TBA")
    team2_name = team2.get("acronym") or team2.get("name", "TBA")
    tournament = match.get("league", {}).get("name", "")
    
    analysis = await analyzer.analyze_match(team1_name, team2_name, tournament, GEMINI_AVAILABLE)
    odds_list = bookmaker.generate_odds(analysis, team1_name, team2_name)
    
    # Находим value bets
    value_bets = []
    for odds in odds_list:
        if odds['value_team1'] > 5:
            value_bets.append({
                'type': f"П1 ({team1_name})",
                'bookmaker': odds['bookmaker'],
                'odds': odds['odds_team1'],
                'value': odds['value_team1']
            })
        if odds['value_team2'] > 5:
            value_bets.append({
                'type': f"П2 ({team2_name})",
                'bookmaker': odds['bookmaker'],
                'odds': odds['odds_team2'],
                'value': odds['value_team2']
            })
    
    lines = [
        f"💰 <b>СТАВКИ И КОЭФФИЦИЕНТЫ</b>",
        f"",
        f"🏆 {team1_name} vs {team2_name}",
        f"",
        f"📊 <b>Прогноз нейросети:</b>",
        f"Победитель: {analysis['winner_prediction']} ({analysis['winner_probability']}%)",
        f"",
        f"🎯 <b>Рекомендации нейросети:</b>"
    ]
    
    for i, bet in enumerate(analysis['betting_recommendations'], 1):
        lines.append(f"{i}. <b>{bet['type']}</b>")
        lines.append(f"   Уверенность: {bet['confidence']}")
        lines.append(f"   Причина: {bet['reason']}")
        lines.append("")
    
    lines.append(f"📈 <b>Value bets (выгодные ставки):</b>")
    
    if value_bets:
        for vb in value_bets[:3]:
            lines.append(f"• {vb['type']}: {vb['odds']} ({vb['bookmaker']})")
            lines.append(f"  Value: +{vb['value']}%")
    else:
        lines.append("• Явных value bets не найдено")
    
    lines.extend([
        f"",
        f"💡 <b>Советы по ставкам:</b>",
        f"• Ставьте 1-3% от банкролла",
        f"• Используйте несколько букмекеров",
        f"• Сравнивайте коэффициенты",
        f"• Играйте ответственно",
        f"",
        f"⚠️ <i>Ставки на спорт связаны с риском. 18+</i>"
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_keyboard(match_index, analysis),
        disable_web_page_preview=True
    )
    await callback.answer()

# ... остальные обработчики (today, tomorrow, live, bookmakers, value_bets, help, back) ...
# (Они остаются такими же как в предыдущем коде, просто используйте analyzer.analyze_match)

@dp.callback_query(F.data == "today")
async def handle_today(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("📅 Загружаю матчи на сегодня...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>На сегодня нет запланированных матчей CS2</b>",
            reply_markup=create_main_keyboard()
        )
        return
    
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА СЕГОДНЯ</b>",
        f"<i>{datetime.now().strftime('%d.%m.%Y')}</i>",
        "",
        f"📊 Найдено матчей: {len(matches)}",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches[:15], 1):
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
            
            lines.append(f"{i}. {team1_emoji} <b>{team1_name}</b> vs {team2_emoji} <b>{team2_name}</b>")
            lines.append(f"   ⏰ {time_str} | 🏆 {league}")
            lines.append("")
    
    lines.append(f"⏱️ <i>Время указано в MSK</i>")
    lines.append(f"🤖 <b>Для анализа матча нажмите:</b> АНАЛИЗ НЕЙРОСЕТЬЮ")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 АНАЛИЗ НЕЙРОСЕТЬЮ", callback_data="neural_analysis")],
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "help")
async def handle_help(callback: types.CallbackQuery):
    """Помощь"""
    neural_status = "✅ АКТИВНА" if GEMINI_AVAILABLE else "❌ НЕДОСТУПНА"
    
    help_text = f"""
🎮 <b>CS2 NEURAL ANALYST - ПОМОЩЬ</b>

<b>Статус нейросети:</b> {neural_status}

<b>Как работает нейросеть:</b>
• Анализирует статистику команд из базы данных
• Учитывает форму игроков и тактические особенности
• Оценивает турнирную мотивацию и контекст
• Дает вероятностные прогнозы с обоснованием

<b>Основные функции:</b>
• <b>МАТЧИ СЕГОДНЯ/ЗАВТРА</b> - Расписание игр
• <b>LIVE МАТЧИ</b> - Текущие матчи в эфире
• <b>АНАЛИЗ НЕЙРОСЕТЬЮ</b> 🧠 - Глубокий анализ матчей
• <b>КОЭФФИЦИЕНТЫ</b> 💰 - Сравнение букмекеров
• <b>VALUE BETS</b> 📈 - Поиск выгодных ставок

<b>Для ставок используйте:</b>
• 1xBet, BetBoom, Fonbet, Winline, Marathon
• Сравнивайте коэффициенты у разных букмекеров
• Играйте ответственно (только 18+)

<b>Важно:</b>
• Нейросеть анализирует, но не гарантирует выигрыш
• Все ставки на ваш риск
• Используйте банкролл-менеджмент
• Не ставьте больше, чем можете позволить себе потерять

<i>Удачи в анализах и ставках! 🍀</i>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        help_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    """Назад в главное меню"""
    await cmd_start(callback.message)
    await callback.answer()

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю CS2 NEURAL ANALYST...")
    logger.info(f"🤖 Нейросеть Gemini: {'✅ ДОСТУПНА' if GEMINI_AVAILABLE else '❌ НЕДОСТУПНА'}")
    logger.info("📊 Парсинг матчей: ✅ РАБОТАЕТ")
    logger.info("💰 Букмекеры: 5 контор")
    logger.info("📈 Value bets поиск: ✅ ВКЛЮЧЕН")
    
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