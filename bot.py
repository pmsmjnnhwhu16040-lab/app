import os, json, telebot, threading, subprocess, sys, time
from telebot import types
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

os.makedirs("hosted", exist_ok=True)
for f in ["templates.json", "user_bots.json"]:
    if not os.path.exists(f):
        with open(f,'w',encoding='utf-8') as fp: json.dump({},fp)

def load(p):
    try: return json.load(open(p,'r',encoding='utf-8'))
    except: return {}
def save(p,d): json.dump(d, open(p,'w',encoding='utf-8'), indent=2, ensure_ascii=False)

admin_state={}; user_state={}; processes={}

def launch_bot(fp):
    def loop():
        while True:
            try:
                proc=subprocess.Popen([sys.executable, fp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes[fp]=proc
                proc.wait()
                time.sleep(3)
            except: time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()

def restore():
    time.sleep(3)
    udb=load("user_bots.json")
    for uid, bots in udb.items():
        for info in bots.values():
            if os.path.exists(info["file"]): launch_bot(info["file"])

def user_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন", "📋 আমার বট")
    kb.row("🗑️ বট বন্ধ করুন")
    return kb

def admin_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন", "📋 বট লিস্ট")
    kb.row("🗑️ টেমপ্লেট ডিলিট", "♻️ রিসেট DB")
    kb.row("📊 স্ট্যাটাস")
    kb.row("🤖 বট চালু করুন", "📋 আমার বট", "🗑️ বট বন্ধ করুন")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id,
        "👋 **SK HOSTING PRO**\n\n"
        "🤖 বট চালু করুন - নতুন বট হোস্ট করুন\n"
        "📋 আমার বট - আপনার রানিং বট দেখুন\n"
        "🗑️ বট বন্ধ করুন - বট বন্ধ করুন\n\n"
        "24/7 Online Hosting",
        reply_markup=user_kb(), parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if m.from_user.id!= ADMIN_ID:
        bot.send_message(m.chat.id, "❌ আপনি এডমিন না!")
        return
    bot.send_message(m.chat.id,
        "👑 **ADMIN PANEL - Welcome Boss**\n\n"
        "➕ বট এড করুন - নতুন টেমপ্লেট এড\n"
        "📋 বট লিস্ট - সব টেমপ্লেট দেখুন\n"
        "🗑️ টেমপ্লেট ডিলিট - টেমপ্লেট ডিলিট করুন\n"
        "♻️ রিসেট DB - সব ডিলিট\n"
        "📊 স্ট্যাটাস - সার্ভার স্ট্যাট",
        reply_markup=admin_kb(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handler(m):
    uid=m.from_user.id; txt=m.text.strip(); su=str(uid); is_admin=uid==ADMIN_ID

    # --- ADMIN ONLY PART ---
    if is_admin:
        if txt=="➕ বট এড করুন":
            admin_state[uid]={"step":"name"}
            bot.send_message(m.chat.id,"1️⃣ বটের নাম লিখুন:"); return
        if txt=="📋 বট লিস্ট":
            db=load("templates.json")
            if not db: bot.send_message(m.chat.id,"❌ কোনো টেমপ্লেট নাই"); return
            msg="\n".join([f"🔹 {v['name']} - ID:{k}" for k,v in db.items()])
            bot.send_message(m.chat.id,f"📋 **টেমপ্লেট লিস্ট:**\n{msg}",parse_mode="Markdown"); return
        if txt=="📊 স্ট্যাটাস":
            udb=load("user_bots.json"); tdb=load("templates.json")
            total=sum(len(v) for v in udb.values())
            bot.send_message(m.chat.id,f"📊 **STATUS**\n\n📦 টেমপ্লেট: {len(tdb)}\n🟢 রানিং বট: {total}\n⚙️ প্রসেস: {len(processes)}"); return
        if txt=="♻️ রিসেট DB":
            save("templates.json",{}); save("user_bots.json",{})
            bot.send_message(m.chat.id,"✅ সব ডাটা রিসেট হয়েছে!"); return
        if txt=="🗑️ টেমপ্লেট ডিলিট":
            db=load("templates.json")
            if not db: bot.send_message(m.chat.id,"❌ ডিলিট করার মত নাই"); return
            mk=types.InlineKeyboardMarkup(row_width=1)
            for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"❌ {v['name']}",callback_data=f"DEL_{k}"))
            bot.send_message(m.chat.id,"কোন টেমপ্লেট ডিলিট করবেন?",reply_markup=mk); return

        if uid in admin_state:
            st=admin_state[uid]
            if st["step"]=="name":
                st["name"]=txt; st["step"]="code"
                bot.send_message(m.chat.id,f"নাম: {txt}\n\nএখন কোড দিন, টোকেনের জায়গায় {{TOKEN}} লিখবেন"); return
            if st["step"]=="code":
                db=load("templates.json"); bid=f"b{len(db)+1}_{int(time.time())}"
                db[bid]={"name":st["name"],"code":m.text}; save("templates.json",db)
                bot.send_message(m.chat.id,f"✅ সেভ হয়েছে: {st['name']}\nID: {bid}",reply_markup=admin_kb())
                del admin_state[uid]; return

    # --- USER + ADMIN COMMON PART ---
    if txt=="🤖 বট চালু করুন":
        db=load("templates.json")
        if not db: bot.send_message(m.chat.id,"❌ এখনো কোনো বট এড করা হয়নি!"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"🚀 {v['name']}",callback_data=f"RUN_{k}"))
        bot.send_message(m.chat.id,"👇 কোন বট চালু করবেন সিলেক্ট করুন:",reply_markup=mk); return

    if txt=="📋 আমার বট":
        udb=load("user_bots.json"); my=udb.get(su,{})
        if not my: bot.send_message(m.chat.id,"❌ আপনার কোনো বট রানিং নাই"); return
        msg="\n".join([f"🟢 {v['name']}" for v in my.values()])
        bot.send_message(m.chat.id,f"📋 **আপনার রানিং বট:**\n{msg}"); return

    if txt=="🗑️ বট বন্ধ করুন":
        udb=load("user_bots.json"); my=udb.get(su,{})
        if not my: bot.send_message(m.chat.id,"❌ বন্ধ করার মত বট নাই"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in my.items(): mk.add(types.InlineKeyboardButton(f"🛑 {v['name']} বন্ধ করুন",callback_data=f"STOP_{k}"))
        bot.send_message(m.chat.id,"কোনটা বন্ধ করবেন?",reply_markup=mk); return

    if uid in user_state:
        token=txt
        if ":" not in token or len(token)<20:
            bot.send_message(m.chat.id,"❌ ভুল টোকেন! সঠিক টোকেন দিন"); return
        bkey=user_state[uid]; db=load("templates.json")
        if bkey not in db: bot.send_message(m.chat.id,"❌ এই টেমপ্লেট আর নাই"); del user_state[uid]; return
        code=db[bkey]["code"].replace("{TOKEN}",token).replace("{{TOKEN}}",token)
        fname=f"hosted/bot_{su}_{bkey}.py"
        with open(fname,'w',encoding='utf-8') as f: f.write(code)
        launch_bot(fname)
        udb=load("user_bots.json"); udb.setdefault(su,{})[bkey]={"name":db[bkey]["name"],"file":fname}
        save("user_bots.json",udb)
        bot.send_message(m.chat.id,f"✅ **{db[bkey]['name']}** চালু হয়েছে!\n\nআপনার বটে গিয়ে /start দিন\n🟢 24/7 Online থাকবে",reply_markup=user_kb())
        del user_state[uid]; return

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid=c.from_user.id; su=str(uid)
    if c.data.startswith("RUN_"):
        user_state[uid]=c.data[4:]
        db=load("templates.json")
        bname=db.get(c.data[4:],{}).get("name","Bot")
        bot.send_message(c.message.chat.id,f"✅ {bname} সিলেক্ট করেছেন\n\nএখন আপনার **Bot Token** দিন:\nBotFather > /newbot > token")
        bot.answer_callback_query(c.id)
    elif c.data.startswith("STOP_"):
        k=c.data[5:]; udb=load("user_bots.json")
        if su in udb and k in udb[su]:
            try: os.remove(udb[su][k]["file"])
            except: pass
            del udb[su][k]; save("user_bots.json",udb)
            bot.send_message(c.message.chat.id,"🛑 বট বন্ধ হয়েছে এবং ফাইল ডিলিট হয়েছে")
        bot.answer_callback_query(c.id)
    elif c.data.startswith("DEL_"):
        if uid!= ADMIN_ID: return
        k=c.data[4:]; db=load("templates.json"); db.pop(k,None); save("templates.json",db)
        bot.send_message(c.message.chat.id,f"🗑️ টেমপ্লেট ডিলিট হয়েছে")
        bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home(): return "SK HOSTING PRO LIVE"
threading.Thread(target=restore, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
