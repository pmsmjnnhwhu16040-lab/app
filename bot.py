import os, json, telebot, threading, subprocess
from telebot import types

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
DB = "templates.json"

def load_db():
    if not os.path.exists(DB):
        with open(DB, 'w') as f: json.dump({}, f)
    with open(DB, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return {}

def save_db(data):
    with open(DB, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)

admin_step = {} # id: {"step": "name", "name": "..."}
user_step = {} # id: bot_id

def admin_kb():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add("➕ বট এড করুন", "📋 বট লিস্ট")
    mk.add("🗑️ বট ডিলিট করুন")
    return mk

def user_kb():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add("🤖 বট চালু করুন")
    return mk

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id == ADMIN_ID:
        admin_step.pop(m.from_user.id, None)
        bot.send_message(m.chat.id, "👑 **ADMIN PANEL**\n\nবটের নাম আর কোড এড করুন।", reply_markup=admin_kb(), parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "👋 স্বাগতম! বট হোস্ট করতে নিচের বাটনে চাপ দাও।", reply_markup=user_kb())

# ========= ADMIN =========
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ বট এড করুন")
def add_start(m):
    admin_step[m.from_user.id] = {"step": "name"}
    bot.send_message(m.chat.id, "১️⃣ বটটা কি রকমের বট?\n\nনাম লিখো যেমন: `বিজনেস` / `TikTok Downloader`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 বট লিস্ট")
def list_bots(m):
    db = load_db()
    if not db: bot.send_message(m.chat.id, "❌ কোনো বট নাই।"); return
    txt="📋 **লিস্ট:**\n\n"
    for k,v in db.items(): txt+=f"• {v['name']}\n"
    bot.send_message(m.chat.id, txt, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑️ বট ডিলিট করুন")
def del_menu(m):
    db = load_db()
    mk = types.InlineKeyboardMarkup()
    for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"❌ {v['name']}", callback_data=f"del_{k}"))
    bot.send_message(m.chat.id, "ডিলিট করতে ক্লিক করো:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del_"))
def del_do(c):
    if c.from_user.id!= ADMIN_ID: return
    k = c.data.split("del_")[1]
    db = load_db()
    if k in db: del db[k]; save_db(db)
    bot.send_message(c.message.chat.id, f"🗑️ ডিলিট হয়েছে: {k}")
    bot.answer_callback_query(c.id)

# ========= MAIN HANDLER (BUG FIX) =========
@bot.message_handler(func=lambda m: True)
def all_handler(m):
    # ADMIN ADD FLOW
    if m.from_user.id == ADMIN_ID and m.from_user.id in admin_step:
        st = admin_step[m.from_user.id]
        if st["step"] == "name":
            st["name"] = m.text.strip()
            st["step"] = "code"
            bot.send_message(m.chat.id, f"✅ নাম: **{st['name']}**\n\n২️⃣ এখন পুরো Python কোড পাঠাও\n\n⚠️ টোকেনের জায়গায় `{TOKEN}` লিখতে হবে", parse_mode="Markdown")
            return
        elif st["step"] == "code":
            db = load_db()
            bot_id = st["name"].lower().replace(" ", "_")[:30]
            db[bot_id] = {"name": st["name"], "code": m.text}
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **Save Done!**\n\nনাম: {st['name']}\n\nএখন ইউজার 'বট চালু করুন' এ এটা পাবে।", reply_markup=admin_kb(), parse_mode="Markdown")
            del admin_step[m.from_user.id]
            return

    # USER FLOW
    if m.text == "🤖 বট চালু করুন":
        db = load_db()
        if not db: bot.send_message(m.chat.id, "❌ এখনো কোনো বট এড করা হয়নি।"); return
        mk = types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(v['name'], callback_data=f"run_{k}"))
        bot.send_message(m.chat.id, "👇 কি রকমের বট চালু করবে?", reply_markup=mk)
        return

    if m.from_user.id in user_step and ":" in m.text:
        k = user_step[m.from_user.id]
        db = load_db()
        if k not in db: return
        code = db[k]['code'].replace("{TOKEN}", m.text.strip())
        fname = f"hosted_{m.from_user.id}_{k}.py"
        with open(fname, 'w', encoding='utf-8') as f: f.write(code)
        try:
            subprocess.Popen(["python", fname])
            bot.send_message(m.chat.id, f"✅ **{db[k]['name']}** রান হয়েছে! 🟢 24/7")
        except Exception as e:
            bot.send_message(m.chat.id, f"❌ Error: {e}")
        del user_step[m.from_user.id]
        return

@bot.callback_query_handler(func=lambda c: c.data.startswith("run_"))
def ask_token(c):
    k = c.data.split("run_")[1]
    user_step[c.from_user.id] = k
    db = load_db()
    bot.send_message(c.message.chat.id, f"✅ **{db[k]['name']}** সিলেক্ট করেছো\n\nএখন তোমার Bot Token দাও:")
    bot.answer_callback_query(c.id)

from flask import Flask
app = Flask(__name__)
@app.route('/')
def home(): return "Live"
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
