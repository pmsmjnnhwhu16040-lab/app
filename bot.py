import os, json, telebot, threading, subprocess
from telebot import types

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN)
DB = "templates.json"

def load_db():
    if not os.path.exists(DB):
        with open(DB, 'w') as f: json.dump({}, f)
    with open(DB, 'r') as f: return json.load(f)

def save_db(data):
    with open(DB, 'w') as f: json.dump(data, f, indent=2)

user_state = {}
admin_state = {}

def user_kb():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add("🤖 বট চালু করুন")
    return mk

def admin_kb():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add("➕ বট এড করুন", "📋 বট লিস্ট")
    mk.add("🗑️ বট ডিলিট করুন")
    return mk

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id == ADMIN_ID:
        bot.send_message(m.chat.id, "👑 **ADMIN PANEL**\n\nবটের নাম আর কোড এড করুন।\nইউজার শুধু টোকেন দিয়ে রান করবে।", reply_markup=admin_kb(), parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "👋 স্বাগতম!\nবট হোস্ট করতে নিচের বাটনে চাপ দাও।", reply_markup=user_kb())

# ===== ADMIN: বট এড =====
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ বট এড করুন")
def admin_add(m):
    msg = bot.send_message(m.chat.id, "১️⃣ বটটা কি রকমের বট?\n\nনাম লিখো, যেমন:\n`TikTok Downloader`\n`File Store Bot`\n`Auto Reply Bot`")
    bot.register_next_step_handler(msg, admin_add_code)

def admin_add_code(m):
    name = m.text.strip()
    admin_state[m.from_user.id] = name
    msg = bot.send_message(m.chat.id, f"✅ নাম: **{name}**\n\n২️⃣ এখন পুরো Python কোডটা পাঠাও।\n\n⚠️ টোকেনের জায়গায় `{TOKEN}` লিখবে\nযেমন: `TeleBot('{TOKEN}')`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_save)

def admin_save(m):
    name = admin_state[m.from_user.id]
    code = m.text
    db = load_db()
    # নাম দিয়েই ID বানাবো
    bot_id = name.lower().replace(" ", "_")
    db[bot_id] = {"name": name, "code": code}
    save_db(db)
    bot.send_message(m.chat.id, f"✅ **Save Done!**\n\nনাম: {name}\nID: {bot_id}\n\nএখন ইউজাররা এটা দেখতে পাবে।", reply_markup=admin_kb(), parse_mode="Markdown")
    del admin_state[m.from_user.id]

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 বট লিস্ট")
def admin_list(m):
    db = load_db()
    if not db:
        bot.send_message(m.chat.id, "❌ কোনো বট এড করা নাই।")
        return
    txt = "📋 **তোমার এড করা বট:**\n\n"
    for k,v in db.items():
        txt += f"• {v['name']} (`{k}`)\n"
    bot.send_message(m.chat.id, txt, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🗑️ বট ডিলিট করুন")
def admin_del(m):
    db = load_db()
    mk = types.InlineKeyboardMarkup()
    for k,v in db.items():
        mk.add(types.InlineKeyboardButton(f"❌ {v['name']}", callback_data=f"del_{k}"))
    bot.send_message(m.chat.id, "ডিলিট করতে ক্লিক করো:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del_") and c.from_user.id == ADMIN_ID)
def del_done(c):
    k = c.data.split("del_")[1]
    db = load_db()
    if k in db:
        del db[k]
        save_db(db)
        bot.send_message(c.message.chat.id, f"🗑️ {k} ডিলিট হয়েছে")
    bot.answer_callback_query(c.id)

# ===== USER: বট চালু =====
@bot.message_handler(func=lambda m: m.text == "🤖 বট চালু করুন")
def user_choose(m):
    db = load_db()
    if not db:
        bot.send_message(m.chat.id, "❌ এখনো কোনো বট এড করা হয়নি।")
        return
    mk = types.InlineKeyboardMarkup(row_width=1)
    for k,v in db.items():
        mk.add(types.InlineKeyboardButton(v['name'], callback_data=f"run_{k}"))
    bot.send_message(m.chat.id, "👇 কি রকমের বট চালু করবে সিলেক্ট করো:", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("run_"))
def user_token(c):
    k = c.data.split("run_")[1]
    user_state[c.from_user.id] = k
    bot.send_message(c.message.chat.id, f"✅ **{load_db()[k]['name']}** সিলেক্ট করেছো\n\nএখন তোমার Bot Token দাও:", parse_mode="Markdown")
    bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: m.from_user.id in user_state and ":" in m.text)
def user_deploy(m):
    k = user_state[m.from_user.id]
    token = m.text.strip()
    db = load_db()
    code = db[k]['code'].replace("{TOKEN}", token)
    fname = f"hosted_{m.from_user.id}_{k}.py"
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(code)
    subprocess.Popen(["python", fname])
    bot.send_message(m.chat.id, f"✅ **{db[k]['name']}** রান হয়েছে!\n🟢 Live 24/7\n\nতোমার বটে গিয়ে /start দাও।")
    del user_state[m.from_user.id]

# Flask for Render
from flask import Flask
app = Flask(__name__)
@app.route('/')
def home(): return "OK"
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
