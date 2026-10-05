import os, json, telebot, threading, time
from telebot import types
from flask import Flask

TOKEN = os.getenv("BOT_TOKEN")
ADMIN = 8933985337
bot = telebot.TeleBot(TOKEN)

os.makedirs("hosted", exist_ok=True)
if not os.path.exists("templates.json"):
    with open("templates.json","w") as f: json.dump({},f)
if not os.path.exists("users.json"):
    with open("users.json","w") as f: json.dump({},f)

def load(p):
    try: return json.load(open(p,'r',encoding='utf-8'))
    except: return {}
def save(p,d):
    json.dump(d, open(p,'w',encoding='utf-8'), indent=2, ensure_ascii=False)

admin_state={}
user_state={}

def run_bot(token, code_text):
    try:
        code_text = code_text.replace("TOKENHERE", token)
        exec(code_text, {"__name__":"__main__"})
    except Exception as e:
        print(f"Bot Error: {e}")

def user_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন","📋 আমার বট")
    kb.row("🗑️ বট বন্ধ করুন")
    return kb

def admin_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন","📋 বট লিস্ট")
    kb.row("♻️ রিসেট DB")
    kb.row("🤖 বট চালু করুন","📋 আমার বট","🗑️ বট বন্ধ করুন")
    return kb

@bot.message_handler(commands=['start'])
def start_cmd(m):
    bot.send_message(m.chat.id, "👋 SK HOSTING READY\n\n🤖 বট চালু করুন - ক্লিক করুন", reply_markup=user_kb())

@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if m.from_user.id!= ADMIN:
        return
    bot.send_message(m.chat.id, "👑 ADMIN PANEL", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: True)
def handle(m):
    uid=m.from_user.id
    txt=m.text.strip()
    su=str(uid)

    if uid==ADMIN and txt=="➕ বট এড করুন":
        admin_state[uid]="name"
        bot.send_message(m.chat.id,"বটের নাম লিখুন:")
        return

    if uid==ADMIN and txt=="📋 বট লিস্ট":
        db=load("templates.json")
        if not db:
            bot.send_message(m.chat.id,"খালি")
        else:
            for v in db.values():
                bot.send_message(m.chat.id, f"📦 {v['name']}")
        return

    if uid==ADMIN and txt=="♻️ রিসেট DB":
        save("templates.json",{})
        save("users.json",{})
        bot.send_message(m.chat.id,"✅ রিসেট Done")
        return

    if uid==ADMIN and uid in admin_state:
        if admin_state[uid]=="name":
            admin_state[uid]="code"
            admin_state[f"{uid}_name"]=txt
            bot.send_message(m.chat.id,"এখন কোড দিন, টোকেনের জায়গায় TOKENHERE লিখবেন")
            return
        if admin_state[uid]=="code":
            db=load("templates.json")
            bid=str(int(time.time()))
            db[bid]={"name":admin_state[f"{uid}_name"], "code":m.text}
            save("templates.json",db)
            del admin_state[uid]
            bot.send_message(m.chat.id, f"✅ সেভ হয়েছে: {db[bid]['name']}", reply_markup=admin_kb())
            return

    if txt=="🤖 বট চালু করুন":
        db=load("templates.json")
        if not db:
            bot.send_message(m.chat.id,"কোনো বট এড করা হয়নি। /admin > ➕ বট এড করুন")
            return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items():
            mk.add(types.InlineKeyboardButton(f"🚀 {v['name']}", callback_data=f"RUN_{k}"))
        bot.send_message(m.chat.id,"কোন বট চালু করবেন?", reply_markup=mk)
        return

    if uid in user_state:
        bkey=user_state[uid]
        db=load("templates.json")
        if bkey not in db:
            bot.send_message(m.chat.id,"টেমপ্লেট নাই")
            del user_state[uid]
            return
        code=db[bkey]["code"]
        threading.Thread(target=run_bot, args=(txt, code), daemon=True).start()
        udb=load("users.json")
        udb.setdefault(su,{})[bkey]={"name":db[bkey]["name"]}
        save("users.json",udb)
        bot.send_message(m.chat.id, f"✅ {db[bkey]['name']} চালু হয়েছে! 5 সেকেন্ড পর আপনার বটে /start দিন", reply_markup=user_kb())
        del user_state[uid]

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.data.startswith("RUN_"):
        user_state[c.from_user.id]=c.data[4:]
        bot.send_message(c.message.chat.id,"এখন আপনার Bot Token দিন (BotFather থেকে /newbot):")
        bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home():
    return "OK - Bot Hosting Live"

threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
