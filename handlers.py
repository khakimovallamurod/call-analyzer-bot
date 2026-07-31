import os
import tempfile
import re
import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL, ADMIN_IDS
from prompt import QA_SYSTEM_PROMPT
from keyboards import get_main_keyboard, get_admin_panel_keyboard
import database

# Gemini API ni sozlash
client = genai.Client(api_key=GEMINI_API_KEY)

# Stiker ID lari
HELLO_STICKER = "CAACAgIAAxkBAAEF... (Sizning salom stiker ID)" 
WAIT_STICKER = "CAACAgIAAxkBAAEF... (Kutish stikeri ID)"

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi /start bosganda"""
    is_admin = update.message.from_user.id in ADMIN_IDS
    welcome_text = (
        "👋 Assalomu alaykum! Men mijozlarga xizmat ko'rsatish sifatini baholaydigan tahliliy botman.\n\n"
        "Menga operator va mijoz o'rtasidagi suhbat audiosini yuboring (yoki Forward qiling), "
        "men uni eshitib to'liq tahlil qilib, sizga hisobot taqdim etaman."
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(is_admin))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalar bosilganda yoki oddiy matn yuborilganda"""
    if update.message.chat.type in ['group', 'supergroup']:
        return

    text = update.message.text
    user_id = update.message.from_user.id
    is_admin = user_id in ADMIN_IDS

    if text == "📊 Audio yuborish":
        await update.message.reply_text("🎙 Iltimos, audio faylni (.mp3, .ogg, .wav, yoki Voice) yuboring.")
    elif text == "ℹ️ Bot haqida":
        info_text = (
            "Ushbu bot suhbat audiosini eshitib, xodimning muomalasi, "
            "mijozning hissiy holati va xizmat sifatini tahlil qiladi."
        )
        await update.message.reply_text(info_text, parse_mode="Markdown")
        
    # --- ADMIN MENYULARI ---
    elif text == "👑 Admin Panel" and is_admin:
        await update.message.reply_text("👑 Admin panelga xush kelibsiz!", reply_markup=get_admin_panel_keyboard())
    elif text == "🔙 Orqaga" and is_admin:
        await update.message.reply_text("Asosiy menyuga qaytdingiz.", reply_markup=get_main_keyboard(is_admin))
    elif text == "📈 Umumiy Statistika" and is_admin:
        stats = database.get_stats()
        msg = (
            "📈 *Bot Statistikasi:*\n\n"
            f"👥 Unikal foydalanuvchilar: {stats['unique_users']}\n"
            f"📊 Umumiy tahlillar soni: {stats['total_reports']}\n"
            f"⚡ Bugungi tahlillar soni: {stats['today_reports']}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif text == "🏆 Xodimlar reytingi" and is_admin:
        top = database.get_top_employees(10)
        if not top:
            await update.message.reply_text("Hozircha reyting shakllanmagan.")
            return
        
        msg = "🏆 *Eng yaxshi xodimlar (Top 10):*\n\n"
        for i, emp in enumerate(top, 1):
            msg += f"{i}. {emp['username']} — O'rtacha baho: {emp['avg_score']:.1f} ({emp['count']} ta audio)\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif text == "📝 Oxirgi tahlillar" and is_admin:
        latest = database.get_latest_reports(5)
        if not latest:
            await update.message.reply_text("Hozircha tahlillar yo'q.")
            return
            
        msg = "📝 *Oxirgi 5 ta tahlil qilingan audio:*\n\n"
        for rep in latest:
            score_text = f"{rep['score']} ball" if rep['score'] is not None else "Baho yo'q"
            date_str = rep['created_at'][:16]
            msg += f"👤 {rep['username']} — {score_text} ({date_str})\n"
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Iltimos, audio fayl yuboring yoki menyudan foydalaning.")

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminlar uchun statistika (Komanda bilan /stats)"""
    user_id = update.message.from_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Sizda bu komandani ishlatish huquqi yo'q.")
        return
        
    stats = database.get_stats()
    text = (
        "📈 *Bot Statistikasi:*\n\n"
        f"👥 Unikal foydalanuvchilar: {stats['unique_users']}\n"
        f"📊 Umumiy tahlillar soni: {stats['total_reports']}\n"
        f"⚡ Bugungi tahlillar soni: {stats['today_reports']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio faylni qabul qilib, Gemini ga yuborish va tahlil qilish"""
    message = update.message
    
    audio_file = message.voice or message.audio or message.document
    
    if not audio_file:
        if message.chat.type == 'private':
            await update.message.reply_text("Kechirasiz, faqat audio fayllarni tahlil qila olaman.")
        return
    
    if message.document and not message.document.mime_type.startswith('audio/'):
        if message.chat.type == 'private':
            await update.message.reply_text("Kechirasiz, faqat audio formatdagi fayllarni qabul qilaman.")
        return

    status_message = await update.message.reply_text("⏳ Audio fayl yuklab olinmoqda va tahlil qilinmoqda. Kuting...")

    try:
        file_id = audio_file.file_id
        new_file = await context.bot.get_file(file_id)
        
        ext = ".ogg" if message.voice else ".mp3"
        if message.document and message.document.file_name:
            ext = os.path.splitext(message.document.file_name)[1]
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_audio:
            temp_path = temp_audio.name
            
        await new_file.download_to_drive(temp_path)
        
        await status_message.edit_text("🧠 Audio tinglanmoqda va tahlil qilinmoqda... Bu bir necha soniya olishi mumkin.")
        
        uploaded_file = client.files.upload(path=temp_path)
        file_part = types.Part.from_uri(file_uri=uploaded_file.uri, mime_type=uploaded_file.mime_type)
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[QA_SYSTEM_PROMPT, file_part],
                    config=types.GenerateContentConfig(temperature=0.2)
                )
                break
            except Exception as api_err:
                if attempt < max_retries - 1 and ("503" in str(api_err) or "429" in str(api_err) or "UNAVAILABLE" in str(api_err)):
                    await asyncio.sleep(2 ** attempt)  # 1s, 2s
                    continue
                raise api_err
        
        report_text = response.text
        
        # TRANSCRIPT ni ajratib olish
        transcript_text = None
        if "---TRANSCRIPT---" in report_text:
            parts = report_text.split("---TRANSCRIPT---")
            report_text = parts[0].strip()
            if len(parts) > 1:
                transcript_text = parts[1].strip()
                
        # Agar audio mos bo'lmasa, qaytarish
        if "Ushbu audio tahlil uchun mos emas" in report_text:
            await status_message.edit_text("🚫 **Ushbu audio tahlil uchun mos emas** (Suhbat aniqlanmadi).", parse_mode="Markdown")
            return
            
        # Telegram Markdown v1 uchun to'g'irlash
        formatted_text = re.sub(r'^\*\s+', '• ', report_text, flags=re.MULTILINE)
        formatted_text = formatted_text.replace('**', '*')
        formatted_text = formatted_text.replace('##', '📌')
        
        # Bahoni (Score) qidirib topish
        score = None
        # "Baho: 8", "Umumiy ball: 8.5" kabilarni ushlash
        score_match = re.search(r'(?:Baho|Umumiy ball).*?(\d+)', report_text, re.IGNORECASE)
        if score_match:
            score = int(score_match.group(1))

        # Bazaga saqlash va ID ni olish
        user = message.from_user
        username = f"@{user.username}" if user.username else user.first_name
        audio_type = "voice" if message.voice else "audio/document"
        report_id = database.save_report(
            user_id=user.id,
            username=username,
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            audio_type=audio_type,
            report_text=report_text,
            score=score,
            transcript=transcript_text
        )
        
        # Matn tugmasini yaratish
        reply_markup = None
        if transcript_text:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Matnni ko'rish", callback_data=f"transcript_{report_id}")]
            ])

        # Hisobotni qaytarish
        try:
            await status_message.edit_text(formatted_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as md_err:
            if "parse entities" in str(md_err).lower() or "can't parse" in str(md_err).lower():
                await status_message.edit_text(formatted_text, reply_markup=reply_markup)
            else:
                raise md_err
        
        # Gemini serveridan o'chirish
        client.files.delete(name=uploaded_file.name)
        
    except Exception as e:
        if "503" in str(e) or "UNAVAILABLE" in str(e):
            await status_message.edit_text("❌ Sun'iy intellekt serverlarida vaqtinchalik tirbandlik. Iltimos, birozdan so'ng qayta urinib ko'ring.", parse_mode="Markdown")
        else:
            await status_message.edit_text(f"❌ Xatolik yuz berdi:\n`{str(e)}`", parse_mode="Markdown")
    finally:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

async def transcript_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matnni ko'rish tugmasi bosilganda"""
    query = update.callback_query
    await query.answer()
    
    try:
        report_id = int(query.data.split('_')[1])
        transcript = database.get_transcript(report_id)
        
        if transcript:
            # Markdown v1 uchun to'g'irlash
            transcript = transcript.replace('**', '*')
            msg = f"📝 *Audio matni (Transkripsiya):*\n\n{transcript}"
            
            # Matn juda uzun bo'lsa xato bermasligi uchun qirqamiz (Telegram limit: 4096 belgi)
            if len(msg) > 4000:
                msg = msg[:4000] + "...\n[Matn juda uzun, qirqildi]"
                
            try:
                await query.message.reply_text(msg, parse_mode="Markdown")
            except Exception:
                await query.message.reply_text(msg)  # Formatlashsiz yuborish
        else:
            await query.message.reply_text("Kechirasiz, ushbu audio matni bazadan topilmadi.")
    except Exception as e:
        await query.message.reply_text("Xatolik yuz berdi matnni olishda.")
