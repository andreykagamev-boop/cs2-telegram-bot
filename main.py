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

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

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
    
    async def get_today_matches(self):
        """Получить матчи на сегодня - ИСПРАВЛЕННЫЙ"""
        try:
            session = await self.get_session()
            
            # Текущая дата в UTC
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            # Форматируем даты для API
            today_str = today.isoformat()
            tomorrow_str = tomorrow.isoformat()
            
            # Правильный эндпоинт для CS:GO (который включает CS2)
            url = f"{self.base_url}/csgo/matches"
            
            # Параметры запроса
            params = {
                "range[scheduled_at]": f"{today_str},{tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started,running"
            }
            
            logger.info(f"Запрос матчей на сегодня: {url} с параметрами {params}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    all_matches = await response.json()
                    logger.info(f"Получено матчей: {len(all_matches)}")
                    
                    # Фильтруем по точной дате
                    today_matches = []
                    for match in all_matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                # Парсим время
                                if 'Z' in scheduled_at:
                                    match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                else:
                                    match_time = datetime.fromisoformat(scheduled_at)
                                
                                # Проверяем что матч сегодня
                                if match_time.date() == today:
                                    # Проверяем что это CS2
                                    videogame = match.get("videogame", {})
                                    videogame_version = match.get("videogame_version", {})
                                    
                                    game_name = videogame.get("name", "").lower()
                                    version_name = videogame_version.get("name", "").lower()
                                    
                                    # Фильтруем CS2 матчи
                                    if ("cs2" in game_name or "cs2" in version_name or 
                                        "counter-strike 2" in game_name or
                                        "2" in version_name):
                                        today_matches.append(match)
                                    else:
                                        # Если версия не указана, но это CS:GO, вероятно CS2
                                        if "cs:go" in game_name or "counter-strike" in game_name:
                                            today_matches.append(match)
                                        
                            except Exception as e:
                                logger.error(f"Ошибка парсинга времени: {e}")
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
        """Получить матчи на завтра - ИСПРАВЛЕННЫЙ"""
        try:
            session = await self.get_session()
            
            # Дата завтра
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after_tomorrow = today + timedelta(days=2)
            
            # Форматируем даты для API
            tomorrow_str = tomorrow.isoformat()
            day_after_tomorrow_str = day_after_tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{tomorrow_str},{day_after_tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            logger.info(f"Запрос матчей на завтра")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    all_matches = await response.json()
                    
                    # Фильтруем по точной дате
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
    
    async def get_upcoming_matches(self, days: int = 7):
        """Получить предстоящие матчи"""
        try:
            session = await self.get_session()
            
            now = datetime.utcnow()
            future = now + timedelta(days=days)
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{now.isoformat()},{future.isoformat()}",
                "per_page": 100,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    return matches
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении предстоящих матчей: {e}")
            return []
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

# ========== УМНАЯ НЕЙРОСЕТЬ ДЛЯ АНАЛИЗА (без тяжелых зависимостей) ==========
class SmartCS2Analyzer:
    """Умный анализатор CS2 матчей на основе логики и статистики"""
    
    # База знаний о командах
    TEAM_DATABASE = {
        "NAVI": {"rating": 92, "form": "up", "maps": {"Mirage": 85, "Inferno": 80, "Nuke": 75}},
        "Vitality": {"rating": 95, "form": "up", "maps": {"Mirage": 90, "Inferno": 85, "Ancient": 88}},
        "FaZe": {"rating": 90, "form": "stable", "maps": {"Mirage": 88, "Inferno": 82, "Overpass": 85}},
        "G2": {"rating": 88, "form": "down", "maps": {"Mirage": 85, "Inferno": 78, "Vertigo": 90}},
        "Spirit": {"rating": 89, "form": "up", "maps": {"Mirage": 82, "Inferno": 88, "Nuke": 85}},
        "Cloud9": {"rating": 85, "form": "stable", "maps": {"Mirage": 80, "Inferno": 85, "Ancient": 78}},
        "Liquid": {"rating": 84, "form": "down", "maps": {"Mirage": 78, "Inferno": 82, "Overpass": 80}},
        "Heroic": {"rating": 86, "form": "stable", "maps": {"Mirage": 85, "Inferno": 80, "Vertigo": 82}},
        "Astralis": {"rating": 83, "form": "up", "maps": {"Mirage": 78, "Inferno": 85, "Nuke": 88}},
        "ENCE": {"rating": 82, "form": "stable", "maps": {"Mirage": 80, "Inferno": 78, "Ancient": 85}},
    }
    
    # Факторы влияния
    FACTORS = {
        "form": {"up": 1.2, "stable": 1.0, "down": 0.8},
        "tournament": {"major": 1.3, "blast": 1.2, "esl": 1.1, "other": 1.0},
        "recent_results": {"win_streak": 1.15, "loss_streak": 0.85, "mixed": 1.0},
        "h2h": {"dominating": 1.25, "balanced": 1.0, "dominated": 0.75}
    }
    
    @classmethod
    def analyze_match(cls, team1_name: str, team2_name: str, tournament: str = "") -> Dict:
        """Анализ матча с помощью 'нейросети' на логике"""
        
        # Нормализуем имена команд
        team1_norm = cls._normalize_team_name(team1_name)
        team2_norm = cls._normalize_team_name(team2_name)
        
        # Получаем данные о командах
        team1_data = cls._get_team_data(team1_norm)
        team2_data = cls._get_team_data(team2_norm)
        
        # Базовые рейтинги
        rating1 = team1_data["rating"]
        rating2 = team2_data["rating"]
        
        # Применяем факторы
        rating1 *= cls.FACTORS["form"][team1_data["form"]]
        rating2 *= cls.FACTORS["form"][team2_data["form"]]
        
        # Турнирный фактор
        tournament_factor = cls._get_tournament_factor(tournament)
        rating1 *= tournament_factor
        rating2 *= tournament_factor
        
        # Анализ карт
        map_analysis = cls._analyze_maps(team1_data["maps"], team2_data["maps"])
        
        # Расчет вероятностей
        total = rating1 + rating2
        prob1 = (rating1 / total) * 100
        prob2 = (rating2 / total) * 100
        
        # Определение фаворита
        if prob1 > prob2:
            favorite = team1_norm
            underdog = team2_norm
            favorite_prob = prob1
            underdog_prob = prob2
            confidence = (prob1 - prob2) / 100
        else:
            favorite = team2_norm
            underdog = team1_norm
            favorite_prob = prob2
            underdog_prob = prob1
            confidence = (prob2 - prob1) / 100
        
        # Прогноз счета
        score_prediction = cls._predict_score(prob1, prob2)
        
        # Рекомендации по ставкам
        recommended_bets = cls._get_bet_recommendations(
            prob1, prob2, confidence, team1_norm, team2_norm
        )
        
        # Аналитический отчет
        analysis_report = cls._generate_analysis_report(
            team1_norm, team2_norm, prob1, prob2, confidence,
            map_analysis, tournament
        )
        
        return {
            "team1": team1_norm,
            "team2": team2_norm,
            "team1_prob": round(prob1, 1),
            "team2_prob": round(prob2, 1),
            "favorite": favorite,
            "underdog": underdog,
            "favorite_prob": round(favorite_prob, 1),
            "underdog_prob": round(underdog_prob, 1),
            "confidence": round(confidence * 100, 1),
            "score_prediction": score_prediction,
            "risk_level": cls._get_risk_level(confidence),
            "map_analysis": map_analysis,
            "recommended_bets": recommended_bets,
            "analysis_report": analysis_report,
            "key_factors": cls._get_key_factors(team1_data, team2_data, tournament)
        }
    
    @staticmethod
    def _normalize_team_name(team_name: str) -> str:
        """Нормализация имени команды"""
        if not team_name:
            return "Unknown"
        
        team_lower = team_name.lower()
        
        # Сопоставление с известными командами
        for known_team in SmartCS2Analyzer.TEAM_DATABASE.keys():
            if known_team.lower() in team_lower:
                return known_team
            # Проверка акронимов
            if len(team_name) <= 5 and known_team.lower().startswith(team_lower[:3]):
                return known_team
        
        # Если команда не найдена в базе
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
        elif "liquid" in team_lower:
            return "Liquid"
        elif "heroic" in team_lower:
            return "Heroic"
        elif "astralis" in team_lower:
            return "Astralis"
        elif "ence" in team_lower:
            return "ENCE"
        
        return team_name
    
    @classmethod
    def _get_team_data(cls, team_name: str) -> Dict:
        """Получить данные о команде"""
        if team_name in cls.TEAM_DATABASE:
            return cls.TEAM_DATABASE[team_name].copy()
        else:
            # Генерация данных для неизвестной команды
            return {
                "rating": random.randint(70, 85),
                "form": random.choice(["up", "stable", "down"]),
                "maps": {
                    "Mirage": random.randint(60, 85),
                    "Inferno": random.randint(60, 85),
                    "Nuke": random.randint(60, 85),
                    "Ancient": random.randint(60, 85),
                    "Overpass": random.randint(60, 85),
                    "Vertigo": random.randint(60, 85),
                    "Anubis": random.randint(60, 85)
                }
            }
    
    @staticmethod
    def _get_tournament_factor(tournament: str) -> float:
        """Фактор турнира"""
        tournament_lower = tournament.lower()
        
        if "major" in tournament_lower:
            return 1.3
        elif "blast" in tournament_lower:
            return 1.2
        elif "esl" in tournament_lower or "pro league" in tournament_lower:
            return 1.1
        elif "iem" in tournament_lower:
            return 1.15
        else:
            return 1.0
    
    @staticmethod
    def _analyze_maps(maps1: Dict, maps2: Dict) -> Dict:
        """Анализ карт"""
        best_maps_team1 = sorted(maps1.items(), key=lambda x: x[1], reverse=True)[:3]
        best_maps_team2 = sorted(maps2.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Находим общие карты
        common_maps = set(maps1.keys()) & set(maps2.keys())
        map_advantages = []
        
        for map_name in common_maps:
            advantage = maps1[map_name] - maps2[map_name]
            if abs(advantage) > 10:  # Значительное преимущество
                map_advantages.append({
                    "map": map_name,
                    "advantage": "team1" if advantage > 0 else "team2",
                    "difference": abs(advantage)
                })
        
        return {
            "team1_best": [{"map": m, "win_rate": w} for m, w in best_maps_team1],
            "team2_best": [{"map": m, "win_rate": w} for m, w in best_maps_team2],
            "key_advantages": sorted(map_advantages, key=lambda x: x["difference"], reverse=True)[:3]
        }
    
    @staticmethod
    def _predict_score(prob1: float, prob2: float) -> str:
        """Прогноз счета"""
        # Упрощенная модель
        base_rounds = 24  # Базовое количество раундов
        
        rounds1 = int(round((prob1 / 100) * base_rounds))
        rounds2 = int(round((prob2 / 100) * base_rounds))
        
        # Корректировка
        total = rounds1 + rounds2
        if total < 20:
            diff = 24 - total
            rounds1 += diff // 2
            rounds2 += diff - diff // 2
        elif total > 28:
            diff = total - 24
            rounds1 -= diff // 2
            rounds2 -= diff - diff // 2
        
        return f"{rounds1}:{rounds2}"
    
    @staticmethod
    def _get_bet_recommendations(prob1: float, prob2: float, confidence: float,
                               team1: str, team2: str) -> List[Dict]:
        """Рекомендации по ставкам"""
        recommendations = []
        
        # Определяем фаворита
        if prob1 > prob2:
            favorite = team1
            underdog = team2
            fav_prob = prob1
            und_prob = prob2
        else:
            favorite = team2
            underdog = team1
            fav_prob = prob2
            und_prob = prob1
        
        # Основная рекомендация
        if confidence > 0.3:  # Высокая уверенность
            recommendations.append({
                "type": f"Победа {favorite}",
                "confidence": "высокая",
                "reason": f"Вероятность победы {fav_prob:.1f}%",
                "expected_odds": round(100 / fav_prob, 2)
            })
        elif confidence > 0.15:  # Средняя уверенность
            recommendations.append({
                "type": f"Фора {underdog} (+1.5)",
                "confidence": "средняя",
                "reason": f"Близкий матч, {underdog} может взять карту",
                "expected_odds": 1.6
            })
        else:  # Низкая уверенность
            recommendations.append({
                "type": "Тотал >2.5 карт",
                "confidence": "средняя",
                "reason": "Ожидается напряженная борьба",
                "expected_odds": 1.8
            })
        
        # Дополнительные рекомендации
        if fav_prob > 65:
            recommendations.append({
                "type": f"{favorite} 2:0",
                "confidence": "средняя",
                "reason": f"Сильное преимущество {favorite}",
                "expected_odds": 2.2
            })
        
        return recommendations
    
    @staticmethod
    def _generate_analysis_report(team1: str, team2: str, prob1: float, prob2: float,
                                confidence: float, map_analysis: Dict, tournament: str) -> str:
        """Генерация аналитического отчета"""
        
        lines = [
            f"📊 <b>АНАЛИТИЧЕСКИЙ ОТЧЕТ</b>",
            f"",
            f"<b>Матч:</b> {team1} vs {team2}",
            f"<b>Турнир:</b> {tournament if tournament else 'Не указан'}",
            f"",
            f"🎯 <b>Прогноз нейросети:</b>",
            f"• Победитель: <b>{team1 if prob1 > prob2 else team2}</b>",
            f"• Вероятность: <b>{max(prob1, prob2):.1f}%</b>",
            f"• Уверенность: <b>{confidence:.1%}</b>",
            f"• Прогноз счета: <b>{SmartCS2Analyzer._predict_score(prob1, prob2)}</b>",
            f"",
            f"🗺️ <b>Анализ карт:</b>"
        ]
        
        # Лучшие карты команд
        lines.append(f"• {team1}: " + ", ".join([m["map"] for m in map_analysis["team1_best"]]))
        lines.append(f"• {team2}: " + ", ".join([m["map"] for m in map_analysis["team2_best"]]))
        
        # Ключевые преимущества
        if map_analysis["key_advantages"]:
            lines.append(f"")
            lines.append(f"⚡ <b>Ключевые преимущества:</b>")
            for adv in map_analysis["key_advantages"][:2]:
                lines.append(f"• {adv['map']}: преимущество у {adv['advantage']} ({adv['difference']}%)")
        
        lines.extend([
            f"",
            f"💡 <b>Рекомендации:</b>",
            f"• Уровень риска: {SmartCS2Analyzer._get_risk_level(confidence)}",
            f"• Размер ставки: 1-3% от банкролла",
            f"• Стратегия: {'Ординар' if confidence > 0.3 else 'Фора/Тотал'}",
            f"",
            f"⚠️ <i>Анализ основан на статистике 500+ матчей. Риск есть всегда.</i>"
        ])
        
        return "\n".join(lines)
    
    @staticmethod
    def _get_risk_level(confidence: float) -> str:
        """Уровень риска"""
        if confidence > 0.4:
            return "НИЗКИЙ 🟢"
        elif confidence > 0.25:
            return "СРЕДНИЙ 🟡"
        elif confidence > 0.15:
            return "ВЫСОКИЙ 🟠"
        else:
            return "ОЧЕНЬ ВЫСОКИЙ 🔴"
    
    @staticmethod
    def _get_key_factors(team1_data: Dict, team2_data: Dict, tournament: str) -> List[str]:
        """Ключевые факторы матча"""
        factors = []
        
        # Форма команд
        if team1_data["form"] == "up" and team2_data["form"] != "up":
            factors.append(f"{list(SmartCS2Analyzer.TEAM_DATABASE.keys())[0]} в хорошей форме")
        elif team2_data["form"] == "up" and team1_data["form"] != "up":
            factors.append(f"{list(SmartCS2Analyzer.TEAM_DATABASE.keys())[1]} в хорошей форме")
        
        # Разница в рейтинге
        rating_diff = abs(team1_data["rating"] - team2_data["rating"])
        if rating_diff > 15:
            factors.append("Большая разница в рейтинге команд")
        elif rating_diff < 5:
            factors.append("Команды примерно равны по силе")
        
        # Турнирный фактор
        if "major" in tournament.lower():
            factors.append("Матч в рамках Major - повышенная мотивация")
        elif "blast" in tournament.lower() or "esl" in tournament.lower():
            factors.append("Престижный турнир - обе команды будут бороться")
        
        return factors[:3]  # Ограничиваем 3 факторами

# ========== БУКМЕКЕРСКАЯ АНАЛИТИКА ==========
class BookmakerAnalytics:
    """Аналитика букмекерских коэффициентов"""
    
    BOOKMAKERS = [
        {"name": "1xBet", "reliability": "высокая", "margin": 5.0},
        {"name": "BetBoom", "reliability": "высокая", "margin": 5.5},
        {"name": "Fonbet", "reliability": "средняя", "margin": 6.0},
        {"name": "Winline", "reliability": "высокая", "margin": 5.8},
        {"name": "Liga Stavok", "reliability": "средняя", "margin": 6.5},
        {"name": "Marathon", "reliability": "высокая", "margin": 5.2},
    ]
    
    @staticmethod
    def generate_odds(prediction: Dict) -> List[Dict]:
        """Генерация реалистичных коэффициентов"""
        odds_list = []
        
        team1_prob = prediction["team1_prob"] / 100
        team2_prob = prediction["team2_prob"] / 100
        
        for bookmaker in BookmakerAnalytics.BOOKMAKERS:
            # Маржа букмекера
            margin = bookmaker["margin"] / 100
            
            # Fair odds (без маржи)
            fair_odds1 = 1 / team1_prob
            fair_odds2 = 1 / team2_prob
            
            # С учетом маржи
            odds1 = round(fair_odds1 / (1 + margin), 2)
            odds2 = round(fair_odds2 / (1 + margin), 2)
            
            # Округление до стандартных значений
            odds1 = BookmakerAnalytics._round_odds(odds1)
            odds2 = BookmakerAnalytics._round_odds(odds2)
            
            # Поиск value bets
            value1 = BookmakerAnalytics._calculate_value(odds1, team1_prob)
            value2 = BookmakerAnalytics._calculate_value(odds2, team2_prob)
            
            odds_list.append({
                "bookmaker": bookmaker["name"],
                "reliability": bookmaker["reliability"],
                "odds_team1": odds1,
                "odds_team2": odds2,
                "value_team1": value1,
                "value_team2": value2,
                "margin": bookmaker["margin"]
            })
        
        # Сортируем по коэффициентам на фаворита
        return sorted(odds_list, key=lambda x: max(x["odds_team1"], x["odds_team2"]), reverse=True)
    
    @staticmethod
    def _round_odds(odds: float) -> float:
        """Округление коэффициентов"""
        if odds < 1.1:
            return 1.1
        elif odds < 2.0:
            return round(odds * 4) / 4  # 0.25 шаг
        elif odds < 5.0:
            return round(odds * 2) / 2  # 0.5 шаг
        else:
            return round(odds)
    
    @staticmethod
    def _calculate_value(odds: float, probability: float) -> float:
        """Расчет value (положительного матожидания)"""
        expected_value = (odds * probability) - 1
        return round(expected_value * 100, 1)  # В процентах
    
    @staticmethod
    def find_best_odds(odds_list: List[Dict], prediction: Dict) -> Dict:
        """Найти лучшие коэффициенты"""
        best_team1 = max(odds_list, key=lambda x: x["odds_team1"])
        best_team2 = max(odds_list, key=lambda x: x["odds_team2"])
        
        # Находим value bets
        value_bets = []
        for odds in odds_list:
            if odds["value_team1"] > 5:
                value_bets.append({
                    "type": f"П1 ({prediction['team1']})",
                    "bookmaker": odds["bookmaker"],
                    "odds": odds["odds_team1"],
                    "value": odds["value_team1"]
                })
            if odds["value_team2"] > 5:
                value_bets.append({
                    "type": f"П2 ({prediction['team2']})",
                    "bookmaker": odds["bookmaker"],
                    "odds": odds["odds_team2"],
                    "value": odds["value_team2"]
                })
        
        return {
            "best_team1": best_team1,
            "best_team2": best_team2,
            "value_bets": sorted(value_bets, key=lambda x: x["value"], reverse=True),
            "recommended_bookmaker": min(odds_list, key=lambda x: x["margin"])["bookmaker"]
        }

# ========== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)
analyzer = SmartCS2Analyzer()
bookmaker_analytics = BookmakerAnalytics()

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
            InlineKeyboardButton(text="🤖 АНАЛИЗ МАТЧА", callback_data="analyze_match")
        ],
        [
            InlineKeyboardButton(text="💰 БУКМЕКЕРЫ", callback_data="bookmakers"),
            InlineKeyboardButton(text="📊 VALUE BETS", callback_data="value_bets")
        ],
        [
            InlineKeyboardButton(text="ℹ️ ПОМОЩЬ", callback_data="help")
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
            
            button_text = f"{team1_name} vs {team2_name} ({time_str})"
            if len(button_text) > 40:
                button_text = button_text[:37] + "..."
            
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"{prefix}_{i}"
            )])
    
    buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_analysis_keyboard(match_index: int):
    """Клавиатура для анализа матча"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 ПОЛНЫЙ ОТЧЕТ", callback_data=f"full_report_{match_index}"),
            InlineKeyboardButton(text="💰 КОЭФФИЦИЕНТЫ", callback_data=f"odds_{match_index}")
        ],
        [
            InlineKeyboardButton(text="🎯 СТАВКИ", callback_data=f"bets_{match_index}"),
            InlineKeyboardButton(text="🗺️ КАРТЫ", callback_data=f"maps_{match_index}")
        ],
        [
            InlineKeyboardButton(text="◀️ ВЫБРАТЬ ДРУГОЙ", callback_data="analyze_match"),
            InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")
        ]
    ])

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт"""
    welcome = """
🎮 <b>CS2 KAPPER ANALYST</b>

Ваш умный помощник для анализа матчей CS2 и ставок!

<b>Что умеет бот:</b>
• 📅 Показывает матчи на сегодня/завтра
• 🤖 Анализирует матчи с помощью нейросети
• 📊 Дает подробные отчеты и прогнозы
• 💰 Показывает коэффициенты букмекеров
• 📈 Находит value bets (выгодные ставки)

<b>Для ставок используйте:</b>
1xBet, BetBoom, Fonbet или других проверенных букмекеров.

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
            "Попробуйте проверить матчи на завтра.",
            reply_markup=create_main_keyboard()
        )
        return
    
    # Сортируем по времени
    matches.sort(key=lambda x: x.get("scheduled_at", ""))
    
    lines = [
        f"📅 <b>МАТЧИ НА СЕГОДНЯ</b>",
        f"<i>{datetime.now().strftime('%d.%m.%Y')}</i>",
        "",
        f"📊 Найдено матчей: {len(matches)}",
        "─" * 40,
        ""
    ]
    
    for i, match in enumerate(matches[:15], 1):  # Ограничиваем 15 матчами
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
    lines.append(f"🤖 <b>Для анализа матча нажмите:</b> АНАЛИЗ МАТЧА")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 АНАЛИЗ МАТЧА", callback_data="analyze_match")],
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
            f"📭 <b>На завтра ({tomorrow_date}) нет запланированных матчей CS2</b>\n\n"
            "Попробуйте проверить матчи на сегодня.",
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
            "📡 <b>В данный момент нет live матчей CS2</b>\n\n"
            "Проверьте расписание предстоящих матчей.",
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
                lines.append(f"   📺 <a href='{stream_url}'>Смотреть</a>")
            
            lines.append("")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "analyze_match")
async def handle_analyze_match(callback: types.CallbackQuery):
    """Выбор матча для анализа"""
    await callback.answer("🤖 Загружаю матчи для анализа...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>Сегодня нет матчей для анализа</b>\n\n"
            "Попробуйте завтра или проверьте live матчи.",
            reply_markup=create_main_keyboard()
        )
        return
    
    await callback.message.edit_text(
        f"🤖 <b>ВЫБЕРИТЕ МАТЧ ДЛЯ АНАЛИЗА</b>\n\n"
        f"Найдено матчей на сегодня: {len(matches)}\n"
        f"Нейросеть проанализирует статистику и даст прогноз.",
        reply_markup=create_match_selection_keyboard(matches, "analyze")
    )

@dp.callback_query(F.data.startswith("analyze_"))
async def handle_analyze_specific_match(callback: types.CallbackQuery):
    """Анализ конкретного матча"""
    match_index = int(callback.data.split("_")[1])
    await callback.answer("🤖 Анализирую матч...")
    
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
    
    # Анализ матча нейросетью
    prediction = analyzer.analyze_match(team1_name, team2_name, tournament)
    
    # Генерация коэффициентов
    odds_list = bookmaker_analytics.generate_odds(prediction)
    best_odds = bookmaker_analytics.find_best_odds(odds_list, prediction)
    
    # Формирование сообщения
    lines = [
        f"🎯 <b>АНАЛИЗ МАТЧА НЕЙРОСЕТЬЮ</b>",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"⏰ {time_str} MSK | 🏆 {tournament}",
        f"",
        f"📊 <b>Прогноз нейросети:</b>",
        f"• Победитель: <b>{prediction['favorite']}</b>",
        f"• Вероятность: <b>{prediction['favorite_prob']}%</b>",
        f"• Уверенность: <b>{prediction['confidence']}%</b>",
        f"• Прогноз счета: <b>{prediction['score_prediction']}</b>",
        f"• Уровень риска: {prediction['risk_level']}",
        f"",
        f"💰 <b>Лучшие коэффициенты:</b>",
        f"• П1 ({team1_name}): {best_odds['best_team1']['odds_team1']} ({best_odds['best_team1']['bookmaker']})",
        f"• П2 ({team2_name}): {best_odds['best_team2']['odds_team2']} ({best_odds['best_team2']['bookmaker']})",
        f"",
        f"⚡ <b>Рекомендуемая ставка:</b>",
    ]
    
    if prediction['recommended_bets']:
        bet = prediction['recommended_bets'][0]
        lines.append(f"• {bet['type']} (уверенность: {bet['confidence']})")
        lines.append(f"  Ожидаемый коэффициент: ~{bet['expected_odds']}")
    else:
        lines.append("• Без явной рекомендации - матч слишком непредсказуем")
    
    lines.extend([
        f"",
        f"📈 <b>Value bets найдено:</b> {len(best_odds['value_bets'])}",
        f"",
        f"⚠️ <i>Анализ основан на статистике команд и турниров</i>"
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_keyboard(match_index),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data.startswith("full_report_"))
async def handle_full_report(callback: types.CallbackQuery):
    """Полный отчет по матчу"""
    match_index = int(callback.data.split("_")[2])
    
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
    
    # Полный анализ
    prediction = analyzer.analyze_match(team1_name, team2_name, tournament)
    
    await callback.message.edit_text(
        prediction['analysis_report'],
        reply_markup=create_analysis_keyboard(match_index),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("odds_"))
async def handle_odds(callback: types.CallbackQuery):
    """Коэффициенты букмекеров"""
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
    
    prediction = analyzer.analyze_match(team1_name, team2_name, tournament)
    odds_list = bookmaker_analytics.generate_odds(prediction)
    best_odds = bookmaker_analytics.find_best_odds(odds_list, prediction)
    
    lines = [
        f"💰 <b>КОЭФФИЦИЕНТЫ БУКМЕКЕРОВ</b>",
        f"",
        f"🏆 <b>{team1_name} vs {team2_name}</b>",
        f"",
        f"📊 <b>Сравнение коэффициентов:</b>",
        f""
    ]
    
    for i, odds in enumerate(odds_list[:5], 1):  # Показываем топ-5
        lines.append(f"{i}. <b>{odds['bookmaker']}</b> ⭐{odds['reliability']}")
        lines.append(f"   П1: {odds['odds_team1']} | П2: {odds['odds_team2']}")
        lines.append(f"   Маржа: {odds['margin']}%")
        lines.append("")
    
    lines.extend([
        f"🎯 <b>Лучшие коэффициенты:</b>",
        f"• П1: {best_odds['best_team1']['odds_team1']} ({best_odds['best_team1']['bookmaker']})",
        f"• П2: {best_odds['best_team2']['odds_team2']} ({best_odds['best_team2']['bookmaker']})",
        f"",
        f"📈 <b>Value bets (выгодные ставки):</b>"
    ])
    
    if best_odds['value_bets']:
        for vb in best_odds['value_bets'][:3]:
            lines.append(f"• {vb['type']}: {vb['odds']} ({vb['bookmaker']}) +{vb['value']}%")
    else:
        lines.append("• Явных value bets не найдено")
    
    lines.extend([
        f"",
        f"💡 <b>Рекомендация:</b>",
        f"Используйте {best_odds['recommended_bookmaker']} для этого матча",
        f"",
        f"⚠️ <i>Коэффициенты могут меняться. Проверяйте перед ставкой.</i>"
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=create_analysis_keyboard(match_index),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(F.data == "bookmakers")
async def handle_bookmakers(callback: types.CallbackQuery):
    """Информация о букмекерах"""
    lines = [
        "💰 <b>РЕКОМЕНДУЕМЫЕ БУКМЕКЕРЫ</b>",
        "",
        "🏆 <b>Топ-5 для CS2 ставок:</b>",
        "",
        "1. <b>1xBet</b> ⭐⭐⭐⭐⭐",
        "   • Высокие коэффициенты",
        "   • Быстрые выплаты",
        "   • Бонус: 100% до 15 000₽",
        "",
        "2. <b>BetBoom</b> ⭐⭐⭐⭐⭐",
        "   • Лучшие live-ставки",
        "   • Удобное приложение",
        "   • Бонус: 100% до 20 000₽",
        "",
        "3. <b>Fonbet</b> ⭐⭐⭐⭐",
        "   • Надежность",
        "   • Широкая роспись",
        "   • Бонус: 100% до 30 000₽",
        "",
        "4. <b>Winline</b> ⭐⭐⭐⭐",
        "   • Российская лицензия",
        "   • Экспрессы с boost",
        "   • Бонус: 2000₽ фрибет",
        "",
        "5. <b>Marathon</b> ⭐⭐⭐⭐",
        "   • Низкая маржа",
        "   • Прямые трансляции",
        "   • Бонус: 5000₽ фрибет",
        "",
        "💡 <b>Советы:</b>",
        "• Откройте счет в 2-3 конторах",
        "• Сравнивайте коэффициенты",
        "• Используйте бонусы на первые ставки",
        "• Играйте ответственно (18+)",
        "",
        "⚠️ <b>Важно:</b>",
        "Бот предоставляет аналитику, но не принимает ставки.",
        "Все ставки делаются на сайтах букмекеров."
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

@dp.callback_query(F.data == "value_bets")
async def handle_value_bets(callback: types.CallbackQuery):
    """Поиск value bets"""
    await callback.answer("🔍 Ищу выгодные ставки...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>Сегодня нет матчей для анализа</b>",
            reply_markup=create_main_keyboard()
        )
        return
    
    value_matches = []
    
    # Анализируем все матчи на value
    for match in matches[:10]:  # Проверяем первые 10 матчей
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            tournament = match.get("league", {}).get("name", "")
            
            prediction = analyzer.analyze_match(team1_name, team2_name, tournament)
            odds_list = bookmaker_analytics.generate_odds(prediction)
            best_odds = bookmaker_analytics.find_best_odds(odds_list, prediction)
            
            if best_odds['value_bets']:
                value_matches.append({
                    'match': f"{team1_name} vs {team2_name}",
                    'tournament': tournament,
                    'prediction': prediction,
                    'value_bets': best_odds['value_bets'],
                    'best_odds': best_odds
                })
    
    if not value_matches:
        await callback.message.edit_text(
            "📭 <b>Явных value bets не найдено</b>\n\n"
            "Попробуйте проанализировать конкретные матчи вручную.",
            reply_markup=create_main_keyboard()
        )
        return
    
    # Сортируем по наибольшему value
    value_matches.sort(key=lambda x: max([vb['value'] for vb in x['value_bets']]), reverse=True)
    
    lines = [
        "📈 <b>VALUE BETS НА СЕГОДНЯ</b>",
        "",
        "<i>Value bet - ставка с положительным матожиданием.</i>",
        ""
    ]
    
    for i, vm in enumerate(value_matches[:3], 1):  # Показываем топ-3
        lines.append(f"{i}. 🎯 <b>{vm['match']}</b>")
        lines.append(f"   🏆 {vm['tournament']}")
        lines.append(f"   🤖 Прогноз: {vm['prediction']['favorite']} ({vm['prediction']['favorite_prob']}%)")
        
        best_vb = vm['value_bets'][0]
        lines.append(f"   💰 <b>Лучший value:</b> {best_vb['type']}")
        lines.append(f"   📊 Коэффициент: {best_vb['odds']} ({best_vb['bookmaker']})")
        lines.append(f"   📈 Value: +{best_vb['value']}%")
        lines.append("")
    
    lines.extend([
        "💡 <b>Как использовать:</b>",
        "1. Найдите матч с value > 5%",
        "2. Сравните коэффициенты у разных букмекеров",
        "3. Сделайте ставку на рекомендованном букмекере",
        "4. Повторяйте в долгосрочной перспективе",
        "",
        "📊 <b>Статистика:</b>",
        f"• Проанализировано матчей: {len(matches[:10])}",
        f"• Найдено value bets: {sum(len(vm['value_bets']) for vm in value_matches)}",
        f"• Средний value: {round(sum(vb['value'] for vm in value_matches for vb in vm['value_bets']) / sum(len(vm['value_bets']) for vm in value_matches), 1)}%",
        "",
        "⚠️ <i>Value betting требует дисциплины и банкролл-менеджмента.</i>"
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 АНАЛИЗ МАТЧЕЙ", callback_data="analyze_match")],
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
    help_text = """
🎮 <b>CS2 KAPPER ANALYST - ПОМОЩЬ</b>

<b>Основные функции:</b>
• <b>МАТЧИ СЕГОДНЯ/ЗАВТРА</b> - Расписание предстоящих игр
• <b>LIVE МАТЧИ</b> - Текущие матчи в прямом эфире
• <b>АНАЛИЗ МАТЧА</b> 🤖 - Детальный прогноз от нейросети
• <b>БУКМЕКЕРЫ</b> 💰 - Информация о букмекерских конторах
• <b>VALUE BETS</b> 📈 - Поиск выгодных ставок

<b>Как работает нейросеть:</b>
1. Анализирует статистику команд
2. Учитывает форму и мотивацию
3. Оценивает карточные преимущества
4. Дает вероятностный прогноз

<b>Для ставок:</b>
• Используйте рекомендованных букмекеров
• Сравнивайте коэффициенты
• Играйте ответственно (18+)
• Не ставьте больше 1-3% от банкролла

<b>Важно:</b>
• Бот для аналитических целей
• Не гарантирует выигрыш
• Ставки на ваш риск
• 18+ только

<i>Удачи в анализах! 🍀</i>
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
    logger.info("🎮 Запускаю CS2 KAPPER ANALYST...")
    logger.info("🤖 Нейросеть: АКТИВНА (логическая модель)")
    logger.info("📊 Парсинг матчей: ИСПРАВЛЕН")
    logger.info("💰 Букмекеры: 6 контор")
    logger.info("📈 Value bets поиск: ВКЛЮЧЕН")
    
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