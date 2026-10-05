import os, json, telebot, threading, subprocess, sys, time, traceback
from telebot import types
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

os.makedirs("hosted", exist_ok=True)
for f in ["templates.json", "user_bots.json", "error.log"]:
    if not os.path.exists(f):
        with open(f,'w',encoding='utf-8') as fp: fp.write("{}" if ".json" in f else "")

def load(p):
    try: return json.load(open(p,'r',encoding='utf-8'))
    except: return {}
def save(p,d): json.dump(d, open(p,'w',encoding='utf-8'), indent=2, ensure_ascii=False)

admin_state={}; user_state={}; processes={}

def launch_bot(fp):
    def loop():
        while True:
            try:
                # log file এ error লিখবে
                with open("error.log","a",encoding="utf-8") as log:
                    proc = subprocess.Popen([sys.executable, fp], stdout=log, stderr=log)
                processes[fp]=proc
                proc.wait()
                time.sleep(3)
            except Exception as e:
                open("error.log","a").write(f"\n{fp} CRASH: {e}\n{traceback.format_exc()}\n")
                time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()

def restore():
    time.sleep(4)
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
    kb.row("➕ বট এড করুন","📋 বট লিস্ট")
    kb.row("🗑️ টেমপ্লেট ডিলিট","♻️ রিসেট DB")
    kb.row("📊 স্ট্যাটাস","📜 Error Log")
    kb.row("🤖 বট চালু করুন","📋 আমার বট","🗑️ বট বন্ধ করুন")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id,"👋 SK HOSTING PRO\n\n🤖 বট চালু করুন - হোস্ট করুন\n📋 আমার বট - লিস্ট\n🗑️ বট বন্ধ করুন - বন্ধ করুন",reply_markup=user_kb())

@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if m.from_user.id!=ADMIN_ID: bot.send_message(m.chat.id,"❌ Admin না"); return
    bot.send_message(m.chat.id,"👑 ADMIN PANEL",reply_markup=admin_kb())

@bot.message_handler(func=lambda m: True)
def handler(m):
    uid=m.from_user.id; txt=m.text.strip(); su=str(uid); is_admin=uid==ADMIN_ID
    if is_admin:
        if txt=="➕ বট এড করুন": admin_state[uid]={"step":"name"}; bot.send_message(m.chat.id,"1️⃣ নাম লিখুন:"); return
        if txt=="📋 বট লিস্ট":
            db=load("templates.json"); msg="\n".join([f"{v['name']}" for v in db.values()]) or "খালি"
            bot.send_message(m.chat.id,f"📋 {msg}"); return
        if txt=="📜 Error Log":
            try: log=open("error.log","r",encoding="utf-8").read()[-3000:]
            except: log="No log"
            bot.send_message(m.chat.id,f"📜 LOG:\n{log or 'No Error'}"); return
        if txt=="📊 স্ট্যাটাস":
            udb=load("user_bots.json"); tdb=load("templates.json"); total=sum(len(v) for v in udb.values())
            bot.send_message(m.chat.id,f"📦 টেমপ্লেট: {len(tdb)}\n🟢 রানিং: {total}"); return
        if txt=="♻️ রিসেট DB": save("templates.json",{}); save("user_bots.json",{}); bot.send_message(m.chat.id,"✅ রিসেট"); return
        if txt=="🗑️ টেমপ্লেট ডিলিট":
            db=load("templates.json"); mk=types.InlineKeyboardMarkup(row_width=1)
            for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"❌ {v['name']}",callback_data=f"DEL_{k}"))
            bot.send_message(m.chat.id,"কোনটা ডিলিট?",reply_markup=mk); return
        if uid in admin_state:
            st=admin_state[uid]
            if st["step"]=="name": st["name"]=txt; st["step"]="code"; bot.send_message(m.chat.id,f"নাম: {txt}\n\nএখন কোড দিন, {{TOKEN}} লিখবেন"); return
            if st["step"]=="code":
                db=load("templates.json"); bid=f"b{int(time.time())}"
                db[bid]={"name":st["name"],"code":m.text}; save("templates.json",db)
                bot.send_message(m.chat.id,f"✅ সেভ: {st['name']}",reply_markup=admin_kb()); del admin_state[uid]; return
    if txt=="🤖 বট চালু করুন":
        db=load("templates.json")
        if not db: bot.send_message(m.chat.id,"❌ কোনো বট এড করা হয়নি, /admin > ➕ বট এড করুন"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"🚀 {v['name']}",callback_data=f"RUN_{k}"))
        bot.send_message(m.chat.id,"সিলেক্ট করুন:",reply_markup=mk); return
    if txt=="📋 আমার বট":
        udb=load("user_bots.json"); my=udb.get(su,{}); bot.send_message(m.chat.id,"\n".join([f"🟢 {v['name']}" for v in my.values()]) or "❌ নাই"); return
    if txt=="🗑️ বট বন্ধ করুন":
        udb=load("user_bots.json"); my=udb.get(su,{})
        if not my: bot.send_message(m.chat.id,"❌ নাই"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in my.items(): mk.add(types.InlineKeyboardButton(f"🛑 {v['name']}",callback_data=f"STOP_{k}"))
        bot.send_message(m.chat.id,"কোনটা বন্ধ?",reply_markup=mk); return
    if uid in user_state:
        token=txt
        if ":" not in token: bot.send_message(m.chat.id,"❌ ভুল টোকেন"); return
        bkey=user_state[uid]; db=load("templates.json")
        code=db[bkey]["code"].replace("{TOKEN}",token).replace("{{TOKEN}}",token)
        fname=f"hosted/bot_{su}_{bkey}.py"
        with open(fname,'w',encoding='utf-8') as f: f.write(code)
        launch_bot(fname)
        udb=load("user_bots.json"); udb.setdefault(su,{})[bkey]={"name":db[bkey]["name"],"file":fname}; save("user_bots.json",udb)
        bot.send_message(m.chat.id,f"✅ {db[bkey]['name']} চালু! 10 সেকেন্ড পর /start দিন।\n\nযদি না চলে: /admin > 📜 Error Log",reply_markup=user_kb())
        del user_state[uid]

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid=c.from_user.id; su=str(uid)
    if c.data.startswith("RUN_"): user_state[uid]=c.data[4:]; bot.send_message(c.message.chat.id,"✅ এখন Bot Token দিন (BotFather থেকে নতুন):"); bot.answer_callback_query(c.id)
    elif c.data.startswith("STOP_"):
        k=c.data[5:]; udb=load("user_bots.json")
        if su in udb and k in udb[su]:
            try: os.remove(udb[su][k]["file"])
            except: pass
            del udb[su][k]; save("user_bots.json",udb); bot.send_message(c.message.chat.id,"🛑 বন্ধ হয়েছে")
        bot.answer_callback_query(c.id)
    elif c.data.startswith("DEL_") and uid==ADMIN_ID:
        k=c.data[4:]; db=load("templates.json"); db.pop(k,None); save("templates.json",db); bot.send_message(c.message.chat.id,"🗑️ ডিলিট"); bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home(): return "LIVE"
threading.Thread(target=restore, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
