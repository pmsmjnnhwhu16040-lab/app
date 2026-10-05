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
                proc=subprocess.Popen([sys.executable, fp])
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

def admin_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন","📋 বট লিস্ট")
    kb.row("🤖 বট চালু করুন","📋 আমার বট")
    kb.row("🗑️ বট বন্ধ করুন","♻️ রিসেট DB")
    return kb
def user_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন","📋 আমার বট")
    kb.row("🗑️ বট বন্ধ করুন")
    return kb

@bot.message_handler(commands=['start'])
def s(m):
    kb=admin_kb() if m.from_user.id==ADMIN_ID else user_kb()
    bot.send_message(m.chat.id,"🔥 **SK HOSTING PRO - POWERFUL**\n\n✅ Multi-Bot\n✅ Auto Restart\n\nমেনু সিলেক্ট করুন:",reply_markup=kb,parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def h(m):
    uid=m.from_user.id; txt=m.text.strip(); su=str(uid); is_ad=uid==ADMIN_ID
    if is_ad and txt=="➕ বট এড করুন":
        admin_state[uid]={"step":"name"}; bot.send_message(m.chat.id,"১️⃣ বটের নাম লিখুন:"); return
    if is_ad and uid in admin_state:
        st=admin_state[uid]
        if st["step"]=="name":
            st["name"]=txt; st["step"]="code"; bot.send_message(m.chat.id,f"নাম: {txt}\n\nএখন কোড দিন, {{TOKEN}} লিখবেন"); return
        if st["step"]=="code":
            db=load("templates.json"); bid=f"b{len(db)+1}"
            db[bid]={"name":st["name"],"code":m.text}; save("templates.json",db)
            bot.send_message(m.chat.id,f"✅ সেভ: {st['name']}",reply_markup=admin_kb()); del admin_state[uid]; return
    if txt=="📋 বট লিস্ট" and is_ad:
        db=load("templates.json"); msg="\n".join([f"{v['name']}" for v in db.values()]) or "খালি"
        bot.send_message(m.chat.id,f"📋 {msg}"); return
    if txt=="♻️ রিসেট DB" and is_ad:
        save("templates.json",{}); save("user_bots.json",{}); bot.send_message(m.chat.id,"✅ রিসেট"); return
    if txt=="🤖 বট চালু করুন":
        db=load("templates.json")
        if not db: bot.send_message(m.chat.id,"❌ কোনো বট নাই"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(f"🚀 {v['name']}",callback_data=f"RUN_{k}"))
        bot.send_message(m.chat.id,"সিলেক্ট করুন (এড বট):",reply_markup=mk); return
    if txt=="📋 আমার বট":
        udb=load("user_bots.json"); my=udb.get(su,{})
        if not my: bot.send_message(m.chat.id,"❌ রানিং নাই"); return
        bot.send_message(m.chat.id,"\n".join([f"🟢 {v['name']}" for v in my.values()])); return
    if txt=="🗑️ বট বন্ধ করুন":
        udb=load("user_bots.json"); my=udb.get(su,{})
        if not my: bot.send_message(m.chat.id,"❌ বন্ধ করার মত নাই"); return
        mk=types.InlineKeyboardMarkup(row_width=1)
        for k,v in my.items(): mk.add(types.InlineKeyboardButton(f"🛑 {v['name']}",callback_data=f"STOP_{k}"))
        bot.send_message(m.chat.id,"কোনটা বন্ধ (ডিলিট বট):",reply_markup=mk); return
    if uid in user_state:
        token=txt
        if ":" not in token: bot.send_message(m.chat.id,"❌ ভুল টোকেন"); return
        bkey=user_state[uid]; db=load("templates.json")
        code=db[bkey]["code"].replace("{TOKEN}",token).replace("{{TOKEN}}",token)
        fname=f"hosted/bot_{su}_{bkey}.py"
        with open(fname,'w',encoding='utf-8') as f: f.write(code)
        launch_bot(fname)
        udb=load("user_bots.json"); udb.setdefault(su,{})[bkey]={"name":db[bkey]["name"],"file":fname}
        save("user_bots.json",udb)
        bot.send_message(m.chat.id,f"✅ {db[bkey]['name']} চালু হয়েছে! এখন বটে /start দিন।")
        del user_state[uid]

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    su=str(c.from_user.id)
    if c.data.startswith("RUN_"):
        user_state[c.from_user.id]=c.data[4:]; bot.send_message(c.message.chat.id,"✅ সিলেক্ট\n\nএখন টোকেন দিন (নতুন টোকেন, আগেরটা না):"); bot.answer_callback_query(c.id)
    elif c.data.startswith("STOP_"):
        k=c.data[5:]; udb=load("user_bots.json")
        if su in udb and k in udb[su]:
            try: os.remove(udb[su][k]["file"])
            except: pass
            del udb[su][k]; save("user_bots.json",udb)
            bot.send_message(c.message.chat.id,"🛑 বন্ধ হয়েছে")
        bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home(): return "POWERFUL LIVE"
threading.Thread(target=restore, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
