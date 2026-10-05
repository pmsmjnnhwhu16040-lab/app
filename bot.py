import os, json, telebot, threading, subprocess, sys, signal
from telebot import types
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

DB_FILE = "templates.json"
USER_DB = "user_bots.json"

for f in [DB_FILE, USER_DB]:
    if not os.path.exists(f):
        with open(f, 'w', encoding='utf-8') as fp: json.dump({}, fp)

def load(f):
    try:
        with open(f,'r',encoding='utf-8') as fp: return json.load(fp)
    except: return {}
def save(f,d):
    with open(f,'w',encoding='utf-8') as fp: json.dump(d,fp,indent=2,ensure_ascii=False)

admin_state={}; user_state={}

def admin_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন", "📋 বট লিস্ট")
    kb.row("🗑️ বট ডিলিট করুন", "♻️ রিসেট DB")
    kb.row("🤖 বট চালু করুন")
    return kb

def user_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন", "📋 আমার বট")
    kb.row("🗑️ বট বন্ধ করুন")
    return kb

@bot.message_handler(commands=['start'])
def start_cmd(m):
    if m.from_user.id==ADMIN_ID:
        bot.send_message(m.chat.id, "👑 **ADMIN PANEL**\n\nইউজারদের জন্য বট এড করুন।", reply_markup=admin_kb(), parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "👋 **SK Hosting Pro তে স্বাগতম!**\n\n১. বট চালু করুন = নতুন বট হোস্ট (এড বট)\n২. বট বন্ধ করুন = হোস্ট করা বট বন্ধ (ডিলিট বট)", reply_markup=user_kb(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id==ADMIN_ID)
def admin_handler(m):
    t=m.text.strip()
    if t=="➕ বট এড করুন":
        admin_state[m.from_user.id]={"step":"name"}
        bot.send_message(m.chat.id,"১️⃣ বটের নাম লিখুন:\nযেমন: `seller`")
        return
    if t=="📋 বট লিস্ট":
        db=load(DB_FILE)
        msg="📋 **এড করা বট:**\n" + "\n".join([f"🔹 {v['name']}" for v in db.values()]) if db else "❌ খালি"
        bot.send_message(m.chat.id,msg)
        return
    if t=="🗑️ বট ডিলিট করুন":
        db=load(DB_FILE)
        mk=types.InlineKeyboardMarkup()
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"❌ {v['name']}",callback_data=f"DEL_{k}"))
        bot.send_message(m.chat.id,"ডিলিট করুন:",reply_markup=mk)
        return
    if t=="♻️ রিসেট DB": save(DB_FILE,{}); bot.send_message(m.chat.id,"✅ রিসেট হয়েছে"); return

    if m.from_user.id in admin_state:
        st=admin_state[m.from_user.id]
        if st["step"]=="name":
            st["name"]=t; st["step"]="code"
            bot.send_message(m.chat.id,f"✅ নাম: {t}\n\nএখন কোড দিন, `{'{TOKEN}'}` অবশ্যই দিবেন",parse_mode="Markdown")
            return
        if st["step"]=="code":
            db=load(DB_FILE); bid="".join(e for e in st['name'].lower() if e.isalnum())[:15]+str(len(db))
            db[bid]={"name":st["name"],"code":m.text}; save(DB_FILE,db)
            bot.send_message(m.chat.id,f"✅ **{st['name']}** সেভ হয়েছে!",reply_markup=admin_kb(),parse_mode="Markdown")
            del admin_state[m.from_user.id]; return

    # Admin can also run as user
    if t in ["🤖 বট চালু করুন","📋 আমার বট","🗑️ বট বন্ধ করুন"]:
        handle_user(m); return

def handle_user(m):
    t=m.text.strip()
    uid=str(m.from_user.id)
    if t=="🤖 বট চালু করুন":
        db=load(DB_FILE)
        if not db: bot.send_message(m.chat.id,"❌ Admin এখনো বট এড করেনি"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"🚀 {v['name']}",callback_data=f"RUN_{k}"))
        bot.send_message(m.chat.id,"👇 **কোন বট চালু করবেন (এড বট):**",reply_markup=mk,parse_mode="Markdown")
    elif t=="📋 আমার বট":
        udb=load(USER_DB); my=udb.get(uid,{})
        if not my: bot.send_message(m.chat.id,"❌ আপনার কোনো বট রানিং নাই"); return
        msg="📋 **আপনার রানিং বট:**\n\n" + "\n".join([f"🟢 {v['name']} - `{k}.py`" for k,v in my.items()])
        bot.send_message(m.chat.id,msg,parse_mode="Markdown")
    elif t=="🗑️ বট বন্ধ করুন":
        udb=load(USER_DB); my=udb.get(uid,{})
        if not my: bot.send_message(m.chat.id,"❌ বন্ধ করার মত বট নাই"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in my.items(): mk.add(types.InlineKeyboardButton(f"🛑 {v['name']} বন্ধ করুন",callback_data=f"STOP_{k}"))
        bot.send_message(m.chat.id,"কোন বট বন্ধ করবেন (ডিলিট বট):",reply_markup=mk)

@bot.message_handler(func=lambda m: m.from_user.id!=ADMIN_ID)
def user_handler(m):
    t=m.text.strip()
    uid=str(m.from_user.id)
    if t in ["🤖 বট চালু করুন","📋 আমার বট","🗑️ বট বন্ধ করুন"]:
        handle_user(m); return

    if m.from_user.id in user_state: # Token input
        token=t
        if ":" not in token: bot.send_message(m.chat.id,"❌ ভুল টোকেন"); return
        bkey=user_state[m.from_user.id]
        db=load(DB_FILE); code=db[bkey]["code"].replace("{TOKEN}",token).replace("{{TOKEN}}",token)
        fname=f"bot_{uid}_{bkey}.py"
        with open(fname,'w',encoding='utf-8') as f: f.write(code)
        subprocess.Popen([sys.executable, fname])
        # save to user db
        udb=load(USER_DB); udb.setdefault(uid,{})[bkey]={"name":db[bkey]["name"],"file":fname,"token":token}
        save(USER_DB,udb)
        bot.send_message(m.chat.id,f"✅ **{db[bkey]['name']}** রান হয়েছে! 🟢\n\nএড বট সফল!\nএখন /start দিন আপনার বটে।",parse_mode="Markdown")
        del user_state[m.from_user.id]

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid=str(c.from_user.id)
    if c.data.startswith("DEL_") and c.from_user.id==ADMIN_ID:
        k=c.data[4:]; db=load(DB_FILE); db.pop(k,None); save(DB_FILE,db)
        bot.send_message(c.message.chat.id,"🗑️ ডিলিট হয়েছে"); bot.answer_callback_query(c.id)
    elif c.data.startswith("RUN_"):
        k=c.data[4:]; user_state[c.from_user.id]=k
        db=load(DB_FILE)
        bot.send_message(c.message.chat.id,f"✅ **{db[k]['name']}** সিলেক্ট\n\nএখন Bot Token দিন:",parse_mode="Markdown")
        bot.answer_callback_query(c.id)
    elif c.data.startswith("STOP_"):
        k=c.data[5:]; udb=load(USER_DB)
        if uid in udb and k in udb[uid]:
            try: os.remove(udb[uid][k]["file"])
            except: pass
            del udb[uid][k]; save(USER_DB,udb)
            bot.send_message(c.message.chat.id,f"🛑 **বট বন্ধ হয়েছে!**\n\nডিলিট বট সফল। ফাইল ডিলিট করা হয়েছে।")
        bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home(): return "LIVE"
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True,timeout=60),daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
