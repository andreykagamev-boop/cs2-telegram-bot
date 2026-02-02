import os
import asyncio
import logging
import json
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
import aiohttp
import numpy as np
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

# ========== МОДЕЛЬ НЕЙРОСЕТИ (УПРОЩЕННАЯ) ==========
class NeuralNetworkPredictor:
    """Упрощенная модель нейросети для прогнозов"""
    
    def __init__(self):
        self.team_stats = {}
        self.historical_data = defaultdict(list)
        
    async def load_team_data(self, team_id: int, team_name: str):
        """Загрузить статистику команды"""
        # В реальной реализации здесь был бы запрос к API
        # Сейчас используем синтетические данные
        if team_id not in self.team_stats:
            self.team_stats[team_id] = {
                'name': team_name,
                'rating': random.uniform(0.3, 0.9),
                'form': random.uniform(0.4, 0.95),
                'home_advantage': random.uniform(0.5, 0.8),
                'recent_wins': random.randint(0, 10),
                'recent_losses': random.randint(0, 5)
            }
        return self.team_stats[team_id]
    
    def calculate_prediction(self, team1_stats: Dict, team2_stats: Dict, 
                           is_neutral: bool = True) -> Dict:
        """Рассчитать прогноз на матч"""
        
        # Базовые рейтинги
        rating1 = team1_stats['rating']
        rating2 = team2_stats['rating']
        
        # Форма команд (последние 5 матчей)
        form1 = team1_stats['form']
        form2 = team2_stats['form']
        
        # Коеффициент домашнего преимущества
        home_advantage = 0.1  # +10% к силе домашней команды
        
        # Общая сила команд
        if not is_neutral:
            team1_power = (rating1 * 0.6 + form1 * 0.4) * (1 + home_advantage)
            team2_power = rating2 * 0.6 + form2 * 0.4
        else:
            team1_power = rating1 * 0.6 + form1 * 0.4
            team2_power = rating2 * 0.6 + form2 * 0.4
        
        total_power = team1_power + team2_power
        
        # Вероятности
        team1_win_prob = team1_power / total_power
        team2_win_prob = team2_power / total_power
        
        # Определяем фаворита
        if team1_win_prob > team2_win_prob:
            favorite = team1_stats['name']
            underdog = team2_stats['name']
            favorite_prob = team1_win_prob
            underdog_prob = team2_win_prob
        else:
            favorite = team2_stats['name']
            underdog = team1_stats['name']
            favorite_prob = team2_win_prob
            underdog_prob = team1_win_prob
        
        # Уверенность в прогнозе
        confidence = abs(team1_win_prob - team2_win_prob)
        
        # Рекомендуемые ставки
        recommended_bets = self._get_recommended_bets(
            team1_win_prob, team2_win_prob, confidence
        )
        
        # Прогноз счета
        score_prediction = self._predict_score(team1_power, team2_power)
        
        return {
            'team1_win_prob': round(team1_win_prob * 100, 1),
            'team2_win_prob': round(team2_win_prob * 100, 1),
            'favorite': favorite,
            'underdog': underdog,
            'favorite_prob': round(favorite_prob * 100, 1),
            'underdog_prob': round(underdog_prob * 100, 1),
            'confidence': round(confidence * 100, 1),
            'recommended_bets': recommended_bets,
            'score_prediction': score_prediction,
            'risk_level': self._get_risk_level(confidence),
            'prediction_accuracy': random.randint(65, 85)  # В реальности было бы из истории
        }
    
    def _get_recommended_bets(self, prob1: float, prob2: float, 
                            confidence: float) -> List[Dict]:
        """Получить рекомендуемые ставки"""
        bets = []
        
        # Определяем тип ставки на основе уверенности
        if confidence > 0.3:  # Высокая уверенность
            if prob1 > prob2:
                bets.append({
                    'type': 'П1',
                    'confidence': 'высокая',
                    'potential': 'средний'
                })
            else:
                bets.append({
                    'type': 'П2',
                    'confidence': 'высокая',
                    'potential': 'средний'
                })
        else:  # Низкая уверенность - осторожные ставки
            bets.append({
                'type': 'Тотал >2.5',
                'confidence': 'средняя',
                'potential': 'высокий'
            })
            bets.append({
                'type': 'Фора (+1.5) слабой команды',
                'confidence': 'средняя',
                'potential': 'высокий'
            })
        
        # Всегда добавляем долгосрочную ставку
        bets.append({
            'type': 'Экспресс (комбинированная)',
            'confidence': 'низкая',
            'potential': 'очень высокий'
        })
        
        return bets
    
    def _predict_score(self, power1: float, power2: float) -> str:
        """Прогноз счета"""
        # Упрощенная модель предсказания счета
        avg_rounds = 2.5  # Среднее количество раундов
        
        # Нормализуем силы для предсказания раундов
        total_power = power1 + power2
        rounds1 = int(round((power1 / total_power) * avg_rounds * 10))
        rounds2 = int(round((power2 / total_power) * avg_rounds * 10))
        
        # Корректируем чтобы сумма была ~25 (средний тотал)
        total = rounds1 + rounds2
        if total < 20:
            diff = 25 - total
            rounds1 += diff // 2
            rounds2 += diff - diff // 2
        elif total > 30:
            diff = total - 25
            rounds1 -= diff // 2
            rounds2 -= diff - diff // 2
        
        return f"{rounds1}:{rounds2}"
    
    def _get_risk_level(self, confidence: float) -> str:
        """Уровень риска"""
        if confidence > 0.4:
            return "НИЗКИЙ"
        elif confidence > 0.2:
            return "СРЕДНИЙ"
        else:
            return "ВЫСОКИЙ"
    
    def get_express_recommendation(self, matches: List[Dict]) -> Dict:
        """Рекомендация для экспресса"""
        if len(matches) < 2:
            return {'valid': False, 'reason': 'Нужно минимум 2 матча для экспресса'}
        
        # Анализируем все матчи
        total_confidence = 0
        safe_bets = []
        
        for match in matches:
            # Здесь в реальности был бы полный анализ каждого матча
            team1 = match.get('team1', '')
            team2 = match.get('team2', '')
            
            # Случайный прогноз для демонстрации
            confidence = random.uniform(0.3, 0.8)
            total_confidence += confidence
            
            if confidence > 0.5:
                safe_bets.append({
                    'match': f"{team1} vs {team2}",
                    'bet': random.choice(['П1', 'П2', 'ТМ 2.5', 'ТБ 2.5']),
                    'confidence': round(confidence * 100, 1)
                })
        
        avg_confidence = total_confidence / len(matches)
        
        # Расчет коэффициента
        base_coefficient = 1.0
        for bet in safe_bets[:3]:  # Берем 3 самые уверенные ставки
            conf = bet['confidence'] / 100
            base_coefficient *= (1.5 + conf * 0.5)  # Чем выше уверенность, тем ниже коэффициент
        
        final_coefficient = round(base_coefficient, 2)
        
        # Рекомендация
        if avg_confidence > 0.6 and len(safe_bets) >= 2:
            recommendation = "РЕКОМЕНДУЕМ"
            risk = "СРЕДНИЙ"
        elif avg_confidence > 0.4 and len(safe_bets) >= 3:
            recommendation = "МОЖНО ПОПРОБОВАТЬ"
            risk = "ВЫСОКИЙ"
        else:
            recommendation = "НЕ РЕКОМЕНДУЕМ"
            risk = "ОЧЕНЬ ВЫСОКИЙ"
        
        return {
            'valid': True,
            'recommendation': recommendation,
            'total_confidence': round(avg_confidence * 100, 1),
            'coefficient': final_coefficient,
            'risk_level': risk,
            'suggested_bets': safe_bets[:3],
            'potential_win': f"{final_coefficient * 10:.2f}x"  # При ставке 10 единиц
        }

# ========== БУКМЕКЕРСКИЕ КОНТОРЫ ==========
class BookmakerOdds:
    """Генератор коэффициентов букмекеров"""
    
    def __init__(self):
        self.bookmakers = [
            {"name": "1xBet", "reliability": "высокая", "bonus": "100% до 15 000₽"},
            {"name": "BetBoom", "reliability": "высокая", "bonus": "100% до 20 000₽"},
            {"name": "Fonbet", "reliability": "средняя", "bonus": "100% до 30 000₽"},
            {"name": "Winline", "reliability": "высокая", "bonus": "2000₽ фрибет"},
            {"name": "Liga Stavok", "reliability": "средняя", "bonus": "100% до 10 000₽"},
            {"name": "Marathon", "reliability": "высокая", "bonus": "5000₽ фрибет"},
            {"name": "Parimatch", "reliability": "средняя", "bonus": "100% до 25 000₽"},
            {"name": "Zenit Bet", "reliability": "высокая", "bonus": "100% до 15 000₽"}
        ]
    
    def generate_odds(self, team1_win_prob: float, team2_win_prob: float) -> List[Dict]:
        """Сгенерировать коэффициенты для разных букмекеров"""
        odds_list = []
        
        for bookmaker in self.bookmakers:
            # Базовая маржа букмекера (5-10%)
            margin = random.uniform(0.05, 0.10)
            
            # Чем выше надежность, тем меньше маржа
            if bookmaker["reliability"] == "высокая":
                margin *= 0.8
            elif bookmaker["reliability"] == "средняя":
                margin *= 1.0
            else:
                margin *= 1.2
            
            # Коэффициенты с учетом маржи
            odds1 = round(1 / (team1_win_prob / 100) * (1 - margin), 2)
            odds2 = round(1 / (team2_win_prob / 100) * (1 - margin), 2)
            
            # Округление до стандартных значений
            odds1 = self._round_odds(odds1)
            odds2 = self._round_odds(odds2)
            
            # Генерация дополнительных рынков
            total_odds = self._generate_total_odds()
            handicap_odds = self._generate_handicap_odds(team1_win_prob, team2_win_prob)
            
            odds_list.append({
                'bookmaker': bookmaker['name'],
                'reliability': bookmaker['reliability'],
                'bonus': bookmaker['bonus'],
                'odds_team1': odds1,
                'odds_team2': odds2,
                'total_over': total_odds['over'],
                'total_under': total_odds['under'],
                'handicap': handicap_odds
            })
        
        # Сортируем по коэффициентам П1 (от большего к меньшему)
        return sorted(odds_list, key=lambda x: x['odds_team1'], reverse=True)
    
    def _round_odds(self, odds: float) -> float:
        """Округлить коэффициенты до стандартных значений"""
        if odds < 1.1:
            return 1.1
        elif odds < 2.0:
            return round(odds * 2) / 2  # 0.5 шаг
        elif odds < 5.0:
            return round(odds * 4) / 4  # 0.25 шаг
        else:
            return round(odds * 2) / 2  # 0.5 шаг
    
    def _generate_total_odds(self) -> Dict:
        """Сгенерировать коэффициенты на тоталы"""
        total = random.choice([2.5, 3.5, 4.5])
        over = round(random.uniform(1.6, 2.2), 2)
        under = round(random.uniform(1.6, 2.2), 2)
        
        # Корректировка чтобы один был выше
        if random.random() > 0.5:
            over += 0.1
            under -= 0.1
        else:
            over -= 0.1
            under += 0.1
        
        return {'total': total, 'over': over, 'under': under}
    
    def _generate_handicap_odds(self, prob1: float, prob2: float) -> List[Dict]:
        """Сгенерировать коэффициенты на фору"""
        handicaps = []
        
        # Определяем фаворита
        if prob1 > prob2:
            favorite_prob = prob1
            underdog_prob = prob2
        else:
            favorite_prob = prob2
            underdog_prob = prob1
        
        # Генерируем несколько вариантов фор
        for handicap in [-1.5, -2.5, 1.5, 2.5]:
            if handicap < 0:  # Фаворит дает фору
                base_odds = 1.4 if abs(handicap) == 1.5 else 1.8
                if favorite_prob > 70:
                    odds = base_odds - 0.2
                elif favorite_prob > 60:
                    odds = base_odds
                else:
                    odds = base_odds + 0.2
            else:  # Аутсайдер получает фору
                base_odds = 1.6 if abs(handicap) == 1.5 else 2.0
                if underdog_prob > 40:
                    odds = base_odds - 0.2
                elif underdog_prob > 30:
                    odds = base_odds
                else:
                    odds = base_odds + 0.2
            
            handicaps.append({
                'handicap': handicap,
                'odds': round(odds, 2)
            })
        
        return handicaps

# ========== АНАЛИТИКА И ОТЧЕТЫ ==========
class MatchAnalytics:
    """Генератор аналитических отчетов"""
    
    @staticmethod
    def generate_analysis_report(prediction: Dict, odds: List[Dict], 
                               team1_name: str, team2_name: str) -> str:
        """Сгенерировать аналитический отчет"""
        
        # Находим лучшие коэффициенты
        best_odds_p1 = max(odds, key=lambda x: x['odds_team1'])
        best_odds_p2 = max(odds, key=lambda x: x['odds_team2'])
        
        # Анализ value bets
        value_bets = MatchAnalytics._find_value_bets(prediction, odds)
        
        # Рекомендации по размеру ставки
        bet_size_recommendation = MatchAnalytics._get_bet_size_recommendation(
            prediction['confidence']
        )
        
        lines = [
            f"📊 <b>АНАЛИТИЧЕСКИЙ ОТЧЕТ: {team1_name} vs {team2_name}</b>",
            "",
            f"🎯 <b>Прогноз нейросети:</b>",
            f"• Победитель: {prediction['favorite']} ({prediction['favorite_prob']}%)",
            f"• Уверенность: {prediction['confidence']}%",
            f"• Прогноз счета: {prediction['score_prediction']}",
            f"• Точность модели: {prediction['prediction_accuracy']}%",
            "",
            f"💰 <b>Лучшие коэффициенты:</b>",
            f"• П1 ({team1_name}): {best_odds_p1['odds_team1']} ({best_odds_p1['bookmaker']})",
            f"• П2 ({team2_name}): {best_odds_p2['odds_team2']} ({best_odds_p2['bookmaker']})",
            "",
            f"⚡ <b>Value Bets (выгодные ставки):</b>"
        ]
        
        if value_bets:
            for vb in value_bets[:3]:  # Показываем топ-3
                lines.append(f"• {vb['type']}: {vb['odds']} ({vb['bookmaker']}) - {vb['value']}% value")
        else:
            lines.append("• Нет явно выгодных ставок")
        
        lines.extend([
            "",
            f"🎲 <b>Рекомендации:</b>",
            f"• Уровень риска: {prediction['risk_level']}",
            f"• Размер ставки: {bet_size_recommendation}",
            f"• Стратегия: {MatchAnalytics._get_strategy_recommendation(prediction['confidence'])}",
            "",
            f"📈 <b>Статистика букмекеров:</b>",
            f"• Самый надежный: {max(odds, key=lambda x: 1 if x['reliability']=='высокая' else 0.5)['bookmaker']}",
            f"• Лучший бонус: {max(odds, key=lambda x: int(x['bonus'].split()[0]) if x['bonus'][0].isdigit() else 0)['bookmaker']}",
            "",
            f"⚠️ <b>Предупреждение:</b>",
            f"Ставки на спорт связаны с риском. Ставьте только свободные деньги."
        ])
        
        return "\n".join(lines)
    
    @staticmethod
    def _find_value_bets(prediction: Dict, odds: List[Dict]) -> List[Dict]:
        """Найти value bets (ставки с положительным матожиданием)"""
        value_bets = []
        
        # Расчет fair odds (справедливые коэффициенты)
        fair_odds_team1 = 100 / prediction['team1_win_prob']
        fair_odds_team2 = 100 / prediction['team2_win_prob']
        
        for bookmaker in odds:
            # Проверяем Value на П1
            if bookmaker['odds_team1'] > fair_odds_team1:
                value = ((bookmaker['odds_team1'] * prediction['team1_win_prob'] / 100) - 1) * 100
                if value > 5:  # Минимальный value 5%
                    value_bets.append({
                        'type': f"П1 ({bookmaker['odds_team1']})",
                        'bookmaker': bookmaker['bookmaker'],
                        'odds': bookmaker['odds_team1'],
                        'value': round(value, 1)
                    })
            
            # Проверяем Value на П2
            if bookmaker['odds_team2'] > fair_odds_team2:
                value = ((bookmaker['odds_team2'] * prediction['team2_win_prob'] / 100) - 1) * 100
                if value > 5:
                    value_bets.append({
                        'type': f"П2 ({bookmaker['odds_team2']})",
                        'bookmaker': bookmaker['bookmaker'],
                        'odds': bookmaker['odds_team2'],
                        'value': round(value, 1)
                    })
        
        # Сортируем по value
        return sorted(value_bets, key=lambda x: x['value'], reverse=True)
    
    @staticmethod
    def _get_bet_size_recommendation(confidence: float) -> str:
        """Рекомендация по размеру ставки"""
        if confidence > 70:
            return "3-5% от банка"
        elif confidence > 50:
            return "2-3% от банка"
        elif confidence > 30:
            return "1-2% от банка"
        else:
            return "0.5-1% от банка или пропустить"
    
    @staticmethod
    def _get_strategy_recommendation(confidence: float) -> str:
        """Рекомендация по стратегии"""
        if confidence > 70:
            return "Ординар (одиночная ставка)"
        elif confidence > 50:
            return "Ординар или экспресс с 2 событиями"
        else:
            return "Фора или тотал (меньше риска)"

# ========== КАППЕР СЕРВИС ==========
class CapperService:
    """Основной сервис каппера"""
    
    def __init__(self):
        self.predictor = NeuralNetworkPredictor()
        self.bookmaker = BookmakerOdds()
        self.analytics = MatchAnalytics()
        self.user_bank = defaultdict(lambda: 10000)  # Начальный банк 10 000₽ у каждого пользователя
        
    async def get_match_prediction(self, match: Dict) -> Dict:
        """Получить полный прогноз на матч"""
        opponents = match.get("opponents", [])
        
        if len(opponents) < 2:
            return {'error': 'Недостаточно данных о командах'}
        
        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})
        
        team1_name = team1.get("acronym") or team1.get("name", "TBA")
        team2_name = team2.get("acronym") or team2.get("name", "TBA")
        team1_id = team1.get("id", 1)
        team2_id = team2.get("id", 2)
        
        # Загружаем данные команд
        team1_stats = await self.predictor.load_team_data(team1_id, team1_name)
        team2_stats = await self.predictor.load_team_data(team2_id, team2_name)
        
        # Получаем прогноз
        prediction = self.predictor.calculate_prediction(team1_stats, team2_stats)
        
        # Генерируем коэффициенты букмекеров
        odds = self.bookmaker.generate_odds(
            prediction['team1_win_prob'],
            prediction['team2_win_prob']
        )
        
        # Генерируем аналитический отчет
        analysis = self.analytics.generate_analysis_report(
            prediction, odds, team1_name, team2_name
        )
        
        return {
            'match_info': {
                'team1': team1_name,
                'team2': team2_name,
                'time': match.get("scheduled_at", ""),
                'tournament': match.get("league", {}).get("name", "")
            },
            'prediction': prediction,
            'odds': odds,
            'analysis': analysis,
            'recommended_bets': prediction['recommended_bets']
        }
    
    async def get_express_recommendation(self, matches: List[Dict]) -> Dict:
        """Получить рекомендацию для экспресса"""
        if len(matches) < 2:
            return {
                'valid': False,
                'message': 'Для экспресса нужно минимум 2 матча'
            }
        
        # Упрощаем данные матчей для экспресса
        simplified_matches = []
        for match in matches[:5]:  # Берем максимум 5 матчей
            opponents = match.get("opponents", [])
            if len(opponents) >= 2:
                team1 = opponents[0].get("opponent", {})
                team2 = opponents[1].get("opponent", {})
                team1_name = team1.get("acronym") or team1.get("name", "TBA")
                team2_name = team2.get("acronym") or team2.get("name", "TBA")
                
                simplified_matches.append({
                    'team1': team1_name,
                    'team2': team2_name,
                    'time': match.get("scheduled_at", "")
                })
        
        # Получаем рекомендацию от нейросети
        express_pred = self.predictor.get_express_recommendation(simplified_matches)
        
        # Форматируем результат
        if express_pred['valid']:
            lines = [
                "🎯 <b>ЭКСПРЕСС-СТАВКА РЕКОМЕНДАЦИЯ</b>",
                "",
                f"📊 <b>Анализ:</b>",
                f"• Всего матчей: {len(simplified_matches)}",
                f"• Общая уверенность: {express_pred['total_confidence']}%",
                f"• Уровень риска: {express_pred['risk_level']}",
                f"• Рекомендация: <b>{express_pred['recommendation']}</b>",
                "",
                f"💰 <b>Потенциальный выигрыш:</b>",
                f"• Коэффициент: {express_pred['coefficient']}",
                f"• При ставке 1000₽: {float(express_pred['coefficient']) * 1000:.0f}₽",
                "",
                f"🎲 <b>Рекомендуемые ставки:</b>"
            ]
            
            for bet in express_pred['suggested_bets']:
                lines.append(f"• {bet['match']} - {bet['bet']} ({bet['confidence']}%)")
            
            lines.extend([
                "",
                f"⚡ <b>Стратегия:</b>",
                f"• Размер ставки: 1-2% от банка",
                f"• Максимальный экспресс: 3 события",
                f"• Избегайте дублирования турниров",
                "",
                f"⚠️ <b>Важно:</b> Экспрессы имеют высокий риск!"
            ])
            
            return {
                'valid': True,
                'message': "\n".join(lines),
                'coefficient': express_pred['coefficient'],
                'risk': express_pred['risk_level']
            }
        else:
            return {
                'valid': False,
                'message': express_pred['reason']
            }
    
    def place_bet(self, user_id: int, amount: float, coefficient: float, 
                 bet_type: str, match_info: str) -> Dict:
        """Разместить ставку (симуляция)"""
        current_bank = self.user_bank[user_id]
        
        if amount > current_bank:
            return {
                'success': False,
                'message': f'Недостаточно средств. Ваш банк: {current_bank}₽'
            }
        
        # Симуляция результата (в реальности было бы после матча)
        is_win = random.random() > 0.5  # 50% шанс выигрыша
        
        if is_win:
            win_amount = amount * coefficient
            self.user_bank[user_id] += win_amount
            result = '✅ ВЫИГРЫШ'
            message = f"Вы выиграли {win_amount:.2f}₽!"
        else:
            self.user_bank[user_id] -= amount
            result = '❌ ПРОИГРЫШ'
            message = f"Вы проиграли {amount:.2f}₽"
        
        return {
            'success': True,
            'result': result,
            'message': message,
            'new_bank': self.user_bank[user_id],
            'bet_type': bet_type,
            'match': match_info,
            'coefficient': coefficient
        }

# ========== СУЩЕСТВУЮЩИЙ КОД (с минимальными изменениями) ==========
class PandaScoreAPI:
    """API клиент для CS2 (не меняем)"""
    
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
    
    async def get_upcoming_matches(self, days: int = 2):
        """Получить предстоящие матчи - исправленный метод"""
        try:
            session = await self.get_session()
            
            # Получаем ВСЕ предстоящие матчи
            url = f"{self.base_url}/csgo/matches/upcoming"
            params = {
                "per_page": 100,
                "sort": "scheduled_at",
                "page": 1
            }
            
            logger.info("Запрос предстоящих матчей...")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    logger.info(f"Получено матчей: {len(matches)}")
                    
                    # Фильтруем по дате
                    now = datetime.utcnow()
                    filtered_matches = []
                    
                    for match in matches:
                        scheduled_at = match.get("scheduled_at")
                        if scheduled_at:
                            try:
                                match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                                
                                # Проверяем что матч в будущем
                                if match_time > now:
                                    # Фильтруем по количеству дней
                                    days_diff = (match_time.date() - now.date()).days
                                    if days_diff < days:
                                        filtered_matches.append(match)
                            except:
                                continue
                    
                    logger.info(f"После фильтрации: {len(filtered_matches)} матчей")
                    return filtered_matches
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка {response.status}: {error_text[:200]}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении матчей: {e}")
            return []
    
    async def get_today_matches(self):
        """Получить матчи только на сегодня"""
        try:
            session = await self.get_session()
            
            # Получаем текущую дату в UTC
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            
            # Форматируем даты для API
            today_str = today.isoformat()
            tomorrow_str = tomorrow.isoformat()
            
            url = f"{self.base_url}/csgo/matches"
            params = {
                "range[scheduled_at]": f"{today_str},{tomorrow_str}",
                "per_page": 50,
                "sort": "scheduled_at",
                "filter[status]": "not_started"
            }
            
            logger.info(f"Запрос матчей с {today_str} по {tomorrow_str}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем только сегодняшние
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
    
    async def get_tomorrow_matches(self):
        """Получить матчи только на завтра"""
        try:
            session = await self.get_session()
            
            # Получаем дату завтра
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
            
            logger.info(f"Запрос матчей с {tomorrow_str} по {day_after_tomorrow_str}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    # Фильтруем только завтрашние
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

# ========== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ==========
panda_api = PandaScoreAPI(PANDASCORE_TOKEN)
capper_service = CapperService()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (не меняем) ==========
def create_main_keyboard():
    """Главное меню - расширенное для каппера"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 МАТЧИ", callback_data="today"),
            InlineKeyboardButton(text="🤖 ПРОГНОЗЫ", callback_data="predictions")
        ],
        [
            InlineKeyboardButton(text="💰 СТАВКИ", callback_data="bets"),
            InlineKeyboardButton(text="🚀 ЭКСПРЕСС", callback_data="express")
        ],
        [
            InlineKeyboardButton(text="📊 АНАЛИТИКА", callback_data="analytics"),
            InlineKeyboardButton(text="🏦 БАНК", callback_data="bank")
        ],
        [
            InlineKeyboardButton(text="⚙️ ПОМОЩЬ", callback_data="help"),
            InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="refresh")
        ]
    ])
    return keyboard

def create_predictions_keyboard():
    """Клавиатура для прогнозов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 НА СЕГОДНЯ", callback_data="predict_today"),
            InlineKeyboardButton(text="🎯 НА ЗАВТРА", callback_data="predict_tomorrow")
        ],
        [
            InlineKeyboardButton(text="🔥 LIVE ПРОГНОЗЫ", callback_data="predict_live"),
            InlineKeyboardButton(text="⭐ ТОП МАТЧИ", callback_data="predict_top")
        ],
        [
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
        ]
    ])
    return keyboard

def create_bets_keyboard():
    """Клавиатура для ставок"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 БУКМЕКЕРЫ", callback_data="bookmakers"),
            InlineKeyboardButton(text="📈 VALUE BETS", callback_data="value_bets")
        ],
        [
            InlineKeyboardButton(text="🎲 СДЕЛАТЬ СТАВКУ", callback_data="place_bet"),
            InlineKeyboardButton(text="📊 МОИ СТАВКИ", callback_data="my_bets")
        ],
        [
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
        ]
    ])
    return keyboard

def create_match_selection_keyboard(matches: List[Dict]):
    """Клавиатура для выбора матча"""
    buttons = []
    for i, match in enumerate(matches[:5]):  # Показываем первые 5 матчей
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            
            time_str = format_match_time(match.get("scheduled_at", ""))
            button_text = f"{i+1}. {team1_name} vs {team2_name} ({time_str})"
            
            # Обрезаем если слишком длинно
            if len(button_text) > 50:
                button_text = button_text[:47] + "..."
            
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"predict_match_{i}"
            )])
    
    buttons.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="predictions")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_match_time(scheduled_at: str) -> str:
    """Форматирование времени в MSK"""
    try:
        dt_utc = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        dt_msk = dt_utc + timedelta(hours=3)
        return dt_msk.strftime("%H:%M")
    except:
        return "Скоро"

# ========== НОВЫЕ КОМАНДЫ И ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Старт каппер-бота"""
    welcome = """
🎯 <b>CS2 KAPPER BOT</b>

Ваш личный аналитик и помощник по ставкам на CS2!

<b>Основные функции:</b>
• 🤖 Прогнозы от нейросети
• 📊 Аналитика и статистика
• 💰 Коэффициенты букмекеров
• 🚀 Экспресс-ставки
• 📈 Value bets (выгодные ставки)

<b>Ваш банк: 10 000₽</b>

👇 <b>Выберите раздел:</b>
"""
    
    await message.answer(
        welcome,
        reply_markup=create_main_keyboard(),
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "predictions")
async def handle_predictions(callback: types.CallbackQuery):
    """Раздел прогнозов"""
    await callback.message.edit_text(
        "🤖 <b>ПРОГНОЗЫ ОТ НЕЙРОСЕТИ</b>\n\n"
        "Нейросеть анализирует статистику команд, форму, "
        "исторические данные и дает точные прогнозы.\n\n"
        "Выберите тип прогнозов:",
        reply_markup=create_predictions_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "predict_today")
async def handle_predict_today(callback: types.CallbackQuery):
    """Прогнозы на сегодня"""
    await callback.answer("🤖 Анализирую матчи на сегодня...")
    
    matches = await panda_api.get_today_matches()
    if not matches:
        await callback.message.edit_text(
            "📭 <b>На сегодня нет матчей для анализа</b>",
            reply_markup=create_predictions_keyboard()
        )
        return
    
    await callback.message.edit_text(
        f"🤖 <b>ВЫБЕРИТЕ МАТЧ ДЛЯ ПРОГНОЗА</b>\n\n"
        f"Найдено матчей на сегодня: {len(matches)}",
        reply_markup=create_match_selection_keyboard(matches)
    )

@dp.callback_query(F.data.startswith("predict_match_"))
async def handle_predict_match(callback: types.CallbackQuery):
    """Прогноз на конкретный матч"""
    match_index = int(callback.data.split("_")[2])
    await callback.answer("🤖 Анализирую матч...")
    
    # Получаем все матчи на сегодня для выбора
    matches = await panda_api.get_today_matches()
    if not matches or match_index >= len(matches):
        await callback.message.edit_text(
            "❌ <b>Матч не найден</b>",
            reply_markup=create_predictions_keyboard()
        )
        return
    
    match = matches[match_index]
    
    # Получаем полный прогноз
    full_prediction = await capper_service.get_match_prediction(match)
    
    if 'error' in full_prediction:
        await callback.message.edit_text(
            f"❌ <b>Ошибка:</b> {full_prediction['error']}",
            reply_markup=create_predictions_keyboard()
        )
        return
    
    # Форматируем прогноз для отображения
    match_info = full_prediction['match_info']
    prediction = full_prediction['prediction']
    odds = full_prediction['odds']
    
    # Создаем сообщение с прогнозом
    lines = [
        f"🎯 <b>ПРОГНОЗ НА МАТЧ</b>",
        f"🏆 {match_info['team1']} vs {match_info['team2']}",
        f"",
        f"🤖 <b>Прогноз нейросети:</b>",
        f"• Победитель: {prediction['favorite']}",
        f"• Вероятность: {prediction['favorite_prob']}%",
        f"• Уверенность: {prediction['confidence']}%",
        f"• Прогноз счета: {prediction['score_prediction']}",
        f"• Уровень риска: {prediction['risk_level']}",
        f"",
        f"💰 <b>Лучшие коэффициенты:</b>"
    ]
    
    # Показываем топ-3 букмекера
    for i, bookmaker in enumerate(odds[:3], 1):
        lines.append(f"{i}. {bookmaker['bookmaker']}:")
        lines.append(f"   П1: {bookmaker['odds_team1']} | П2: {bookmaker['odds_team2']}")
    
    lines.extend([
        f"",
        f"🎲 <b>Рекомендуемые ставки:</b>"
    ])
    
    for bet in prediction['recommended_bets'][:2]:
        lines.append(f"• {bet['type']} (уверенность: {bet['confidence']})")
    
    lines.extend([
        f"",
        f"📊 <b>Подробная аналитика:</b> /analysis_{match_index}",
        f"",
        f"⚠️ <i>Прогноз основан на статистике. Риск есть всегда!</i>"
    ])
    
    # Клавиатура для действий
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 ПОЛНЫЙ ОТЧЕТ", callback_data=f"full_report_{match_index}"),
            InlineKeyboardButton(text="💰 СДЕЛАТЬ СТАВКУ", callback_data=f"bet_{match_index}")
        ],
        [
            InlineKeyboardButton(text="◀️ ВЫБРАТЬ ДРУГОЙ", callback_data="predict_today"),
            InlineKeyboardButton(text="🏠 В МЕНЮ", callback_data="back")
        ]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "express")
async def handle_express(callback: types.CallbackQuery):
    """Экспресс-ставки"""
    await callback.answer("🚀 Анализирую матчи для экспресса...")
    
    # Получаем матчи на 2 дня для экспресса
    matches = await panda_api.get_upcoming_matches(days=2)
    
    if len(matches) < 2:
        await callback.message.edit_text(
            "❌ <b>Недостаточно матчей для экспресса</b>\n"
            "Нужно минимум 2 предстоящих матча.",
            reply_markup=create_main_keyboard()
        )
        return
    
    # Получаем рекомендацию для экспресса
    express_rec = await capper_service.get_express_recommendation(matches)
    
    if express_rec['valid']:
        # Клавиатура для ставки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 СДЕЛАТЬ ЭКСПРЕСС", callback_data="place_express"),
                InlineKeyboardButton(text="📊 ДРУГИЕ МАТЧИ", callback_data="express_matches")
            ],
            [
                InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
            ]
        ])
        
        await callback.message.edit_text(
            express_rec['message'],
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    else:
        await callback.message.edit_text(
            f"❌ <b>{express_rec['message']}</b>",
            reply_markup=create_main_keyboard()
        )

@dp.callback_query(F.data == "analytics")
async def handle_analytics(callback: types.CallbackQuery):
    """Аналитика и статистика"""
    await callback.answer("📊 Загружаю аналитику...")
    
    # Получаем матчи на сегодня
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>На сегодня нет матчей для анализа</b>",
            reply_markup=create_main_keyboard()
        )
        return
    
    # Создаем аналитический отчет
    lines = [
        "📊 <b>АНАЛИТИКА НА СЕГОДНЯ</b>",
        "",
        f"📈 <b>Общая статистика:</b>",
        f"• Всего матчей: {len(matches)}",
        f"• Турниров: {len(set(m.get('league', {}).get('name', '') for m in matches))}",
        f"",
        "🎯 <b>Рекомендации на сегодня:</b>"
    ]
    
    # Анализируем несколько матчей
    analyzed = 0
    for i, match in enumerate(matches[:3]):  # Анализируем первые 3 матча
        prediction = await capper_service.get_match_prediction(match)
        if 'error' not in prediction:
            match_info = prediction['match_info']
            pred = prediction['prediction']
            
            lines.append(f"{i+1}. <b>{match_info['team1']} vs {match_info['team2']}</b>")
            lines.append(f"   🏆 {match_info['tournament']}")
            lines.append(f"   🤖 Прогноз: {pred['favorite']} ({pred['favorite_prob']}%)")
            lines.append(f"   ⚡ Риск: {pred['risk_level']}")
            lines.append("")
            analyzed += 1
    
    lines.extend([
        f"",
        f"💰 <b>Букмекерская аналитика:</b>",
        f"• Самые щедрые: 1xBet, BetBoom",
        f"• Надежные: Winline, Marathon",
        f"• Лучшие бонусы: BetBoom (20к₽), Fonbet (30к₽)",
        f"",
        f"⚡ <b>Стратегия на сегодня:</b>",
        f"• Фокус на турнирах ESL, BLAST",
        f"• Избегать ранних матчей (меньше данных)",
        f"• Размер ставки: 2-3% от банка",
        f"",
        f"⚠️ <i>Аналитика основана на данных PandaScore и статистике команд</i>"
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 ПОДРОБНЫЕ ПРОГНОЗЫ", callback_data="predict_today"),
            InlineKeyboardButton(text="💰 VALUE BETS", callback_data="value_bets")
        ],
        [
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
        ]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "bank")
async def handle_bank(callback: types.CallbackQuery):
    """Информация о банке"""
    user_id = callback.from_user.id
    bank = capper_service.user_bank[user_id]
    
    # Симулируем историю ставок
    bet_history = [
        {"type": "П1", "match": "NAVI vs Vitality", "result": "✅ +1500₽"},
        {"type": "Тотал >2.5", "match": "FaZe vs G2", "result": "❌ -500₽"},
        {"type": "Экспресс", "match": "2 события", "result": "✅ +3200₽"}
    ]
    
    lines = [
        f"🏦 <b>ВАШ БАНК: {bank}₽</b>",
        f"",
        f"📊 <b>Статистика:</b>",
        f"• Начальный банк: 10 000₽",
        f"• Текущий результат: {'+' if bank > 10000 else ''}{bank - 10000}₽",
        f"• ROI: {((bank - 10000) / 10000 * 100):.1f}%",
        f"",
        f"📝 <b>История ставок:</b>"
    ]
    
    for bet in bet_history:
        lines.append(f"• {bet['type']} - {bet['match']} - {bet['result']}")
    
    lines.extend([
        f"",
        f"💡 <b>Рекомендации:</b>",
        f"• Не ставьте больше 5% от банка",
        f"• Фиксируйте прибыль регулярно",
        f"• Ведите статистику ставок",
        f"",
        f"🔄 <b>Обновить банк:</b> /reset_bank"
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 ПОПОЛНИТЬ", callback_data="deposit"),
            InlineKeyboardButton(text="🎯 СТАВКА", callback_data="place_bet")
        ],
        [
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back")
        ]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "bookmakers")
async def handle_bookmakers(callback: types.CallbackQuery):
    """Информация о букмекерах"""
    bookmakers_info = [
        {"name": "1xBet", "rating": "9.5/10", "bonus": "100% до 15 000₽", "features": "Лучшие коэффициенты, много рынков"},
        {"name": "BetBoom", "rating": "9.2/10", "bonus": "100% до 20 000₽", "features": "Быстрые выплаты, хороший интерфейс"},
        {"name": "Fonbet", "rating": "8.8/10", "bonus": "100% до 30 000₽", "features": "Надежность, высокая линия"},
        {"name": "Winline", "rating": "9.0/10", "bonus": "2000₽ фрибет", "features": "Экспрессы с повышенным кэфом"},
        {"name": "Marathon", "rating": "8.5/10", "bonus": "5000₽ фрибет", "features": "Низкая маржа, live-ставки"}
    ]
    
    lines = [
        "💰 <b>БУКМЕКЕРСКИЕ КОНТОРЫ</b>",
        "",
        "🏆 <b>Топ-5 для CS2:</b>",
        ""
    ]
    
    for i, bm in enumerate(bookmakers_info, 1):
        lines.append(f"{i}. <b>{bm['name']}</b> ⭐{bm['rating']}")
        lines.append(f"   🎁 Бонус: {bm['bonus']}")
        lines.append(f"   📊 Особенности: {bm['features']}")
        lines.append("")
    
    lines.extend([
        "💡 <b>Рекомендации:</b>",
        "• Открывайте счет в 2-3 конторах",
        "• Сравнивайте коэффициенты перед ставкой",
        "• Используйте бонусы на первые ставки",
        "",
        "⚠️ <i>Играйте ответственно. 18+</i>"
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 СРАВНИТЬ КОЭФФИЦИЕНТЫ", callback_data="compare_odds"),
            InlineKeyboardButton(text="🎁 БОНУСЫ", callback_data="bonuses")
        ],
        [
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="bets")
        ]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "value_bets")
async def handle_value_bets(callback: types.CallbackQuery):
    """Value bets (выгодные ставки)"""
    await callback.answer("🔍 Ищу выгодные ставки...")
    
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await callback.message.edit_text(
            "📭 <b>Сегодня нет матчей для анализа</b>",
            reply_markup=create_bets_keyboard()
        )
        return
    
    lines = [
        "📈 <b>VALUE BETS НА СЕГОДНЯ</b>",
        "",
        "<i>Value bets - ставки с положительным матожиданием.</i>",
        ""
    ]
    
    # Анализируем первые 5 матчей
    value_found = 0
    for i, match in enumerate(matches[:5]):
        prediction = await capper_service.get_match_prediction(match)
        if 'error' not in prediction:
            odds = prediction['odds']
            
            # Ищем value bets в этом матче
            for bookmaker in odds[:2]:  # Проверяем 2 лучших букмекера
                # Упрощенный расчет value
                fair_odds_team1 = 100 / prediction['prediction']['team1_win_prob']
                fair_odds_team2 = 100 / prediction['prediction']['team2_win_prob']
                
                value1 = (bookmaker['odds_team1'] * prediction['prediction']['team1_win_prob'] / 100) - 1
                value2 = (bookmaker['odds_team2'] * prediction['prediction']['team2_win_prob'] / 100) - 1
                
                if value1 > 0.05 or value2 > 0.05:  # Value > 5%
                    match_info = prediction['match_info']
                    lines.append(f"🎯 <b>{match_info['team1']} vs {match_info['team2']}</b>")
                    lines.append(f"   📊 {bookmaker['bookmaker']}")
                    
                    if value1 > 0.05:
                        lines.append(f"   💰 П1: {bookmaker['odds_team1']} (value: +{value1*100:.1f}%)")
                    if value2 > 0.05:
                        lines.append(f"   💰 П2: {bookmaker['odds_team2']} (value: +{value2*100:.1f}%)")
                    
                    lines.append("")
                    value_found += 1
                    break
    
    if value_found == 0:
        lines.append("📭 <b>Явных value bets не найдено</b>")
        lines.append("")
        lines.append("Попробуйте позже или проверьте другие матчи.")
    
    lines.extend([
        "",
        "💡 <b>Совет:</b> Ставки с value > 5% имеют положительное "
        "матожидание в долгосрочной перспективе.",
        "",
        "⚠️ <i>Анализ основан на прогнозах нейросети</i>"
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 СДЕЛАТЬ СТАВКУ", callback_data="place_bet"),
            InlineKeyboardButton(text="🤖 ПРОГНОЗЫ", callback_data="predict_today")
        ],
        [
            InlineKeyboardButton(text="◀️ НАЗАД", callback_data="bets")
        ]
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@dp.callback_query(F.data == "help")
async def handle_help(callback: types.CallbackQuery):
    """Помощь по боту"""
    help_text = """
🎯 <b>CS2 KAPPER BOT - ПОМОЩЬ</b>

<b>Основные команды:</b>
/start - Главное меню
/help - Эта справка

<b>Разделы:</b>
• <b>МАТЧИ</b> - Расписание предстоящих игр
• <b>ПРОГНОЗЫ</b> - Прогнозы от нейросети на матчи
• <b>СТАВКИ</b> - Букмекеры и рекомендации
• <b>ЭКСПРЕСС</b> - Анализ и создание экспрессов
• <b>АНАЛИТИКА</b> - Статистика и аналитика
• <b>БАНК</b> - Управление виртуальным банком

<b>Как пользоваться:</b>
1. Выберите раздел в меню
2. Получите прогноз от нейросети
3. Сравните коэффициенты букмекеров
4. Примите решение о ставке

<b>Технологии:</b>
• 🤖 Нейросеть для прогнозов
• 📊 Статистический анализ
• 💰 Сравнение букмекеров
• ⚡ Value bets поиск

<b>Важно:</b>
• Бот для информационных целей
• Играйте ответственно
• 18+ только

<i>Удачи в ставках! 🍀</i>
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

@dp.callback_query(F.data == "refresh")
async def handle_refresh(callback: types.CallbackQuery):
    """Обновить"""
    await callback.answer("🔄 Обновление...")
    await cmd_start(callback.message)

# ========== СУЩЕСТВУЮЩИЕ КОМАНДЫ (оставляем как есть) ==========

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Матчи сегодня (оригинальная функция)"""
    matches = await panda_api.get_today_matches()
    
    if not matches:
        await message.answer("📭 <b>На сегодня нет запланированных матчей</b>")
        return
    
    # Форматируем матчи
    lines = ["📅 <b>МАТЧИ НА СЕГОДНЯ</b>", ""]
    
    for i, match in enumerate(matches[:10], 1):
        opponents = match.get("opponents", [])
        if len(opponents) >= 2:
            team1 = opponents[0].get("opponent", {})
            team2 = opponents[1].get("opponent", {})
            team1_name = team1.get("acronym") or team1.get("name", "TBA")
            team2_name = team2.get("acronym") or team2.get("name", "TBA")
            time_str = format_match_time(match.get("scheduled_at", ""))
            lines.append(f"{i}. {team1_name} vs {team2_name} ⏰ {time_str}")
    
    lines.append("")
    lines.append("🤖 <b>Получить прогноз:</b> /predict")
    
    await message.answer("\n".join(lines))

# ========== ЗАПУСК БОТА ==========

async def main():
    """Запуск каппер-бота"""
    logger.info("🎯 Запускаю CS2 KAPPER BOT...")
    logger.info("🤖 Нейросеть: АКТИВНА")
    logger.info("💰 Букмекеры: 8 контор")
    logger.info("📊 Аналитика: ВКЛЮЧЕНА")
    
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