from telegram import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard(is_admin=False):
    """Asosiy menyu tugmalari"""
    keyboard = [
        [KeyboardButton("📊 Audio yuborish"), KeyboardButton("ℹ️ Bot haqida")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton("👑 Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_panel_keyboard():
    """Admin panel tugmalari"""
    keyboard = [
        [KeyboardButton("📈 Umumiy Statistika"), KeyboardButton("🏆 Xodimlar reytingi")],
        [KeyboardButton("📝 Oxirgi tahlillar"), KeyboardButton("🔙 Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
