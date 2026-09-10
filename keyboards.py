from telegram import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard(is_admin=False):
    """Asosiy menyu tugmalari - ikkita alohida yo'nalish"""
    keyboard = [
        [KeyboardButton("🎙 Qo'ng'iroqlar tahlili (/audio)"), KeyboardButton("📈 Savdo tahlili (/sales)")],
        [KeyboardButton("ℹ️ Bot haqida")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_audio_keyboard():
    """Audio tahlil (Call Analyzer) rejimi tugmalari"""
    keyboard = [
        [KeyboardButton("🎙 Audio yuborish")],
        [KeyboardButton("🔙 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_sales_keyboard():
    """Sales AI Analytics rejimi tugmalari"""
    keyboard = [
        [KeyboardButton("📊 ABC tahlil (Mijozlar)"), KeyboardButton("🗺 Hududlar tahlili")],
        [KeyboardButton("📦 TOP SKUlar"), KeyboardButton("👥 Agentlar ro'yxati")],
        [KeyboardButton("🔙 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_panel_keyboard():
    """Admin panel tugmalari"""
    keyboard = [
        [KeyboardButton("📈 Umumiy Statistika"), KeyboardButton("🏆 Xodimlar reytingi")],
        [KeyboardButton("📝 Oxirgi tahlillar"), KeyboardButton("🔙 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
