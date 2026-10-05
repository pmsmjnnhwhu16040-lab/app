import os, json, telebot, threading, sys, time, traceback
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

admin_state={}; user_state={}

def run_hosted_bot(token, code_str):
    try:
        # token replace
        final_code = code_str.replace("{TOKEN}", token).replace("{{TOKEN}}", token)
        # Direct exec in thread
        exec(final_code, {"__name__":"__main__"})
    except Exception as e:
        print(f"BOT CRASH {token[:10]}: {e}")
        traceback.print_exc()
        time.sleep(3)

def user_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🤖 বট চালু করুন","📋 আমার বট"); kb.row("🗑️ বট বন্ধ করুন"); return kb
def admin_kb():
    kb=types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ বট এড করুন","📋 বট লিস্ট"); kb.row("🗑️ টেমপ্লেট ডিলিট","♻️ রিসেট DB")
    kb.row("🤖 বট চালু করুন","📋 আমার বট","🗑️ বট বন্ধ করুন"); return kb

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id,"👋 SK HOSTING LIVE\n\n🤖 বট চালু করুন",reply_markup=user_kb())
@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if m.from_user.id!=ADMIN_ID: return
    bot.send_message(m.chat.id,"👑 ADMIN PANEL",reply_markup=admin_kb())

@bot.message_handler(func=lambda m: True)
def handler(m):
    uid=m.from_user.id; txt=m.text.strip(); su=str(uid); is_admin=uid==ADMIN_ID
    if is_admin and txt=="➕ বট এড করুন": admin_state[uid]={"step":"name"}; bot.send_message(m.chat.id,"নাম:"); return
    if is_admin and txt=="♻️ রিসেট DB": save("templates.json",{}); save("user_bots.json",{}); bot.send_message(m.chat.id,"✅ রিসেট"); return
    if is_admin and txt=="🗑️ টেমপ্লেট ডিলিট":
        db=load("templates.json"); mk=types.InlineKeyboardMarkup()
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(v['name'],callback_data="DEL_"+k))
        bot.send_message(m.chat.id,"ডিলিট:",reply_markup=mk); return
    if is_admin and uid in admin_state:
        st=admin_state[uid]
        if st["step"]=="name": st["name"]=txt; st["step"]="code"; bot.send_message(m.chat.id,"কোড দিন, {TOKEN} লিখবেন:"); return
        if st["step"]=="code":
            db=load("templates.json"); bid=str(int(time.time()))
            db[bid]={"name":st["name"],"code":m.text}; save("templates.json",db)
            bot.send_message(m.chat.id,"✅ সেভ: "+st["name"],reply_markup=admin_kb()); del admin_state[uid]; return
    if txt=="🤖 বট চালু করুন":
        db=load("templates.json")
        if not db: bot.send_message(m.chat.id,"কোনো টেমপ্লেট নাই"); return
        mk=types.InlineKeyboardMarkup()
        for k,v in db.items(): mk.add(types.InlineKeyboardButton(v['name'],callback_data="RUN_"+k))
        bot.send_message(m.chat.id,"সিলেক্ট:",reply_markup=mk); return
    if txt=="📋 আমার বট":
        udb=load("user_bots.json"); bot.send_message(m.chat.id,str(list(udb.get(su,{}).values())) or "নাই"); return
    if txt=="🗑️ বট বন্ধ করুন":
        udb=load("user_bots.json"); my=udb.get(su,{})
        if not my: bot.send_message(m.chat.id,"নাই"); return
        mk=types.InlineKeyboardMarkup()
        for k,v in my.items(): mk.add(types.InlineKeyboardButton(v['name'],callback_data="STOP_"+k))
        bot.send_message(m.chat.id,"বন্ধ:",reply_markup=mk); return
    if uid in user_state:
        bkey=user_state[uid]; db=load("templates.json")
        if bkey not in db: bot.send_message(m.chat.id,"টেমপ্লেট নাই"); del user_state[uid]; return
        code = db[bkey]["code"]
        # launch in thread
        threading.Thread(target=run_hosted_bot, args=(txt, code), daemon=True).start()
        udb=load("user_bots.json"); udb.setdefault(su,{})[bkey]={"name":db[bkey]["name"],"token":txt[:15]}; save("user_bots.json",udb)
        bot.send_message(m.chat.id,f"✅ {db[bkey]['name']} LIVE! এখন আপনার বটে /start দিন। 5 সেকেন্ড অপেক্ষা করুন।",reply_markup=user_kb())
        del user_state[uid]

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    uid=c.from_user.id; su=str(uid)
    if c.data.startswith("RUN_"): user_state[uid]=c.data[4:]; bot.send_message(c.message.chat.id,"✅ টোকেন দিন (নতুন BotFather টোকেন, Hosting বটের টোকেন না):"); bot.answer_callback_query(c.id)
    elif c.data.startswith("STOP_"):
        k=c.data[5:]; udb=load("user_bots.json")
        if su in udb and k in udb[su]: del udb[su][k]; save("user_bots.json",udb); bot.send_message(c.message.chat.id,"🛑 বন্ধ (Render Restart দিলে পুরো বন্ধ হবে)")
        bot.answer_callback_query(c.id)
    elif c.data.startswith("DEL_") and uid==ADMIN_ID:
        k=c.data[4:]; db=load("templates.json"); db.pop(k,None); save("templates.json",db); bot.send_message(c.message.chat.id,"🗑️ ডিলিট"); bot.answer_callback_query(c.id)

app=Flask(__name__)
@app.route('/')
def home(): return "LIVE"
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
