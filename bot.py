import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import Config
from parser import parser

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        Config.START_MSG,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        Config.HELP_MSG,
        parse_mode='Markdown'
    )

async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text(
        "🔄 *Загружаю матчи...*",
        parse_mode='Markdown'
    )
    
    try:
        matches = parser.get_upcoming_matches()
        
        if not matches:
            await message.edit_text("❌ *Матчей не найдено*", parse_mode='Markdown')
            return
        
        text = "🎮 *Ближайшие матчи CS2:*\n\n"
        
        for i, match in enumerate(matches, 1):
            stars = "⭐" * match.get('stars', 1)
            text += f"*{i}. {match['team1']}* vs *{match['team2']}*\n"
            text += f"   🏆 {match['event']}\n"
            text += f"   ⏰ {match['time']}\n"
            text += f"   📊 {match['format']} {stars}\n\n"
        
        text += "📊 *Данные с HLTV.org*"
        
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data='refresh')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.edit_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.edit_text("⚠️ *Ошибка при загрузке*", parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'refresh':
        await query.edit_message_text("🔄 *Обновляю...*", parse_mode='Markdown')
        matches = parser.get_upcoming_matches()
        
        if not matches:
            await query.edit_message_text("❌ *Матчей не найдено*", parse_mode='Markdown')
            return
        
        text = "🎮 *Ближайшие матчи CS2:*\n\n"
        
        for i, match in enumerate(matches, 1):
            stars = "⭐" * match.get('stars', 1)
            text += f"*{i}. {match['team1']}* vs *{match['team2']}*\n"
            text += f"   🏆 {match['event']}\n"
            text += f"   ⏰ {match['time']}\n"
            text += f"   📊 {match['format']} {stars}\n\n"
        
        text += "📊 *Данные с HLTV.org*"
        
        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data='refresh')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

def main():
    print("🚀 Запускаю CS2 Matches Bot...")
    
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("matches", matches_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
