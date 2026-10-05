import os
import json
import time
import subprocess
import sys

from server import keep_alive
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler
)

# ---------------------------------------------------------
# CONSTANTS & CONFIGURATION
# ---------------------------------------------------------
OWNER_ID = 8933985337  # Admin Owner ID
TEMPLATES_FILE = "templates.json"
USERS_FILE = "users.json"

# Conversation States
ADMIN_BOT_NAME, ADMIN_BOT_CODE = range(2)
USER_GET_TOKEN = range(2, 3)

# Active running process store
running_processes = {}

# ---------------------------------------------------------
# DATABASE HELPER FUNCTIONS
# ---------------------------------------------------------
def load_json(filename):
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump({}, f)
        return {}
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# Init files
load_json(TEMPLATES_FILE)
load_json(USERS_FILE)

# ---------------------------------------------------------
# SUBPROCESS BOT ENGINE
# ---------------------------------------------------------
def start_bot_process(user_id, bot_id, token, code_template):
    process_key = f"{user_id}_{bot_id}"
    
    # TOKENHERE এর জায়গায় ইউজার টোকেন বসানো
    final_code = code_template.replace("TOKENHERE", token)
    
    try:
        # সরাসরি ব্যাকগ্রাউন্ড প্রসেসে রান
        p = subprocess.Popen(
            [sys.executable, "-c", final_code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        running_processes[process_key] = p
        print(f"[SUCCESS] Bot {bot_id} started for user {user_id} (PID: {p.pid})")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to start bot {bot_id}: {e}")
        return False

def stop_bot_process(user_id, bot_id):
    process_key = f"{user_id}_{bot_id}"
    if process_key in running_processes:
        p = running_processes[process_key]
        p.terminate()
        del running_processes[process_key]

# ---------------------------------------------------------
# USER PANEL HANDLERS
# ---------------------------------------------------------
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🚀 বট চালু করুন", callback_data="user_start_bot")],
        [InlineKeyboardButton("📋 আমার বট", callback_data="user_my_bots")],
        [InlineKeyboardButton("🗑️ বট বন্ধ করুন", callback_data="user_stop_bot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("✨ **SK HOSTING READY** ✨\nনিচের যেকোনো অপশন নির্বাচন করুন:", reply_markup=reply_markup, parse_mode="Markdown")

def user_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "user_start_bot":
        templates = load_json(TEMPLATES_FILE)
        if not templates:
            query.edit_message_text("❌ বর্তমানে কোনো বট টেমপ্লেট এভেলেবল নেই।")
            return

        keyboard = []
        for t_id, t_info in templates.items():
            keyboard.append([InlineKeyboardButton(f"🚀 {t_info['name']}", callback_data=f"select_tpl_{t_id}")])
        
        query.edit_message_text("নিচের তালিকা থেকে একটি বট টেমপ্লেট বেছে নিন:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("select_tpl_"):
        template_id = data.split("select_tpl_")[1]
        context.user_data['selected_template'] = template_id
        query.edit_message_text("🔑 আপনার BotFather থেকে প্রাপ্ত **Bot Token** টি পাঠান:\n(ফরম্যাট: `1234567890:AAHxyz...`)", parse_mode="Markdown")
        return USER_GET_TOKEN

    elif data == "user_my_bots":
        users = load_json(USERS_FILE)
        user_bots = users.get(str(user_id), {})

        if not user_bots:
            query.edit_message_text("📋 আপনার বর্তমানে কোনো রানিং বট নেই।")
            return

        msg = "📋 **আপনার চালু থাকা বটসমূহ:**\n\n"
        for b_id, info in user_bots.items():
            msg += f"🤖 **নাম:** {info['name']}\n⏱️ **সময়:** {info['time']}\n🟢 **Status:** Running\n━━━━━━━━━━━━━━━━━━\n"
        
        query.edit_message_text(msg, parse_mode="Markdown")

    elif data == "user_stop_bot":
        users = load_json(USERS_FILE)
        user_bots = users.get(str(user_id), {})

        if not user_bots:
            query.edit_message_text("❌ বন্ধ করার মতো কোনো বট পাওয়া যায়নি।")
            return

        keyboard = []
        for b_id, info in user_bots.items():
            keyboard.append([InlineKeyboardButton(f"🛑 {info['name']}", callback_data=f"kill_bot_{b_id}")])

        query.edit_message_text("যে বটটি বন্ধ করতে চান সেটির উপর ক্লিক করুন:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("kill_bot_"):
        bot_id = data.split("kill_bot_")[1]
        users = load_json(USERS_FILE)
        str_uid = str(user_id)

        if str_uid in users and bot_id in users[str_uid]:
            stop_bot_process(user_id, bot_id)
            del users[str_uid][bot_id]
            save_json(USERS_FILE, users)
            query.edit_message_text("✅ বট সফলভাবে বন্ধ ও রিমুভ করা হয়েছে।")
        else:
            query.edit_message_text("❌ বটটি খুঁজে পাওয়া যায়নি।")

def user_receive_token(update: Update, context: CallbackContext):
    token = update.message.text.strip()
    user_id = update.message.from_user.id
    template_id = context.user_data.get('selected_template')

    if ":" not in token:
        update.message.reply_text("❌ অকার্যকর টোকেন! Bot Token-এ `:` থাকা আবশ্যক। পুনরায় চেষ্টা করুন:")
        return USER_GET_TOKEN

    templates = load_json(TEMPLATES_FILE)
    if template_id not in templates:
        update.message.reply_text("❌ টেমপ্লেটটি খুঁজে পাওয়া যায়নি। আবার চেষ্টা করুন।")
        return ConversationHandler.END

    tpl_info = templates[template_id]
    
    # Subprocess দিয়ে চালুর চেষ্টা
    success = start_bot_process(user_id, template_id, token, tpl_info["code"])

    if success:
        users = load_json(USERS_FILE)
        str_uid = str(user_id)
        if str_uid not in users:
            users[str_uid] = {}

        run_time = time.strftime("%Y-%m-%d %H:%M:%S")
        users[str_uid][template_id] = {
            "name": tpl_info["name"],
            "token": token,
            "time": run_time
        }
        save_json(USERS_FILE, users)
        update.message.reply_text(f"🚀 **{tpl_info['name']}** বট সফলভাবে চালু করা হয়েছে!\nStatus: 🟢 Running", parse_mode="Markdown")
    else:
        update.message.reply_text("❌ বট চালু করতে সমস্যা হয়েছে। টোকেন বা কোড যাচাই করুন।")

    return ConversationHandler.END

# ---------------------------------------------------------
# ADMIN PANEL HANDLERS
# ---------------------------------------------------------
def admin_panel(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        return

    keyboard = [
        [InlineKeyboardButton("➕ বট এড করুন", callback_data="admin_add_bot")],
        [InlineKeyboardButton("📋 বট লিস্ট দেখুন", callback_data="admin_list_bots")],
        [InlineKeyboardButton("♻️ রিসেট DB", callback_data="admin_reset_db")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("👑 **ADMIN PANEL SYSTEM**\nএকটি অপশন বেছে নিন:", reply_markup=reply_markup, parse_mode="Markdown")

def admin_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        query.answer("❌ শুধুমাত্র অ্যাডমিন এটি ব্যবহার করতে পারবে।", show_alert=True)
        return

    query.answer()
    data = query.data

    if data == "admin_add_bot":
        query.edit_message_text("Step 1: বটের নাম লিখুন (যেমন: Seller Bot, Shop Bot):")
        return ADMIN_BOT_NAME

    elif data == "admin_list_bots":
        templates = load_json(TEMPLATES_FILE)
        if not templates:
            query.edit_message_text("📋 কোনো বট টেমপ্লেট এড করা নেই।")
            return

        msg = "📋 **টেমপ্লেট বট তালিকা:**\n\n"
        for t_id, info in templates.items():
            msg += f"🆔 **ID:** `{t_id}`\n🤖 **নাম:** {info['name']}\n━━━━━━━━━━━━━━━━━━\n"
        query.edit_message_text(msg, parse_mode="Markdown")

    elif data == "admin_reset_db":
        for key in list(running_processes.keys()):
            u_id, b_id = key.split("_")
            stop_bot_process(u_id, b_id)

        save_json(TEMPLATES_FILE, {})
        save_json(USERS_FILE, {})
        query.edit_message_text("♻️ **Database Reset Complete!**\nসব টেমপ্লেট এবং ইউজার ডাটা ডিলিট করা হয়েছে।", parse_mode="Markdown")

def admin_get_name(update: Update, context: CallbackContext):
    context.user_data['new_bot_name'] = update.message.text
    update.message.reply_text("Step 2: বটের পুরো Python কোডটি পাঠান।\n⚠️ মনে রাখবেন: কোডের ভিতর টোকেনের জায়গায় `TOKENHERE` থাকতে হবে।", parse_mode="Markdown")
    return ADMIN_BOT_CODE

def admin_get_code(update: Update, context: CallbackContext):
    code_text = update.message.text
    bot_name = context.user_data.get('new_bot_name')
    template_id = str(int(time.time()))

    templates = load_json(TEMPLATES_FILE)
    templates[template_id] = {
        "name": bot_name,
        "code": code_text
    }
    save_json(TEMPLATES_FILE, templates)

    update.message.reply_text(f"✅ **{bot_name}** টেমপ্লেট সফলভাবে যুক্ত করা হয়েছে!\nID: `{template_id}`", parse_mode="Markdown")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("অপারেশন বাতিল করা হয়েছে।")
    return ConversationHandler.END

# ---------------------------------------------------------
# AUTO-RESTART HOSTED BOTS
# ---------------------------------------------------------
def restore_running_bots():
    users = load_json(USERS_FILE)
    templates = load_json(TEMPLATES_FILE)

    for uid, user_bots in users.items():
        for bot_id, info in user_bots.items():
            if bot_id in templates:
                token = info["token"]
                code_template = templates[bot_id]["code"]
                start_bot_process(int(uid), bot_id, token, code_template)

# ---------------------------------------------------------
# MAIN FUNCTION
# ---------------------------------------------------------
def main():
    # Start Flask Web Server
    keep_alive()

    # Get Master Bot Token
    master_token = os.environ.get("BOT_TOKEN")
    if not master_token:
        print("❌ Error: BOT_TOKEN Environment Variable পাওয়া যায়নি!")
        return

    updater = Updater(master_token, use_context=True)
    dp = updater.dispatcher

    # Restore previously hosted bots
    restore_running_bots()

    # Admin Conversation Handler
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_button_handler, pattern="^admin_add_bot$")],
        states={
            ADMIN_BOT_NAME: [MessageHandler(Filters.text & ~Filters.command, admin_get_name)],
            ADMIN_BOT_CODE: [MessageHandler(Filters.text & ~Filters.command, admin_get_code)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # User Token Conversation Handler
    user_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(user_button_handler, pattern="^select_tpl_")],
        states={
            USER_GET_TOKEN: [MessageHandler(Filters.text & ~Filters.command, user_receive_token)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Handlers Registration
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("admin", admin_panel))
    dp.add_handler(admin_conv)
    dp.add_handler(user_conv)
    dp.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^admin_"))
    dp.add_handler(CallbackQueryHandler(user_button_handler, pattern="^user_"))

    print("🚀 SK HOSTING BOT PRO IS NOW RUNNING...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
