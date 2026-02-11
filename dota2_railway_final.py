import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime
import logging

BOT_TOKEN = os.getenv('BOT_TOKEN')
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def parse_live_dota():
    """Парсим ТОЛЬКО реальные матчи прямо с сайтов"""
    try:
        async with aiohttp.ClientSession() as session:
            # === LIQUIPEDIA — ТОЛЬКО РЕАЛЬНЫЕ МАТЧИ ===
            url = "https://liquipedia.net/dota2/Liquipedia:Matches"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            async with session.get(url, headers=headers, timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                matches = []
                # Ищем таблицу с матчами
                for row in soup.select('table.wikitable tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        team1 = cells[0].get_text(strip=True)
                        team2 = cells[2].get_text(strip=True)
                        time = cells[3].get_text(strip=True)
                        score = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        # LIVE матчи содержат счет
                        if ':' in score:
                            matches.append({
                                'team1': team1,
                                'team2': team2,
                                'score': score,
                                'time': 'LIVE',
                                'tournament': 'Liquipedia'
                            })
                        # Будущие матчи
                        elif 'CEST' in time or 'UTC' in time:
                            matches.append({
                                'team1': team1,
                                'team2': team2,
                                'time': time,
                                'tournament': 'Liquipedia'
                            })
                
                if matches:
                    return matches[:5]  # 5 реальных матчей
    except Exception as e:
        logging.error(f"Liquipedia error: {e}")
    
    # === FALLBACK: ПРЯМОЙ ПАРСИНГ БУКМЕКЕРА ===
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://www.oddsportal.com/esports/dota-2/"
            async with session.get(url, headers=headers, timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                matches = []
                for event in soup.select('.event'):
                    teams = event.select('.participant-name')
                    if len(teams) >= 2:
                        matches.append({
                            'team1': teams[0].text.strip(),
                            'team2': teams[1].text.strip(),
                            'time': 'LIVE' if 'live' in event.get('class', []) else 'Upcoming',
                            'tournament': 'OddsPortal'
                        })
                if matches:
                    return matches[:5]
    except:
        pass
    
    return [{'team1': 'НЕТ LIVE МАТЧЕЙ', 'team2': 'ПРОВЕРЬ ПОЗЖЕ', 'time': '—', 'tournament': ''}]

@dp.message(Command("live"))
async def live_cmd(message: types.Message):
    msg = await message.answer("🔍 Парсим Liquipedia и OddsPortal...")
    matches = await parse_live_dota()
    
    if not matches or 'НЕТ LIVE МАТЧЕЙ' in matches[0]['team1']:
        await msg.edit_text("📭 Нет активных матчей Dota 2 прямо сейчас.\nПроверь через 15-30 минут.")
        return
    
    text = "🔴 <b>LIVE DOTA 2 МАТЧИ</b>\n"
    text += f"{datetime.now().strftime('%d.%m.%Y %H:%M')} МСК\n\n"
    
    for i, m in enumerate(matches[:3], 1):
        if 'score' in m:
            text += f"{i}. <b>{m['team1']} vs {m['team2']}</b>\n"
            text += f"   🎯 {m['score']} • {m.get('tournament', '')}\n"
        else:
            text += f"{i}. <b>{m['team1']} vs {m['team2']}</b>\n"
            text += f"   ⏰ {m['time']} • {m.get('tournament', '')}\n"
    
    await msg.edit_text(text, parse_mode='HTML')

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🐲 <b>DOTA 2 ПАРСЕР 2026</b>\n\n"
        "✅ Только реальные матчи\n"
        "✅ Liquipedia + OddsPortal\n"
        "✅ Без заглушек\n\n"
        "/live — матчи прямо сейчас"
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())