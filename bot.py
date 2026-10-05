import os, json, telebot, threading, subprocess, sys, time
from telebot import types
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8933985337
bot = telebot.TeleBot(BOT_TOKEN)

os.makedirs("hosted", exist_ok=True)
for f in ["templates.json", "user_bots.json"]:
    if not os.path.exists(f):
        with open(f,'w') as fp: json.dump({},fp)

def load(p):
    try: return json.load(open(p,'r',encoding='utf-8'))
    except: return {}
def save(p,d): json.dump(d, open(p,'w',encoding='utf-8'), indent=2, ensure_ascii=False)

admin_state={}; user_state={}; processes={}

def launch_bot(fp):
    def run():
        while True:
            try:
                proc=subprocess.Popen([sys.executable, fp])
                processes[fp]=proc
                proc.wait()
                time.sleep(3)
            except: time.sleep(5)
    threading.Thread(target=run, daemon=True).start()

def user_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন","📋 আমার বট")
    kb.row("🗑️ বট বন্ধ করুন")
    return kb
def admin_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন","📋 বট লিস্ট")
    kb.row("🗑️ টেমপ্লেট ডিলিট","♻️ রিসেট DB")
    kb.row("🤖 বট চালু করুন","📋 আমার বট","🗑️ বট বন্ধ করুন")
    return kb

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id,"👋 SK HOSTING LIVE\n\n🤖 বট চালু করুন - নতুন বট\n📋 আমার বট - লিস্ট",reply_markup=user_kb())

@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if m.from_user.id!=ADMIN_ID: return
    bot.send_message(m.chat.id,"👑 ADMIN PANEL",reply_markup=admin_kb())

@bot.message_handler(func=lambda m: True)
def handler(m):
    uid=m.from_user.id; txt=m.text.strip(); su=str(uid); is_admin=uid==ADMIN_ID
    if is_admin and txt=="➕ বট এড করুন":
        admin_state[uid]={"step":"name"}; bot.send_message(m.chat.id,"নাম লিখুন:"); return
    if is_admin and txt=="📋 বট লিস্ট":
        db=load("templates.json"); bot.send_message(m.chat.id,str(list(db.values())) or "খালি"); return
    if is_admin and txt=="♻️ রিসেট DB":
        save("templates.json",{}); save("user_bots.json",{}); bot.send_message(m.chat.id,"✅ রিসেট"); return
    if is_admin and txt=="🗑️ টেমপ্লেট ডিলিট":
        db=load("templates.json"); mk=types.InlineKeyboardMarkup()
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(v['name'],callback_data="DEL_"+k))
        bot.send_message(m.chat.id,"ডিলিট সিলেক্ট:",reply_markup=mk); return
    if is_admin and uid in admin_state:
        st=admin_state[uid]
        if st["step"]=="name":
            st["name"]=txt; st["step"]="code"
            bot.send_message(m.chat.id,"এখন কোড দিন। টোকেনের জায়গায় TOKENHERE লিখবেন"); return
        if st["step"]=="code":
            db=load("templates.json"); bid=str(int(time.time()))
            db[bid]={"name":st["name"],"code":m.text}; save("templates.json",db)
            bot.send_message(m.chat.id,"✅ সেভ হয়েছে: "+st["name"],reply_markup=admin_kb())
            del admin_state[uid]; return
    if txt=="🤖 বট চালু করুন":
        db=load("templates.json")
        if not db: bot.send_message(m.chat.id,"কোনো টেমপ্লেট নাই"); return
        mk=types.InlineKeyboardMarkup()
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(v['name'],callback_data="RUN_"+k))
        bot.send_message(m.chat.id,"সিলেক্ট:",reply_markup=mk); return
    if txt=="📋 আমার বট":
        udb=load("user_bots.json"); bot.send_message(m.chat.id,str(udb.get(su,"খালি"))); return
    if txt=="🗑️ বট বন্ধ করুন":
        udb=load("user_bots.json"); my=udb.get(su,{})
        mk=types.InlineKeyboardMarkup()
        for k,v in my.items(): mk.add(types.InlineKeyboardButton(v['name'],callback_data="STOP_"+k))
        bot.send_message(m.chat.id,"বন্ধ করুন:",reply_markup=mk); return
    if uid in user_state:
        bkey=user_state[uid]; db=load("templates.json")
        code=db[bkey]["code"].replace("TOKENHERE",txt)
        fname=f"hosted/bot_{su}_{bkey}.py"
        open(fname,'w',encoding='utf-8').write(code)
        launch_bot(fname)
        udb=load("user_bots.json"); udb.setdefault(su,{})[bkey]={"name":db[bkey]["name"],"file":fname}; save("user_bots.json",udb)
        bot.send_message(m.chat.id,"✅ চালু হয়েছে! আপনার বটে /start দিন",reply_markup=user_kb())
        del user_state[uid]

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid=c.from_user.id; su=str(uid)
    if c.data.startswith("RUN_"):
        user_state[uid]=c.data[4:]; bot.send_message(c.message.chat.id,"টোকেন দিন:"); bot.answer_callback_query(c.id)
    elif c.data.startswith("STOP_"):
        k=c.data[5:]; udb=load("user_bots.json")
        if su in udb and k in udb[su]:
            try: os.remove(udb[su][k]["file"])
            except: pass
            del udb[su][k]; save("user_bots.json",udb)
            bot.send_message(c.message.chat.id,"🛑 বন্ধ")
        bot.answer_callback_query(c.id)
    elif c.data.startswith("DEL_") and uid==ADMIN_ID:
        k=c.data[4:]; db=load("templates.json"); db.pop(k,None); save("templates.json",db)
        bot.send_message(c.message.chat.id,"🗑️ ডিলিট"); bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home(): return "OK"
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
