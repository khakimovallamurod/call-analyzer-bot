import os
import tempfile
import re
import asyncio
import uuid
import io
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_AUDIO_MODEL, GEMINI_SALES_MODEL, ADMIN_IDS, DATASETS_DIR
from prompt import QA_SYSTEM_PROMPT
from keyboards import get_main_keyboard, get_audio_keyboard, get_sales_keyboard, get_admin_panel_keyboard
import database
import sales_analytics

# Gemini API ni sozlash
client = genai.Client(api_key=GEMINI_API_KEY)

# Stiker ID lari
HELLO_STICKER = "CAACAgIAAxkBAAEF... (Sizning salom stiker ID)" 
WAIT_STICKER = "CAACAgIAAxkBAAEF... (Kutish stikeri ID)"

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi /start bosganda"""
    is_admin = update.message.from_user.id in ADMIN_IDS
    context.user_data['mode'] = None
    welcome_text = (
        "👋 **Assalomu alaykum! Tahliliy botimizga xush kelibsiz!**\n\n"
        "Botda 2 ta asosiy mustaqil yo'nalish mavjud:\n\n"
        "1️⃣ **🎙 Qo'ng'iroqlar tahlili (/audio)** — Xodim va mijoz o'rtasidagi audio suhbatlarni eshitib, "
        "xizmat ko'rsatish sifati, odob-axloq va mijoz ehtiyojlarini tahlil qiladi.\n\n"
        "2️⃣ **📈 Savdo tahlili (/sales)** — Excel/CSV hisobotlar asosida savdo tushumlari, mijozlar (ABC), "
        "hududlar va SKU (mahsulotlar) bo'yicha sun'iy intellekt orqali chuqur tahlil beradi.\n\n"
        "Kerakli bo'limni tanlash uchun quyidagi tugmalardan birini bosing yoki tegishli komandani yuboring."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin))

async def audio_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/audio yoki /call_analyzer komandasi bosilganda"""
    context.user_data['mode'] = 'audio'
    text = (
        "🎙 **Qo'ng'iroqlar tahlili (Call Analyzer) rejimi faollashtirildi!**\n\n"
        "Menga operator va mijoz o'rtasidagi suhbat audiosini yuboring (Voice, .mp3, .ogg, .wav formatda).\n"
        "Men uni diqqat bilan eshitib, to'liq tahliliy hisobot va baho taqdim etaman.\n\n"
        "🔙 Bosh menyuga qaytish uchun *'🔙 Asosiy menyu'* tugmasini bosing."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_audio_keyboard())

async def sales_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sales yoki /sales_analytics komandasi bosilganda"""
    context.user_data['mode'] = 'sales'
    text = (
        "📈 **Sales AI Analytics rejimi faollashtirildi!**\n\n"
        "Ushbu rejimda savdo, mijozlar (ABC), hududlar va SKU bo'yicha tahliliy savollaringizni yozishingiz mumkin.\n\n"
        "💡 **Misol savollar:**\n"
        "• `Фуркат Курбанов bo'yicha analiz qil`\n"
        "• `Qaysi hudud eng ko'p sotuv qilgan?`\n"
        "• `Mijozlar bo'yicha ABC tahlil`\n"
        "• `Eng ko'p sotilgan SKUlarni ko'rsat`\n\n"
        "📁 Shuningdek, yangi Excel (.xlsx, .csv) fayl yuborib yangilashingiz ham mumkin.\n\n"
        "🔙 Bosh menyuga qaytish uchun *'🔙 Asosiy menyu'* tugmasini bosing."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_sales_keyboard())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalar bosilganda yoki oddiy matn yuborilganda"""
    if update.message.chat.type in ['group', 'supergroup']:
        return

    text = update.message.text.strip()
    user_id = update.message.from_user.id
    is_admin = user_id in ADMIN_IDS
    current_mode = context.user_data.get('mode')

    # Rejimlarni ochish tugmalari
    if text in ["🎙 Qo'ng'iroqlar tahlili (/audio)", "/audio", "/call_analyzer"]:
        await audio_command_handler(update, context)
        return

    if text in ["📈 Savdo tahlili (/sales)", "/sales", "/sales_analytics"]:
        await sales_command_handler(update, context)
        return

    # Asosiy menyuga qaytish
    if text in ["🔙 Asosiy menyu", "🔙 Orqaga"]:
        context.user_data['mode'] = None
        await update.message.reply_text("Asosiy menyuga qaytdingiz. Kerakli bo'limni tanlang:", reply_markup=get_main_keyboard(is_admin))
        return

    # Bot haqida
    if text == "ℹ️ Bot haqida":
        info_text = (
            "🤖 **Call Analyzer & Sales AI Bot**\n\n"
            "Ushbu ko'p tarmoqli tahliliy bot 2 ta asosiy moduldan iborat:\n\n"
            "1. **Call Analyzer:** Operator va mijoz suhbatini eshitib, odob-axloq, mijoz ehtiyoji, "
            "bosim yo'qligi bo'yicha ball qo'yadi va to'liq transkripsiyasini taqdim etadi.\n\n"
            "2. **Sales AI Analytics:** Excel/CSV ma'lumotlari asosida RAG arxitekturasi orqali ABC tahlil, "
            "hududlar (Gear list bilan JOIN), SKU mahsulotlar va mas'ul agentlar bo'yicha aniq, faktik tahlillarni amalga oshiradi."
        )
        await update.message.reply_text(info_text, parse_mode="Markdown")
        return

    # --- ADMIN MENYULARI ---
    if text == "👑 Admin Panel" and is_admin:
        await update.message.reply_text("👑 Admin panelga xush kelibsiz!", reply_markup=get_admin_panel_keyboard())
        return
    elif text == "📈 Umumiy Statistika" and is_admin:
        stats = database.get_stats()
        msg = (
            "📈 *Bot Statistikasi:*\n\n"
            f"👥 Unikal foydalanuvchilar: {stats['unique_users']}\n"
            f"📊 Umumiy tahlillar soni: {stats['total_reports']}\n"
            f"⚡ Bugungi tahlillar soni: {stats['today_reports']}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
    elif text == "🏆 Xodimlar reytingi" and is_admin:
        top = database.get_top_employees(10)
        if not top:
            await update.message.reply_text("Hozircha reyting shakllanmagan.")
            return
        
        msg = "🏆 *Eng yaxshi xodimlar (Top 10):*\n\n"
        for i, emp in enumerate(top, 1):
            msg += f"{i}. {emp['username']} — O'rtacha baho: {emp['avg_score']:.1f} ({emp['count']} ta audio)\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return
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
        return

    # --- AUDIO REJIMI TUGMALARI ---
    if current_mode == 'audio':
        if text == "📊 Audio yuborish":
            await update.message.reply_text("🎙 Iltimos, audio faylni (.mp3, .ogg, .wav, yoki Voice) yuboring.")
            return
        else:
            await update.message.reply_text(
                "🎙 Siz hozir **Qo'ng'iroqlar tahlili** rejimidasiz.\n"
                "Iltimos, audio fayl yuboring yoki boshqa bo'limga o'tish uchun '🔙 Asosiy menyu' tugmasini bosing.",
                parse_mode="Markdown"
            )
            return

    # --- SALES ANALYTICS REJIMI TUGMALARI VA SAVOLLAR ---
    if current_mode == 'sales':
        query_text = text
        if text == "📊 ABC tahlil (Mijozlar)":
            query_text = "Mijozlar bo'yicha ABC klassifikatsiyasini tahlil qilib ber"
        elif text == "🗺 Hududlar tahlili":
            query_text = "Hududlar bo'yicha savdo va reytingni tahlil qilib ber"
        elif text == "📦 TOP SKUlar":
            query_text = "Eng ko'p sotilgan TOP SKU mahsulotlarni tahlil qilib ber"
        elif text == "👥 Agentlar ro'yxati":
            agents = sales_analytics.get_available_agents()
            if agents:
                msg = "👥 **Mavjud savdo agentlari:**\n\n"
                for i, ag in enumerate(agents, 1):
                    msg += f"{i}. `{ag}`\n"
                msg += "\n💡 Biror agent tahlilini ko'rish uchun uning ismini yuboring (masalan: `Фуркат Курбанов bo'yicha analiz qil`)."
                await update.message.reply_text(msg, parse_mode="Markdown")
                return
            else:
                await update.message.reply_text("Agentlar ro'yxati topilmadi.")
                return

        # Savol berildi - Sales AI ga yuboramiz
        status_msg = await update.message.reply_text("⏳ *Ma'lumotlar manbasi o'rganilmoqda va hisob-kitoblar bajarilmoqda...*", parse_mode="Markdown")
        try:
            ai_response, audio_summary = await sales_analytics.ask_sales_ai(query_text)
            
            # Inline audio tugmasini shakllantirish (har doim 100% chiqishi ta'minlanadi)
            if not audio_summary:
                clean_raw = re.sub(r'[*_`~\[\]]', '', ai_response)
                summary_lines = [l.strip() for l in clean_raw.split('\n') if l.strip() and not l.startswith(('•', '-', '📊', '📌', '🏪', '💰', '🏷'))]
                audio_summary = " ".join(summary_lines[-3:]) if summary_lines else clean_raw[:250]

            audio_id = str(uuid.uuid4())[:8]
            context.bot_data.setdefault('sales_audio_cache', {})[audio_id] = audio_summary
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔊 Xulosa audiosini eshitish", callback_data=f"sales_audio_{audio_id}")]
            ])

            # Telegram limiti: 4096 belgi
            if len(ai_response) <= 4000:
                try:
                    await status_msg.edit_text(ai_response, parse_mode="Markdown", reply_markup=reply_markup)
                except Exception as md_err:
                    await status_msg.edit_text(ai_response, reply_markup=reply_markup)
            else:
                # Bir nechta xabarga bo'lish
                await status_msg.delete()
                lines = ai_response.split('\n')
                current_chunk = ""
                chunks = []
                for line in lines:
                    if len(current_chunk) + len(line) + 1 > 3800:
                        chunks.append(current_chunk.strip())
                        current_chunk = line + "\n"
                    else:
                        current_chunk += line + "\n"
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())

                for i, chunk in enumerate(chunks):
                    # Tugmani oxirgi qismga qo'yamiz
                    msg_markup = reply_markup if i == len(chunks) - 1 else None
                    try:
                        await update.message.reply_text(chunk, parse_mode="Markdown", reply_markup=msg_markup)
                    except Exception:
                        await update.message.reply_text(chunk, reply_markup=msg_markup)
        except Exception as err:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: {str(err)}")
        return

    # Agar hech qaysi rejim tanlanmagan bo'lsa
    await update.message.reply_text(
        "Iltimos, avval pastdagi menyudan kerakli bo'limni tanlang:\n\n"
        "• 🎙 **Qo'ng'iroqlar tahlili (/audio)**\n"
        "• 📈 **Savdo tahlili (/sales)**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

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
    current_mode = context.user_data.get('mode')

    # Agar foydalanuvchi Sales rejimida bo'lsa, adashmaslik uchun ogohlantiramiz
    if current_mode == 'sales':
        await update.message.reply_text(
            "⚠️ Siz hozir **Sales AI Analytics** rejimidagiz.\n\n"
            "Audio suhbatni tahlil qilish uchun avval /audio komandasini yuboring yoki *'🔙 Asosiy menyu'* orqali audio bo'limiga o'ting.",
            parse_mode="Markdown"
        )
        return

    # Audio rejimiga avtomatik o'tkazamiz
    context.user_data['mode'] = 'audio'
    
    audio_file = message.voice or message.audio or message.document
    
    if not audio_file:
        if message.chat.type == 'private':
            await update.message.reply_text("Kechirasiz, faqat audio fayllarni tahlil qila olaman.")
        return
    
    if message.document and not (message.document.mime_type and message.document.mime_type.startswith('audio/')):
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
                    model=GEMINI_AUDIO_MODEL,
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

async def sales_audio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xulosa audiosini eshitish tugmasi bosilganda (0 Gemini token sarflaydi!)"""
    query = update.callback_query
    await query.answer("🔊 Audio tayyorlanmoqda, kuting...")

    audio_id = query.data.replace("sales_audio_", "").strip()
    cache = context.bot_data.get('sales_audio_cache', {})
    audio_text = cache.get(audio_id)

    if not audio_text:
        # Keshda topilmasa, xabar matnidan olamiz
        msg_text = query.message.text or query.message.caption or ""
        lines = [l.strip() for l in msg_text.split('\n') if l.strip() and not l.startswith(('•', '-', '📊', '📌', '🏪', '💰', '🏷'))]
        audio_text = " ".join(lines[:3]) if lines else "Savdo tahlili hisoboti tayyor."

    try:
        audio_bytes = await sales_analytics.generate_speech_audio(audio_text)
        if audio_bytes:
            bio = io.BytesIO(audio_bytes)
            bio.name = "sales_summary.mp3"
            await query.message.reply_voice(
                voice=bio,
                caption="🎧 *Tahlil bo'yicha audio hisobot*\n_(Asosiy tahliliy xulosa)_",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text("Kechirasiz, audio xulosani shakllantirishda xatolik yuz berdi.")
    except Exception as e:
        await query.message.reply_text(f"Audio yaratishda xatolik: {str(e)}")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Excel yoki CSV fayllar, yoxud audio hujjatlar yuborilganda"""
    message = update.message
    doc = message.document
    if not doc:
        return

    file_name = doc.file_name or ""
    lower_name = file_name.lower()

    # Agar audio hujjat bo'lsa
    if (doc.mime_type and doc.mime_type.startswith('audio/')) or lower_name.endswith(('.mp3', '.ogg', '.wav', '.m4a')):
        await audio_handler(update, context)
        return

    # Agar Excel yoki CSV fayl bo'lsa
    if lower_name.endswith(('.xlsx', '.xls', '.csv')):
        status_msg = await update.message.reply_text(f"⏳ `{file_name}` qabul qilinmoqda va bazaga yuklanmoqda...", parse_mode="Markdown")
        try:
            os.makedirs(DATASETS_DIR, exist_ok=True)
            save_path = os.path.join(DATASETS_DIR, file_name)
            
            new_file = await context.bot.get_file(doc.file_id)
            await new_file.download_to_drive(save_path)

            # Sales ma'lumotlar bazasini yangilash
            sales_analytics.data_loader.reload()
            context.user_data['mode'] = 'sales'

            text = (
                f"✅ **Yangi hisobot muvaffaqiyatli yuklandi!**\n\n"
                f"📁 Fayl: `{file_name}`\n"
                f"📊 Ma'lumotlar bazasi yangilandi va JOIN qilindi.\n\n"
                f"Endi ushbu fayl bo'yicha tahliliy savollaringizni yozishingiz mumkin (masalan: `Mijozlar ABC tahlili` yoki `Agent bo'yicha analiz`)."
            )
            await status_msg.edit_text(text, parse_mode="Markdown", reply_markup=get_sales_keyboard())
        except Exception as e:
            await status_msg.edit_text(f"❌ Faylni yuklashda xatolik yuz berdi:\n`{str(e)}`", parse_mode="Markdown")
        return

    # Boshqa fayl bo'lsa
    await update.message.reply_text("Kechirasiz, faqat audio fayllar (.mp3, .ogg, .wav) yoki Excel/CSV (.xlsx, .csv) fayllarini tahlil qila olaman.")
