import os, json, telebot, threading, subprocess, sys
from telebot import types
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
DB_FILE = "templates.json"

# DB তৈরি
if not os.path.exists(DB_FILE):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump({}, f)

def load_db():
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)

# State
admin_state = {} # admin_id -> {step, name}
user_state = {} # user_id -> bot_key

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন", "📋 বট লিস্ট")
    kb.row("🗑️ বট ডিলিট করুন", "♻️ রিসেট DB")
    return kb

def user_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন")
    return kb

@bot.message_handler(commands=['start'])
def start_cmd(m):
    if m.from_user.id == ADMIN_ID:
        admin_state.pop(m.from_user.id, None)
        bot.send_message(m.chat.id, "👑 **ADMIN PANEL - SK HOSTING PRO**\n\n✅ বট রেডি\n➕ বট এড করুন এ চাপ দিন", reply_markup=admin_kb(), parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "👋 SK Hosting Pro তে স্বাগতম!\n\nআপনার বট হোস্ট করতে নিচের বাটনে চাপ দিন।", reply_markup=user_kb())

# ===== ADMIN HANDLER =====
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_handler(m):
    text = m.text.strip()

    if text == "➕ বট এড করুন":
        admin_state[m.from_user.id] = {"step": "wait_name"}
        bot.send_message(m.chat.id, "১️⃣ **বটের নাম লিখুন:**\nযেমন: `বিজনেস বট` বা `Seller Bot`", parse_mode="Markdown")
        return

    if text == "📋 বট লিস্ট":
        db = load_db()
        if not db:
            bot.send_message(m.chat.id, "❌ লিস্ট খালি। আগে বট এড করুন।")
        else:
            msg = "📋 **এড করা বট:**\n\n"
            for k,v in db.items(): msg += f"🔹 {v['name']} | ID: `{k}`\n"
            bot.send_message(m.chat.id, msg, parse_mode="Markdown")
        return

    if text == "🗑️ বট ডিলিট করুন":
        db = load_db()
        if not db: bot.send_message(m.chat.id, "❌ ডিলিট করার মত বট নাই"); return
        mk = types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"❌ {v['name']}", callback_data=f"DEL_{k}"))
        bot.send_message(m.chat.id, "কোনটা ডিলিট করবেন?", reply_markup=mk)
        return

    if text == "♻️ রিসেট DB":
        save_db({})
        bot.send_message(m.chat.id, "✅ DB রিসেট করা হয়েছে। এখন নতুন করে বট এড করুন।")
        return

    # Step by step add
    if m.from_user.id in admin_state:
        st = admin_state[m.from_user.id]
        if st["step"] == "wait_name":
            st["name"] = text
            st["step"] = "wait_code"
            bot.send_message(m.chat.id, f"✅ নাম সেভ: **{text}**\n\n২️⃣ **এখন বটের পুরো কোড দিন**\n\n⚠️ অবশ্যই টোকেনের জায়গায় `{{TOKEN}}` লিখবেন।\nযেমন: `TeleBot('{{TOKEN}}')`", parse_mode="Markdown")
            return
        if st["step"] == "wait_code":
            code = m.text # code with new lines
            name = st["name"]
            bot_id = "".join(e for e in name.lower() if e.isalnum())[:20] + str(len(load_db()))
            db = load_db()
            db[bot_id] = {"name": name, "code": code}
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **সেভ হয়েছে!**\n\nনাম: {name}\nID: {bot_id}\n\nইউজার এখন `🤖 বট চালু করুন` এ এটা দেখতে পাবে।", reply_markup=admin_kb())
            del admin_state[m.from_user.id]
            return

# ===== USER HANDLER =====
@bot.message_handler(func=lambda m: m.from_user.id!= ADMIN_ID)
def user_handler(m):
    text = m.text.strip()
    if text == "🤖 বট চালু করুন":
        db = load_db()
        if not db:
            bot.send_message(m.chat.id, "❌ Admin এখনো কোনো বট এড করেনি। পরে ট্রাই করুন।")
            return
        mk = types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items():
            mk.add(types.InlineKeyboardButton(f"🚀 {v['name']}", callback_data=f"RUN_{k}"))
        bot.send_message(m.chat.id, "👇 **কোন বট চালু করবেন সিলেক্ট করুন:**", reply_markup=mk, parse_mode="Markdown")
        return

    # User token input
    if m.from_user.id in user_state:
        token = text
        if ":" not in token or len(token) < 20:
            bot.send_message(m.chat.id, "❌ এটা সঠিক টোকেন না। BotFather থেকে টোকেন কপি করে দিন।")
            return
        bot_key = user_state[m.from_user.id]
        db = load_db()
        if bot_key not in db:
            bot.send_message(m.chat.id, "❌ এই বটটা ডিলিট হয়ে গেছে।")
            return
        raw_code = db[bot_key]["code"]
        final_code = raw_code.replace("{TOKEN}", token).replace("{{TOKEN}}", token)

        file_name = f"bot_{m.from_user.id}_{bot_key}.py"
        with open(file_name, 'w', encoding='utf-8') as f: f.write(final_code)

        # Kill old if exists
        try: subprocess.Popen([sys.executable, file_name])
        except Exception as e:
            bot.send_message(m.chat.id, f"❌ রান করতে Error: {e}\n\nকোডে ভুল আছে। Admin কে বলুন।")
            return

        bot.send_message(m.chat.id, f"✅ **{db[bot_key]['name']}** সফলভাবে রান হয়েছে!\n\n🟢 Status: Online 24/7\n🔑 Token: `{token[:10]}...`\n\nএখন আপনার বটে গিয়ে /start দিন।", parse_mode="Markdown")
        del user_state[m.from_user.id]
        return

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    data = c.data
    if data.startswith("DEL_") and c.from_user.id == ADMIN_ID:
        k = data.replace("DEL_", "")
        db = load_db()
        if k in db: del db[k]; save_db(db); bot.send_message(c.message.chat.id, f"🗑️ ডিলিট হয়েছে: {k}")
        bot.answer_callback_query(c.id)
    elif data.startswith("RUN_"):
        k = data.replace("RUN_", "")
        user_state[c.from_user.id] = k
        db = load_db()
        name = db.get(k, {}).get("name", "Bot")
        bot.send_message(c.message.chat.id, f"✅ আপনি **{name}** সিলেক্ট করেছেন।\n\nএখন আপনার Bot Token টি পাঠান:\n(BotFather থেকে নিবেন)", parse_mode="Markdown")
        bot.answer_callback_query(c.id)

# Flask + Polling
app = Flask(__name__)
@app.route('/')
def home(): return "SK HOSTING PRO IS LIVE"

def run_bot(): bot.infinity_polling(none_stop=True, timeout=60, long_polling_timeout=60)
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
