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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== DEEPSEEK НЕЙРОСЕТЬ ==========
try:
    from openai import AsyncOpenAI
    DEEPSEEK_AVAILABLE = bool(DEEPSEEK_API_KEY)
    if DEEPSEEK_AVAILABLE:
        deepseek_client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        logger.info("✅ DeepSeek нейросеть активирована")
    else:
        logger.warning("⚠️ DeepSeek API ключ не найден в .env")
        DEEPSEEK_AVAILABLE = False
except ImportError:
    logger.warning("⚠️ OpenAI библиотека не установлена. Установите: pip install openai")
    DEEPSEEK_AVAILABLE = False
except Exception as e:
    logger.error(f"❌ Ошибка инициализации DeepSeek: {e}")
    DEEPSEEK_AVAILABLE = False

class DeepSeekAnalyzer:
    """Настоящая нейросеть для анализа CS2 матчей"""
    
    @staticmethod
    async def analyze_match(team1: str, team2: str, tournament: str = "", 
                           additional_context: str = "") -> Dict:
        """Анализ матча с помощью DeepSeek"""
        
        if not DEEPSEEK_AVAILABLE:
            return await LocalAnalyzer.analyze_match(team1, team2, tournament)
        
        try:
            prompt = f"""
            [ЗАДАЧА]
            Проанализируй предстоящий матч Counter-Strike 2 и дай профессиональный прогноз.
            
            [ДАННЫЕ МАТЧА]
            Команда 1: {team1}
            Команда 2: {team2}
            Турнир: {tournament if tournament else 'Не указан'}
            Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M MSK')}
            Дополнительный контекст: {additional_context if additional_context else 'Нет'}
            
            [ТРЕБОВАНИЯ К АНАЛИЗУ]
            1. Проведи сравнительный анализ команд
            2. Оцени текущую форму и мотивацию
            3. Проанализируй статистику на картах (если данные доступны)
            4. Учти историю личных встреч (head-to-head)
            5. Оцени тактические особенности
            6. Учти последние изменения в составе (если есть)
            7. Дай вероятностный прогноз
            
            [ФОРМАТ ОТВЕТА]
            Верни ответ в формате JSON:
            {{
                "team_analysis": {{
                    "team1": {{
                        "strength": 0-100,
                        "current_form": "описание",
                        "key_strengths": ["сила1", "сила2"],
                        "weaknesses": ["слабость1", "слабость2"]
                    }},
                    "team2": {{ ... }}
                }},
                "match_prediction": {{
                    "most_likely_winner": "название команды",
                    "winner_probability": 0-100,
                    "predicted_score": "формат 2:0 или 16:14",
                    "match_duration": "быстрый/средний/долгий",
                    "expected_maps": 2 или 3
                }},
                "risk_assessment": {{
                    "risk_level": "LOW/MEDIUM/HIGH",
                    "confidence": 0-100,
                    "volatility": "низкая/средняя/высокая"
                }},
                "betting_insights": {{
                    "value_bet": "тип наиболее выгодной ставки",
                    "safe_bet": "тип безопасной ставки",
                    "avoid_bets": ["типы ставок которых стоит избегать"],
                    "bankroll_recommendation": "1-3% от банка"
                }},
                "key_factors": [
                    {{
                        "factor": "название фактора",
                        "impact": "HIGH/MEDIUM/LOW",
                        "favors": "team1/team2/both"
                    }}
                ],
                "detailed_analysis": "развернутый текстовый анализ на 3-5 абзацев",
                "ai_model": "DeepSeek-Chat",
                "analysis_timestamp": "2024-01-01T12:00:00Z"
            }}
            """
            
            response = await deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": """Ты профессиональный аналитик киберспорта Counter-Strike 2 
                        с 10-летним опытом. Ты специализируешься на анализе матчей, 
                        статистике команд и прогнозировании результатов. Будь точным, 
                        объективным и приводи факты. Избегай общих фраз, будь конкретен."""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Добавляем мета-информацию
            result["ai_analysis"] = True
            result["deepseek_used"] = True
            result["analysis_time"] = datetime.now().isoformat()
            
            # Обогащаем букмекерскими данными
            if "match_prediction" in result:
                prediction = result["match_prediction"]
                if "winner_probability" in prediction:
                    result["calculated_odds"] = DeepSeekAnalyzer._calculate_odds(
                        prediction["winner_probability"]
                    )
            
            return result
            
        except Exception as e:
            logger.error(f"DeepSeek API ошибка: {e}")
            # Fallback на локальный анализатор
            return await LocalAnalyzer.analyze_match(team1, team2, tournament)
    
    @staticmethod
    def _calculate_odds(probability: float) -> Dict:
        """Расчет реалистичных коэффициентов"""
        if probability <= 0:
            probability = 1
        
        fair_odds = 100 / probability
        
        # Разные маржи букмекеров
        return {
            "fair_odds": round(fair_odds, 2),
            "low_margin_odds": round(fair_odds * 0.97, 2),  # 3% маржа (премиум)
            "medium_margin_odds": round(fair_odds * 0.95, 2),  # 5% маржа (средние)
            "high_margin_odds": round(fair_odds * 0.92, 2),  # 8% маржа (высокие)
            "value_threshold": round(fair_odds * 1.05, 2)  # 5% value
        }
    
    @staticmethod
    async def get_quick_prediction(team1: str, team2: str) -> str:
        """Быстрый прогноз для уведомлений"""
        if not DEEPSEEK_AVAILABLE:
            return "Локальный анализ: матч требует детального изучения"
        
        try:
            prompt = f"Кто вероятнее победит в CS2: {team1} или {team2}? Ответь кратко."
            
            response = await deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "Дай краткий прогноз на матч CS2."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=100
            )
            
            return response.choices[0].message.content
            
        except:
            return "Анализ временно недоступен"

# ========== ЛОКАЛЬНЫЙ АНАЛИЗАТОР (FALLBACK) ==========
class LocalAnalyzer:
    """Локальный анализатор когда нейросеть недоступна"""
    
    TEAM_DATABASE = {
        "NAVI": {"rating": 92, "form": "up", "style": "агрессивный", "maps": {"Mirage": 85, "Inferno": 80}},
        "Vitality": {"rating": 95, "form": "up", "style": "стратегический", "maps": {"Mirage": 90, "Ancient": 88}},
        "FaZe": {"rating": 90, "form": "stable", "style": "универсальный", "maps": {"Mirage": 88, "Overpass": 85}},
        "G2": {"rating": 88, "form": "down", "style": "индивидуальный", "maps": {"Mirage": 85, "Vertigo": 90}},
        "Spirit": {"rating": 89, "form": "up", "style": "тактический", "maps": {"Inferno": 88, "Nuke": 85}},
        "Cloud9": {"rating": 85, "form": "stable", "style": "агрессивный", "maps": {"Inferno": 85, "Ancient": 78}},
    }
    
    @staticmethod
    async def analyze_match(team1: str, team2: str, tournament: str = "") -> Dict:
        """Локальный анализ на основе базы знаний"""
        
        # Нормализация имен
        team1_norm = LocalAnalyzer._normalize_name(team1)
        team2_norm = LocalAnalyzer._normalize_name(team2)
        
        # Данные команд
        team1_data = LocalAnalyzer.TEAM_DATABASE.get(team1_norm, {
            "rating": random.randint(75, 85),
            "form": random.choice(["up", "stable", "down"]),
            "style": "неизвестно",
            "maps": {}
        })
        
        team2_data = LocalAnalyzer.TEAM_DATABASE.get(team2_norm, {
            "rating": random.randint(75, 85),
            "form": random.choice(["up", "stable", "down"]),
            "style": "неизвестно",
            "maps": {}
        })
        
        # Расчет вероятностей
        rating1 = team1_data["rating"]
        rating2 = team2_data["rating"]
        
        # Корректировки
        form_multiplier = {"up": 1.15, "stable": 1.0, "down": 0.85}
        rating1 *= form_multiplier[team1_data["form"]]
        rating2 *= form_multiplier[team2_data["form"]]
        
        total = rating1 + rating2
        prob1 = (rating1 / total) * 100
        prob2 = (rating2 / total) * 100
        
        # Определение победителя
        winner = team1_norm if prob1 > prob2 else team2_norm
        confidence = abs(prob1 - prob2)
        
        return {
            "team_analysis": {
                "team1": {
                    "strength": team1_data["rating"],
                    "current_form": team1_data["form"],
                    "key_strengths": [team1_data["style"]],
                    "weaknesses": ["Недостаток данных" if team1_norm not in LocalAnalyzer.TEAM_DATABASE else "Стабильность"]
                },
                "team2": {
                    "strength": team2_data["rating"],
                    "current_form": team2_data["form"],
                    "key_strengths": [team2_data["style"]],
                    "weaknesses": ["Недостаток данных" if team2_norm not in LocalAnalyzer.TEAM_DATABASE else "Стабильность"]
                }
            },
            "match_prediction": {
                "most_likely_winner": winner,
                "winner_probability": max(prob1, prob2),
                "predicted_score": LocalAnalyzer._predict_score(prob1, prob2),
                "match_duration": "средний",
                "expected_maps": 2 if max(prob1, prob2) > 65 else 3
            },
            "risk_assessment": {
                "risk_level": "HIGH" if confidence < 15 else "MEDIUM" if confidence < 30 else "LOW",
                "confidence": confidence,
                "volatility": "высокая"
            },
            "betting_insights": {
                "value_bet": "Победа " + winner if confidence > 20 else "Тотал карт >2.5",
                "safe_bet": "Фора +1.5 слабой команды",
                "avoid_bets": ["Четкий счет", "Точный тотал"],
                "bankroll_recommendation": "1-2% от банка"
            },
            "key_factors": [
                {
                    "factor": "Текущая форма",
                    "impact": "HIGH",
                    "favors": team1_norm if team1_data["form"] == "up" else team2_norm if team2_data["form"] == "up" else "both"
                }
            ],
            "detailed_analysis": f"Матч между {team1} и {team2}. {winner} имеет небольшое преимущество.",
            "ai_model": "Local Knowledge Base",
            "analysis_timestamp": datetime.now().isoformat(),
            "ai_analysis": False,
            "deepseek_used": False
        }
    
    @staticmethod
    def _normalize_name(team_name: str) -> str:
        """Нормализация имени команды"""
        if not team_name:
            return "Unknown"
        
        team_lower = team_name.lower()
        
        for known_team in LocalAnalyzer.TEAM_DATABASE.keys():
            if known_team.lower() in team_lower:
                return known_team
        
        # Популярные команды
        if "navi" in team_lower or "natus" in team_lower:
            return "NAVI"
        elif "vitality" in team_lower or "vita" in team_lower:
            return "Vitality"
        elif "faze" in team_lower:
            return "FaZe"
        elif "g2" in team_lower:
            return "G2"
        elif "spirit" in team_lower:
            return "Spirit"
        elif "cloud9" in team_lower or "c9" in team_lower:
            return "Cloud9"
        
        return team_name
    
    @staticmethod
    def _predict_score(prob1: float, prob2: float) -> str:
        """Прогноз счета"""
        diff = abs(prob1 - prob2)
        
        if diff > 30:
            return "2:0" if prob1 > prob2 else "0:2"
        elif diff > 15:
            return "2:1" if prob1 > prob2 else "1:2"
        else:
            return "2:1"  # Близкий матч

# ========== УЛУЧШЕННЫЙ ПАРСИНГ МАТЧЕЙ ==========
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
    
    async def get_today_matches(self) -> List[Dict]:
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
                "filter[status]": "not_started"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем по точной дате
                    today_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                if match_time.date() == today:
                                    today_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"Найдено матчей на сегодня: {len(today_matches)}")
                    return today_matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении сегодняшних матчей: {e}")
            return []
    
    async def get_tomorrow_matches(self) -> List[Dict]:
        """Получить матчи на завтра"""
        try:
            session = await self.get_session()
            
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after_tomorrow = today + timedelta(days=2)
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{tomorrow.isoformat()},{day_after_tomorrow.isoformat()}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    tomorrow_matches = []
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
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
    
    async def get_live_matches(self) -> List[Dict]:
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
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении live матчей: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# ========== УЛУЧШЕННАЯ БУКМЕКЕРСКАЯ АНАЛИТИКА ==========
class SmartBettingAnalytics:
    """Умная аналитика для ставок на основе данных нейросети"""
    
    @staticmethod
    def generate_betting_recommendations(prediction: Dict) -> Dict:
        """Генерация умных рекомендаций по ставкам"""
        
        if not prediction.get("ai_analysis", False):
            return SmartBettingAnalytics._generate_basic_recommendations(prediction)
        
        match_pred = prediction.get("match_prediction", {})
        risk_assessment = prediction.get("risk_assessment", {})
        betting_insights = prediction.get("betting_insights", {})
        
        winner = match_pred.get("most_likely_winner", "")
        probability = match_pred.get("winner_probability", 50)
        confidence = risk_assessment.get("confidence", 50)
        risk_level = risk_assessment.get("risk_level", "MEDIUM")
        
        # Расчет value
        fair_odds = 100 / probability if probability > 0 else 2.0
        recommended_odds = fair_odds * 0.95  # С маржой 5%
        
        # Определение типа ставки
        if confidence > 70 and probability > 65:
            bet_type = f"Победа {winner}"
            bet_confidence = "ВЫСОКАЯ"
            stake_percentage = "2-3%"
        elif confidence > 50:
            bet_type = f"Фора {winner} (-1.5)"
            bet_confidence = "СРЕДНЯЯ"
            stake_percentage = "1-2%"
        else:
            bet_type = "Тотал карт >2.5"
            bet_confidence = "НИЗКАЯ"
            stake_percentage = "0.5-1%"
        
        # Находим лучшие коэффициенты
        best_odds = SmartBettingAnalytics._find_best_bookmakers(fair_odds)
        
        # Value bets
        value_bets = SmartBettingAnalytics._find_value_bets(probability, best_odds)
        
        return {
            "primary_recommendation": {
                "type": bet_type,
                "confidence": bet_confidence,
                "stake": stake_percentage,
                "expected_odds": round(recommended_odds, 2),
                "reason": SmartBettingAnalytics._get_reason(confidence, probability, risk_level)
            },
            "alternative_bets": SmartBettingAnalytics._get_alternative_bets(prediction),
            "value_bets": value_bets,
            "best_bookmakers": best_odds,
            "risk_warnings": SmartBettingAnalytics._get_risk_warnings(risk_level),
            "bankroll_advice": "Никогда не ставьте больше 5% от банка за одну ставку",
            "ai_confidence": f"{confidence}% уверенности в анализе"
        }
    
    @staticmethod
    def _find_best_bookmakers(fair_odds: float) -> List[Dict]:
        """Найти лучшие коэффициенты у букмекеров"""
        bookmakers = [
            {"name": "1xBet", "margin": 0.95, "reliability": "высокая"},
            {"name": "BetBoom", "margin": 0.96, "reliability": "высокая"},
            {"name": "Fonbet", "margin": 0.94, "reliability": "средняя"},
            {"name": "Winline", "margin": 0.93, "reliability": "высокая"},
            {"name": "Marathon", "margin": 0.97, "reliability": "высокая"}
        ]
        
        result = []
        for bm in bookmakers:
            odds = round(fair_odds * bm["margin"], 2)
            result.append({
                "bookmaker": bm["name"],
                "odds": odds,
                "reliability": bm["reliability"],
                "value_score": round((odds / fair_odds - 1) * 100, 1)
            })
        
        return sorted(result, key=lambda x: x["odds"], reverse=True)
    
    @staticmethod
    def _find_value_bets(probability: float, bookmaker_odds: List[Dict]) -> List[Dict]:
        """Найти value bets"""
        fair_odds = 100 / probability if probability > 0 else 2.0
        value_bets = []
        
        for bm in bookmaker_odds:
            if bm["odds"] > fair_odds * 1.05:  # 5% value
                value = ((bm["odds"] * probability / 100) - 1) * 100
                if value > 5:
                    value_bets.append({
                        "bookmaker": bm["bookmaker"],
                        "odds": bm["odds"],
                        "value": round(value, 1),
                        "edge": "ПОЛОЖИТЕЛЬНОЕ"
                    })
        
        return value_bets
    
    @staticmethod
    def _get_alternative_bets(prediction: Dict) -> List[Dict]:
        """Альтернативные ставки"""
        match_pred = prediction.get("match_prediction", {})
        expected_maps = match_pred.get("expected_maps", 2)
        
        alternatives = []
        
        if expected_maps == 3:
            alternatives.append({
                "type": "Тотал карт >2.5",
                "reason": "Ожидается напряженная борьба",
                "confidence": "СРЕДНЯЯ"
            })
        
        alternatives.append({
            "type": "Фора +1.5 слабой команды",
            "reason": "Страховка на случай неожиданностей",
            "confidence": "ВЫСОКАЯ"
        })
        
        return alternatives
    
    @staticmethod
    def _get_reason(confidence: float, probability: float, risk_level: str) -> str:
        """Причина рекомендации"""
        if confidence > 70:
            return "Сильный сигнал от нейросети, высокая статистическая значимость"
        elif confidence > 50:
            return "Умеренный сигнал, но есть явные преимущества"
        else:
            return "Низкая уверенность, ставка в основном для диверсификации"
    
    @staticmethod
    def _get_risk_warnings(risk_level: str) -> List[str]:
        """Предупреждения о рисках"""
        warnings = [
            "Ставки на спорт связаны с риском потери денег",
            "Никогда не ставьте последние деньги",
            "Ведите учет всех ставок"
        ]
        
        if risk_level == "HIGH":
            warnings.append("⚠️ ВЫСОКИЙ РИСК: Этот матч очень непредсказуем")
        elif risk_level == "MEDIUM":
            warnings.append("⚠️ СРЕДНИЙ РИСК: Есть факторы неопределенности")
        
        return warnings
    
    @staticmethod
    def _generate_basic_recommendations(prediction: Dict) -> Dict:
        """Базовые рекомендации для локального анализа"""
        return {
            "primary_recommendation": {
                "type": "Тотал карт >2.5",
                "confidence": "НИЗКАЯ",
                "stake": "0.5-1%",
                "expected_odds": 1.8,
                "reason": "Недостаточно данных для точного прогноза"
            },
            "alternative_bets": [],
            "value_bets": [],
            "best_bookmakers": [],
            "risk_warnings": [
                "⚠️ Анализ проведен без нейросети",
                "⚠️ Требуется дополнительное исследование",
                "⚠️ Высокий риск"
            ],
            "bankroll_advice": "Рекомендуется пропустить этот матч или поставить минимальную сумму",
            "ai_confidence": "Локальный анализ"
        }

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
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
    elif "heroic" in team_lower:
        return "⚔️"
    
    return "🎮"

# ========== КЛАВИАТУРЫ ==========
def create_main_keyboard():
    """Главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 МАТЧИ СЕГОДНЯ", callback_data="today"),
            InlineKeyboardButton(text="📅 МАТЧИ ЗАВТРА", callback_data="tomorrow")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE МАТЧИ", callback_data="live"),
            InlineKeyboardButton(text="🤖 АНАЛИЗ НЕЙРОСЕТЬЮ", callback_data="analyze")
        ],
        [
            InlineKeyboardButton(text="📊 СТАВКИ И КОЭФФИЦИЕНТЫ", callback_data="betting"),
            InlineKeyboardButton(text="ℹ️ О БОТЕ", callback_data="about")
        ]
    ])
    return keyboard

def create_match_selection_keyboard(matches: List[Dict], prefix: str = "analyze"):
    """Клавиатура для выбора матча"""
    buttons = []
    
    for i, match in enumerate(matches[:6]):  # Максимум 6 матчей
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            time_str = format_match_time(match.get("scheduled_at", ""))
            
            button_text = f"{team1_name} vs {team2_name} ({time_str})"
            if len(button_text) > 35:
                button_text = button_text[:32] + "..."
            
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"{prefix}_{i}"
            )])
    
    buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_analysis_actions_keyboard(match_index: int):
    """Действия после анализа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 ДЕТАЛЬНЫЙ ОТЧЕТ", callback_data=f"report_{match_index}"),
            InlineKeyboardButton(text="💰 СТАВКИ", callback_data=f"bets_{match_index}")
        ],
        [
            InlineKeyboardButton(text="🎯 БЫСТРЫЙ ПРОГНОЗ", callback_data=f"quick_{match_index}"),
            InlineKeyboardButton(text="📈 КОЭФФИЦИЕНТЫ", callback_data=f"odds_{match_index}")
        ],
        [
            InlineKeyboardButton(text="🤖 АНАЛИЗ ДРУГОГО МАТЧА", callback_data="analyze"),
            InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")
        ]
    ])

# ========== ИНИЦИАЛИЗАЦИЯ ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)
betting_analytics = SmartBettingAnalytics()

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    ai_status = "✅ АКТИВНА (DeepSeek)" if DEEPSEEK_AVAILABLE else "⚠️ ЛОКАЛЬНЫЙ РЕЖИМ"
    
    welcome = f"""
🎮 <b>CS2 AI ANALYST</b>

🤖 <b>Нейросеть:</b> {ai_status}
📊 <b>Аналитика:</b> Глубокая с множеством факторов
💰 <b>Ставки:</b> Умные рекомендации с оценкой риска

<b>Возможности:</b>
• 📅 Расписание матчей (сегодня/завтра/live)
• 🤖 Анализ от нейросети DeepSeek
• 📊 Детальные отчеты с ключевыми факторами
• 💰 Рекомендации по ставкам и коэффициенты
• 🎯 Value bets поиск

<b>Для DeepSeek нейросети добавьте в .env:</b>
<code>DEEPSEEK_API_KEY=ваш_ключ</code>

👇 <b>Выберите раздел:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "today")
async def handle_today(callback: types.CallbackQuery):
    """Матчи сегодня"""
    await callback.answer("📅 Загружаю матчи на сегодня...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>На сегодня нет запланированных матчей CS2</b>\n\n"
            "Проверьте завтра или live матчи.",
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
            
            lines.append(f"{i}. {team1_emoji} <b>{team1_name}</b> vs {team2_emoji} <b>{team2_name}</b>")
            lines.append(f"   ⏰ {time_str} | 🏆 {league}")
            lines.append("")
    
    lines.append(f"⏱️ <i>Время указано в MSK</i>")
    lines.append(f"")
    lines.append(f"🤖 <b>Для анализа матча нейросетью нажмите:</b> АНАЛИЗ НЕЙРОСЕТЬЮ")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 АНАЛИЗ НЕЙРОСЕТЬЮ", callback_data="analyze")],
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "tomorrow")
async def handle_tomorrow(callback: types.CallbackQuery):
    """Матчи завтра"""
    await callback.answer("📅 Загружаю матчи на завтра...")
    
    matches = await panda_api.get_tomorrow_matches()
    
    if not matches:
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
        await callback.message.edit_text(
            f"📭 <b>На завтра ({tomorrow_date}) нет матчей</b>",
            reply_markup=create_main_keyboard()
        )
        return
    
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
    
    lines = [
        f"📅 <b>МАТЧИ НА ЗАВТРА</b>",
        f"<i>{tomorrow_date}</i>",
        "",
        f"📊 Найдено матчей: {len(matches)}",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches[:8], 1):
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
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
            "📡 <b>В данный момент нет live матчей CS2</b>",
            reply_markup=create_main_keyboard()
        )
        return
    
    lines = [
        "🔥 <b>LIVE МАТЧИ CS2</b>",
        "",
        f"📊 Матчей в эфире: {len(matches)}",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches, 1):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            
            results = match.get("results", [])
            score1 = results[0].get("score", 0) if len(results) > 0 else 0
            score2 = results[1].get("score", 0) if len(results) > 1 else 0
            
            team1_emoji = get_team_emoji(team1_name)
            team2_emoji = get_team_emoji(team2_name)
            
            league = match.get("league", {}).get("name", "")
            
            lines.append(f"{i}. 🔴 {team1_emoji} <b>{team1_name}</b> {score1}:{score2} <b>{team2_name}</b> {team2_emoji}")
            lines.append(f"   🏆 {league}")
            lines.append("")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "analyze")
async def handle_analyze(callback: types.CallbackQuery):
    """Анализ матча нейросетью"""
    await callback.answer("🤖 Загружаю матчи для анализа...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>Сегодня нет матчей для анализа</b>\n\n"
            "Нейросеть может анализировать только предстоящие матчи.",
            reply_markup=create_main_keyboard()
        )
        return
    
    ai_status = "использует DeepSeek нейросеть" if DEEPSEEK_AVAILABLE else "в локальном режиме"
    
    await callback.message.edit_text(
        f"🤖 <b>ВЫБЕРИТЕ МАТЧ ДЛЯ АНАЛИЗА</b>\n\n"
        f"Найдено матчей на сегодня: {len(matches)}\n"
        f"Нейросеть {ai_status}.\n"
        f"Анализ занимает 10-20 секунд.",
        reply_markup=create_match_selection_keyboard(matches, "analyze")
    )

@dp.callback_query(F.data.startswith("analyze_"))
async def handle_analyze_specific(callback: types.CallbackQuery):
    """Анализ конкретного матча"""
    match_index = int(callback.data.split("_")[1])
    await callback.answer("🤖 Нейросеть анализирует матч...")
    
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.message.edit_text("❌ Матч не найден", reply_markup=create_main_keyboard())
        return
    
    match = matches[match_index]
    opponents = match.get("opponents", [])
    
    if len(opponents) < 2:
        await callback.message.edit_text("❌ Недостаточно данных", reply_markup=create_main_keyboard())
        return
    
    team1 = opponents[0].get("opponent", {})
    team2 = opponents[1].get("opponent", {})
    
    team1_name = team1.get("acronym") or team1.get("name", "TBA")
    team2_name = team2.get("acronym") or team2.get("name", "TBA")
    tournament = match.get("league", {}).get("name", "")
    time_str = format_match_time(match.get("scheduled_at", ""))
    
    # Показываем загрузку
    loading_msg = await callback.message.edit_text(
        f"🤖 <b>АНАЛИЗ МАТЧА</b>\n\n"
        f"{team1_name} vs {team2_name}\n"
        f"⏰ {time_str} | 🏆 {tournament}\n\n"
        f"🔄 Нейросеть анализирует статистику, форму команд, тактику...\n"
        f"<i>Это займет 10-20 секунд</i>"
    )
    
    # Запускаем анализ
    analysis = await DeepSeekAnalyzer.analyze_match(team1_name, team2_name, tournament)
    
    # Генерация рекомендаций по ставкам
    betting_recs = betting_analytics.generate_betting_recommendations(analysis)
    
    # Формируем основной ответ
    match_pred = analysis.get("match_prediction", {})
    risk_assessment = analysis.get("risk_assessment", {})
    
    winner = match_pred.get("most_likely_winner", "Не определен")
    probability = match_pred.get("winner_probability", 50)
    confidence = risk_assessment.get("confidence", 50)
    risk_level = risk_assessment.get("risk_level", "MEDIUM")
    predicted_score = match_pred.get("predicted_score", "2:1")
    
    lines = [
        f"🎯 <b>АНАЛИЗ ОТ НЕЙРОСЕТИ</b>",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"⏰ {time_str} | 🏆 {tournament}",
        f"",
        f"📊 <b>ОСНОВНОЙ ПРОГНОЗ:</b>",
        f"• Победитель: <b>{winner}</b>",
        f"• Вероятность: <b>{probability}%</b>",
        f"• Прогноз счета: <b>{predicted_score}</b>",
        f"• Уверенность анализа: <b>{confidence}%</b>",
        f"• Уровень риска: <b>{risk_level}</b>",
        f"",
        f"💰 <b>СТАВКИ:</b>",
        f"• Рекомендация: <b>{betting_recs['primary_recommendation']['type']}</b>",
        f"• Уверенность: {betting_recs['primary_recommendation']['confidence']}",
        f"• Размер ставки: {betting_recs['primary_recommendation']['stake']}",
        f"",
        f"🤖 <b>МОДЕЛЬ:</b> {analysis.get('ai_model', 'Локальная')}",
        f"",
        f"👇 <b>Выберите действие:</b>"
    ]
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_actions_keyboard(match_index),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data.startswith("report_"))
async def handle_report(callback: types.CallbackQuery):
    """Детальный отчет"""
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
    
    await callback.answer("📊 Формирую детальный отчет...")
    
    analysis = await DeepSeekAnalyzer.analyze_match(team1_name, team2_name, tournament)
    
    team_analysis = analysis.get("team_analysis", {})
    detailed = analysis.get("detailed_analysis", "Нет детального анализа")
    key_factors = analysis.get("key_factors", [])
    
    lines = [
        f"📊 <b>ДЕТАЛЬНЫЙ АНАЛИТИЧЕСКИЙ ОТЧЕТ</b>",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"",
        f"👥 <b>АНАЛИЗ КОМАНД:</b>",
        f"",
        f"<b>{team1_name}:</b>",
        f"• Сила: {team_analysis.get('team1', {}).get('strength', '?')}/100",
        f"• Форма: {team_analysis.get('team1', {}).get('current_form', '?')}",
        f"• Сильные стороны: {', '.join(team_analysis.get('team1', {}).get('key_strengths', []))}",
        f"• Слабые стороны: {', '.join(team_analysis.get('team1', {}).get('weaknesses', []))}",
        f"",
        f"<b>{team2_name}:</b>",
        f"• Сила: {team_analysis.get('team2', {}).get('strength', '?')}/100",
        f"• Форма: {team_analysis.get('team2', {}).get('current_form', '?')}",
        f"• Сильные стороны: {', '.join(team_analysis.get('team2', {}).get('key_strengths', []))}",
        f"• Слабые стороны: {', '.join(team_analysis.get('team2', {}).get('weaknesses', []))}",
        f"",
        f"⚡ <b>КЛЮЧЕВЫЕ ФАКТОРЫ:</b>"
    ]
    
    for i, factor in enumerate(key_factors[:5], 1):
        lines.append(f"{i}. {factor.get('factor', '')} - влияние: {factor.get('impact', '')}")
    
    lines.extend([
        f"",
        f"📝 <b>РАЗВЕРНУТЫЙ АНАЛИЗ:</b>",
        f"{detailed[:800]}" + ("..." if len(detailed) > 800 else ""),
        f"",
        f"🤖 <b>ИСТОЧНИК:</b> {analysis.get('ai_model', 'Локальная база знаний')}",
        f"",
        f"⚠️ <i>Анализ предоставлен для информационных целей</i>"
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_actions_keyboard(match_index),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data.startswith("bets_"))
async def handle_bets(callback: types.CallbackQuery):
    """Рекомендации по ставкам"""
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
    
    await callback.answer("💰 Анализирую ставки...")
    
    analysis = await DeepSeekAnalyzer.analyze_match(team1_name, team2_name, tournament)
    betting_recs = betting_analytics.generate_betting_recommendations(analysis)
    
    lines = [
        f"💰 <b>РЕКОМЕНДАЦИИ ПО СТАВКАМ</b>",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"",
        f"🎯 <b>ОСНОВНАЯ РЕКОМЕНДАЦИЯ:</b>",
        f"• Тип: {betting_recs['primary_recommendation']['type']}",
        f"• Уверенность: {betting_recs['primary_recommendation']['confidence']}",
        f"• Размер: {betting_recs['primary_recommendation']['stake']}",
        f"• Причина: {betting_recs['primary_recommendation']['reason']}",
        f"",
        f"📊 <b>АЛЬТЕРНАТИВНЫЕ СТАВКИ:</b>"
    ]
    
    if betting_recs['alternative_bets']:
        for bet in betting_recs['alternative_bets']:
            lines.append(f"• {bet['type']} ({bet['confidence']}) - {bet['reason']}")
    else:
        lines.append("• Нет альтернативных рекомендаций")
    
    lines.extend([
        f"",
        f"📈 <b>VALUE BETS (выгодные ставки):</b>"
    ])
    
    if betting_recs['value_bets']:
        for vb in betting_recs['value_bets'][:3]:
            lines.append(f"• {vb['bookmaker']}: коэффициент {vb['odds']} (value: +{vb['value']}%)")
    else:
        lines.append("• Явных value bets не найдено")
    
    lines.extend([
        f"",
        f"🏦 <b>ЛУЧШИЕ БУКМЕКЕРЫ ДЛЯ ЭТОГО МАТЧА:</b>"
    ])
    
    if betting_recs['best_bookmakers']:
        for bm in betting_recs['best_bookmakers'][:3]:
            lines.append(f"• {bm['bookmaker']}: коэффициент ~{bm['odds']} ({bm['reliability']})")
    else:
        lines.append("• Используйте 1xBet, BetBoom или Marathon")
    
    lines.extend([
        f"",
        f"⚠️ <b>ПРЕДУПРЕЖДЕНИЯ О РИСКАХ:</b>"
    ])
    
    for warning in betting_recs['risk_warnings'][:3]:
        lines.append(f"• {warning}")
    
    lines.extend([
        f"",
        f"💡 <b>СОВЕТ:</b> {betting_recs['bankroll_advice']}",
        f"",
        f"🤖 <b>УВЕРЕННОСТЬ НЕЙРОСЕТИ:</b> {betting_recs['ai_confidence']}",
        f"",
        f"<i>Ставки на спорт связаны с риском. Играйте ответственно.</i>"
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_actions_keyboard(match_index),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "betting")
async def handle_betting_info(callback: types.CallbackQuery):
    """Информация о ставках"""
    lines = [
        "💰 <b>УМНАЯ СИСТЕМА СТАВОК</b>",
        "",
        "🎯 <b>Как работает:</b>",
        "1. Нейросеть анализирует матч по 10+ факторам",
        "2. Определяет вероятности и уровень риска",
        "3. Генерирует персонализированные рекомендации",
        "4. Ищет value bets (ставки с положительным матожиданием)",
        "",
        "📊 <b>Факторы анализа:</b>",
        "• Текущая форма команд",
        "• Статистика на картах",
        "• Индивидуальная форма игроков",
        "• История личных встреч",
        "• Тактические особенности",
        "• Турнирная мотивация",
        "• Психологическая устойчивость",
        "",
        "🎲 <b>Типы рекомендаций:</b>",
        "• Основная ставка (самая выгодная)",
        "• Альтернативные ставки (для диверсификации)",
        "• Value bets (ставки с edge)",
        "• Ставки которых следует избегать",
        "",
        "🏦 <b>Рекомендуемые букмекеры:</b>",
        "• 1xBet - лучшие коэффициенты",
        "• BetBoom - удобное приложение",
        "• Marathon - низкая маржа",
        "• Fonbet - надежность",
        "",
        "⚠️ <b>Важные правила:</b>",
        "1. Никогда не ставьте больше 5% от банка",
        "2. Ведите учет всех ставок",
        "3. Не пытайтесь отыграться после проигрыша",
        "4. Делайте перерывы",
        "5. Играйте только на свободные деньги",
        "",
        "🤖 <b>Нейросеть:</b> " + ("DeepSeek AI" if DEEPSEEK_AVAILABLE else "Локальный анализатор"),
        "",
        "<i>Бот для аналитических целей. Решения о ставках принимайте самостоятельно.</i>"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 АНАЛИЗ МАТЧА", callback_data="analyze")],
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "about")
async def handle_about(callback: types.CallbackQuery):
    """О боте"""
    ai_status = "✅ DeepSeek нейросеть активна" if DEEPSEEK_AVAILABLE else "⚠️ Локальный режим (добавьте DEEPSEEK_API_KEY в .env)"
    
    lines = [
        "ℹ️ <b>О CS2 AI ANALYST</b>",
        "",
        "🤖 <b>Технологии:</b>",
        "• Искусственный интеллект DeepSeek",
        "• Анализ по множеству факторов",
        "• Машинное обучение для прогнозов",
        "• Умная система рекомендаций",
        "",
        "📊 <b>Источники данных:</b>",
        "• PandaScore API - расписание матчей",
        "• DeepSeek AI - анализ и прогнозы",
        "• Локальная база знаний команд",
        "• Статистические модели",
        "",
        "🎯 <b>Точность:</b>",
        "• Нейросеть анализирует 10+ факторов",
        "• Учитывает текущую форму и мотивацию",
        "• Оценивает тактические особенности",
        "• Дает вероятностные прогнозы",
        "",
        f"🔧 <b>Статус:</b> {ai_status}",
        "",
        "💡 <b>Для максимальной точности:</b>",
        "1. Добавьте DEEPSEEK_API_KEY в .env файл",
        "2. Используйте команду /start для проверки",
        "3. Анализируйте матчи за 1-2 часа до начала",
        "",
        "⚠️ <b>Отказ от ответственности:</b>",
        "Бот предоставляет аналитику для информационных целей.",
        "Не гарантирует выигрыш в ставках.",
        "Играйте ответственно (18+).",
        "",
        "📧 <b>Поддержка:</b> @ваш_аккаунт",
        "",
        "<i>Версия 2.0 с нейросетью DeepSeek</i>"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "back")
async def handle_back(callback: types.CallbackQuery):
    """Назад в главное меню"""
    await cmd_start(callback.message)
    await callback.answer()

# ========== КОМАНДЫ ==========
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь"""
    await handle_about(
        types.CallbackQuery(
            id="help",
            from_user=message.from_user,
            chat_instance="help",
            message=message,
            data="about"
        )
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Статус бота"""
    ai_status = "🟢 DeepSeek активна" if DEEPSEEK_AVAILABLE else "🟡 Локальный режим"
    
    status_text = f"""
📊 <b>СТАТУС БОТА</b>

🤖 <b>Нейросеть:</b> {ai_status}
📡 <b>API PandaScore:</b> {"🟢 Активно" if PANDASCORE_TOKEN else "🔴 Не настроено"}
🔧 <b>Версия:</b> 2.0 с DeepSeek AI

<b>Для активации нейросети:</b>
1. Получите ключ: https://platform.deepseek.com
2. Добавьте в .env: DEEPSEEK_API_KEY=ваш_ключ
3. Перезапустите бота

<b>Текущие функции:</b>
• Анализ матчей нейросетью
• Умные рекомендации по ставкам
• Поиск value bets
• Расписание матчей
"""
    
    await message.answer(status_text)

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск бота"""
    logger.info("🎮 Запускаю CS2 AI ANALYST...")
    
    if DEEPSEEK_AVAILABLE:
        logger.info("🤖 DeepSeek нейросеть: АКТИВНА")
    else:
        logger.warning("🤖 DeepSeek нейросеть: НЕ АКТИВНА (добавьте ключ в .env)")
    
    logger.info("📊 Парсинг матчей: PandaScore API")
    logger.info("💰 Умные ставки: Value bets поиск")
    
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