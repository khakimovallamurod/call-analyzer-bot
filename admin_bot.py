import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import TELEGRAM_BOT_TOKEN
from handlers import (
    start_handler,
    text_handler,
    audio_handler,
    stats_handler,
    transcript_callback,
    sales_audio_callback,
    audio_command_handler,
    sales_command_handler,
    document_handler
)
import database

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Httpx loglarini faqat WARNING darajasiga tushirish (getUpdates spam qilib yubormasligi uchun)
logging.getLogger("httpx").setLevel(logging.WARNING)

def main():
    """Botni ishga tushiruvchi asosiy funksiya"""
    # Bazani initsializatsiya qilish
    database.init_db()
    logger.info("Database tekshirildi va ishga tushdi.")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN topilmadi! Iltimos, .env faylini tekshiring.")
        return

    # Bot ilovasini yaratish
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Asosiy komandalar
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler(["audio", "call_analyzer"], audio_command_handler))
    app.add_handler(CommandHandler(["sales", "sales_analytics"], sales_command_handler))
    app.add_handler(CommandHandler("stats", stats_handler)) # Admin komandasi
    
    # Callback query handler (Tugmalar)
    app.add_handler(CallbackQueryHandler(transcript_callback, pattern='^transcript_'))
    app.add_handler(CallbackQueryHandler(sales_audio_callback, pattern='^sales_audio_'))
    
    # Audio va Voice xabarlarni ushlash (Guruhda va shaxsiyda)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    
    # Hujjatlarni ushlash (Excel, CSV yoki audio hujjatlar)
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    # Oddiy matnli xabarlarni ushlash
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Botni ishga tushirish
    logger.info("Bot ishga tushirildi...")
    app.run_polling()

if __name__ == "__main__":
    main()
