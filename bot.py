import asyncio
import contextvars
import hashlib
import html
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramUnauthorizedError
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

logging.basicConfig(level=logging.INFO)

# ============================== কনফিগ ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "___")
ADMIN_ID = 8918465399  # মূল অ্যাডমিন (Owner) - শুধু ইনি অ্যাডমিন যোগ/বাদ দিতে পারবেন
DB_FILE = "data.json"
BOT_USERNAME = ""  # main() এ সেট হয়
BACK_TEXT = "🔙 পিছনে যান"
CANCEL_TEXT = "❌ বাতিল করুন"
TZ = timezone(timedelta(hours=6))  # বাংলাদেশ সময়

# ---------- মাল্টি-বট (মূল বট থেকে নতুন বট বানানো) ----------
BOTS_DIR = "bots"  # প্রতিটি নতুন বটের আলাদা ডাটা ফাইল এখানে থাকে
BTN_ADD_BOT = "➕ এড বট"
BTN_MY_BOTS = "🤖 আমার বট"
BTN_DEL_BOT = "🗑 ডিলিট বট"
BOT_BTNS = (BTN_ADD_BOT, BTN_MY_BOTS, BTN_DEL_BOT)
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


class BotCtx:
    """একটি বটের পরিচয়: আলাদা ডাটা ফাইল, আলাদা Owner, আলাদা ইউজারনেম"""

    def __init__(self, key, db_file, owner, token, is_main=False, username=""):
        self.key = key
        self.db_file = db_file
        self.owner_id = owner
        self.token = token
        self.is_main = is_main
        self.username = username


MAIN_CTX = BotCtx("main", DB_FILE, ADMIN_ID, BOT_TOKEN, True)
CUR_BOT = contextvars.ContextVar("cur_bot", default=None)
RUNNING = {}  # key -> {"task": Task, "bot": Bot}
DP = None  # main() এ সেট হয়


def cur():
    return CUR_BOT.get() or MAIN_CTX


def owner_id():
    return cur().owner_id

COLORS = {
    "blue": ("🔵 নীল", "primary"),
    "green": ("🟢 সবুজ", "success"),
    "red": ("🔴 লাল", "danger"),
    "none": ("⚪ ডিফল্ট", None),
}

KINDS = {
    "text": "📝 শুধু মেসেজ দেখাবে",
    "input": "📥 ইউজারের কাছ থেকে ইনপুট নেবে (লেখা / ছবি)",
    "tasks": "🎯 টাস্ক লিস্ট দেখাবে",
    "balance": "💰 ব্যালেন্স দেখাবে",
    "refer": "🎁 রেফার লিংক দেখাবে",
    "withdraw": "💸 উইথড্র রিকোয়েস্ট",
    "history": "📜 ইউজারের হিস্টোরি",
    "support": "☎️ সাপোর্ট",
    "shop": "🛒 শপ / প্রোডাক্ট ক্যাটালগ (বিজনেস বট)",
    "shopcat": "📂 নির্দিষ্ট ক্যাটাগরির প্রডাক্ট লিস্ট দেখাবে",
    "addmoney": "➕ এড মানি (Transaction ID দিয়ে)",
    "cart": "🧺 কার্ট দেখাবে",
    "orders": "🧾 অর্ডার হিস্টোরি",
    "wallet": "👛 ওয়ালেট (ব্যালেন্স + খরচ + লেনদেন)",
    "profile": "👤 ইউজার প্রোফাইল",
    "refund": "♻️ রিফান্ড রিকোয়েস্ট",
    "ticket": "🆘 সাপোর্টে মেসেজ পাঠানো (ইউজার → অ্যাডমিন)",
}

# প্লেসহোল্ডার: {balance} {refs} {link} {bonus} {currency} {min} {name} {id} {support} {bot} {methods}
LINE = "━━━━━━━━━━━━━━━━"

DEFAULT_MSGS = {
    "balance": (
        "💎 <b>আপনার ওয়ালেট</b>\n"
        f"{LINE}\n"
        "👤 <b>{name}</b>\n"
        "🆔 {id}\n\n"
        "💰 <b>বর্তমান ব্যালেন্স</b>\n"
        "➤ <b>{balance} {currency}</b>\n\n"
        "👥 মোট রেফার: <b>{refs}</b> জন\n"
        "💳 ন্যূনতম উইথড্র: <b>{min} {currency}</b>\n"
        f"{LINE}\n"
        "✨ আরও আয় করতে টাস্ক সম্পন্ন করুন ও বন্ধুদের রেফার করুন!"
    ),
    "refer": (
        "🎁 <b>রেফার করুন, আয় করুন!</b>\n"
        f"{LINE}\n"
        "🔗 <b>আপনার ইনভাইট লিংক</b>\n"
        "{link}\n\n"
        "🎯 প্রতি সফল রেফারে পাবেন <b>{bonus} {currency}</b>\n"
        "👥 এখন পর্যন্ত রেফার: <b>{refs}</b> জন\n"
        f"{LINE}\n"
        "📤 লিংকটি বন্ধুদের শেয়ার করুন। বন্ধু জয়েন করলেই বোনাস আপনার ব্যালেন্সে যোগ হবে!"
    ),
    "withdraw": (
        "💸 <b>উইথড্র রিকোয়েস্ট</b>\n"
        f"{LINE}\n"
        "💰 আপনার ব্যালেন্স: <b>{balance} {currency}</b>\n"
        "📉 ন্যূনতম উইথড্র: <b>{min} {currency}</b>\n"
        "🏦 পেমেন্ট মাধ্যম: <b>{methods}</b>\n"
        f"{LINE}\n"
        "✍️ কত {currency} উইথড্র করতে চান? পরিমাণ লিখুন।\n\n"
        "<i>(বাতিল করতে /cancel লিখুন)</i>"
    ),
    "wd_sent": (
        "✅ <b>উইথড্র রিকোয়েস্ট জমা হয়েছে</b>\n"
        f"{LINE}\n"
        "💸 পরিমাণ: <b>{amount} {currency}</b>\n"
        "🏦 মাধ্যম: <b>{method}</b>\n"
        "📮 অ্যাকাউন্ট: {account}\n"
        "⏳ স্ট্যাটাস: <b>পেন্ডিং</b>\n"
        f"{LINE}\n"
        "💰 অবশিষ্ট ব্যালেন্স: <b>{balance} {currency}</b>\n"
        "🕐 অ্যাডমিন যাচাই করে শীঘ্রই জানিয়ে দেবেন।"
    ),
    "wd_ok": (
        "🎉 <b>উইথড্র সফল হয়েছে!</b>\n"
        f"{LINE}\n"
        "💸 পরিমাণ: <b>{amount} {currency}</b>\n"
        "🏦 মাধ্যম: <b>{method}</b>\n"
        "📮 অ্যাকাউন্ট: {account}\n"
        f"{LINE}\n"
        "✅ পেমেন্ট পাঠিয়ে দেওয়া হয়েছে। আমাদের সাথে থাকার জন্য ধন্যবাদ!"
    ),
    "wd_no": (
        "❌ <b>উইথড্র রিকোয়েস্ট বাতিল হয়েছে</b>\n"
        f"{LINE}\n"
        "💸 পরিমাণ: <b>{amount} {currency}</b>\n"
        "↩️ টাকা আপনার ব্যালেন্সে ফেরত দেওয়া হয়েছে\n"
        "💰 বর্তমান ব্যালেন্স: <b>{balance} {currency}</b>\n"
        f"{LINE}\n"
        "☎️ সমস্যা থাকলে যোগাযোগ করুন: {support}"
    ),
}

MSG_LABELS = {
    "balance": "💰 ব্যালেন্স মেসেজ",
    "refer": "🎁 রেফার মেসেজ",
    "withdraw": "💸 উইথড্র শুরুর মেসেজ",
    "wd_sent": "📨 উইথড্র জমা হওয়ার মেসেজ",
    "wd_ok": "✅ উইথড্র সফল মেসেজ",
    "wd_no": "❌ উইথড্র বাতিল মেসেজ",
}
# এই তিন ধরনের বাটন প্রিমিয়াম টেমপ্লেট ব্যবহার করে
TPL_KINDS = ("balance", "refer", "withdraw")

DEFAULT_REPLY = {
    "tasks": "🎯 <b>উপলব্ধ টাস্ক</b>\n👇 একটি টাস্ক বেছে নিন:",
    "history": "📜 <b>আপনার সাম্প্রতিক হিস্টোরি</b>",
    "support": "☎️ <b>সাপোর্ট</b>\nযেকোনো সমস্যায় যোগাযোগ করুন: {support}",
    "shop": "🛒 <b>আমাদের শপ</b>\n🟢 সবুজ = স্টক আছে | 🔴 লাল = স্টক নেই\n👇 পণ্য বেছে নিন:",
    "shopcat": "📂 <b>প্রডাক্ট লিস্ট</b>\n🟢 সবুজ = স্টক আছে | 🔴 লাল = স্টক নেই\n👇 পণ্য বেছে নিন:",
    "addmoney": "➕ <b>এড মানি</b>\n━━━━━━━━━━━━━━━━\nনিচ থেকে পেমেন্ট মাধ্যম বেছে নিন, টাকা পাঠান ও Transaction ID দিন। অ্যাডমিন যাচাই করলে ব্যালেন্সে টাকা যোগ হবে।",
    "orders": "🧾 <b>আপনার অর্ডার</b>",
    "refund": "♻️ <b>রিফান্ড রিকোয়েস্ট</b>\nপণ্য না পেলে বা সমস্যা হলে রিফান্ড চাইতে পারেন।",
    "ticket": "🆘 <b>সাপোর্ট</b>\n✍️ আপনার সমস্যাটি লিখে পাঠান (ছবিও দিতে পারেন):",
}

DEFAULT_TASK_PROMPT = "📝 আপনার কাজের প্রমাণ (লেখা বা স্ক্রিনশট) পাঠান:"
DEFAULT_TASK_DONE = "✅ আপনার সাবমিশন জমা হয়েছে। অ্যাডমিন যাচাই করে জানাবেন।"

SET_LABELS = {
    "currency": "💱 কারেন্সি চিহ্ন",
    "ref_bonus": "🎁 রেফার বোনাস",
    "ref_commission": "📈 রেফার কমিশন %",
    "welcome_bonus": "🎉 ওয়েলকাম বোনাস",
    "min_withdraw": "💸 ন্যূনতম উইথড্র",
    "min_add": "➕ ন্যূনতম এড মানি",
    "bot_name": "🤖 বটের নাম",
    "support": "☎️ সাপোর্ট",
}
STR_KEYS = {"currency", "bot_name", "support"}

STATUS_ICON = {"pending": "⏳", "approved": "✅", "rejected": "❌"}

# কপি সেটিং: কোন লেখায় টাচ করলে কপি হবে (অ্যাডমিন প্যানেল → 📋 কপি সেটিং থেকে বদলানো যায়)
COPY_LABELS = {
    "user_msg": "📥 ইউজারের পাঠানো মেসেজ (অ্যাডমিন দেখবে)",
    "id": "🆔 ইউজার আইডি",
    "link": "🔗 রেফার লিংক",
    "balance": "💰 ব্যালেন্স",
    "refs": "👥 মোট রেফার",
    "bonus": "🎁 রেফার বোনাস",
    "min": "💳 ন্যূনতম উইথড্র",
    "name": "👤 ইউজারের নাম",
    "support": "☎️ সাপোর্ট",
    "methods": "🏦 পেমেন্ট মাধ্যম",
    "amount": "💸 উইথড্র পরিমাণ",
    "account": "📮 উইথড্র অ্যাকাউন্ট",
}
COPY_DEFAULT = {k: k in ("user_msg", "id", "account") for k in COPY_LABELS}
COPY_WORDS_MAX = 100

# স্টিকার / আইকন লাইব্রেরি: কী -> (নাম, সাধারণ ইমোজি)
# স্টিকার (প্রিমিয়াম কাস্টম ইমোজি) অ্যাডমিন প্যানেল → 🎨 স্টিকার / আইকন লাইব্রেরি থেকে সেট করা হয়
ICON_PRESETS = {
    "facebook": ("Facebook", "📘"),
    "instagram": ("Instagram", "📸"),
    "gmail": ("Gmail", "📧"),
    "whatsapp": ("WhatsApp", "💬"),
    "telegram": ("Telegram", "✈️"),
    "youtube": ("YouTube", "▶️"),
    "tiktok": ("TikTok", "🎵"),
    "twitter": ("X (Twitter)", "🐦"),
    "messenger": ("Messenger", "💭"),
    "linkedin": ("LinkedIn", "💼"),
    "google": ("Google", "🔍"),
    "binance": ("Binance", "🔶"),
    "bkash": ("bKash", "💸"),
    "nagad": ("Nagad", "🟠"),
    "rocket": ("Rocket", "🚀"),
    "upay": ("Upay", "🟡"),
    "paypal": ("PayPal", "🅿️"),
    "payoneer": ("Payoneer", "💳"),
    "skrill": ("Skrill", "💜"),
    "usdt": ("USDT", "💵"),
    "bitcoin": ("Bitcoin", "₿"),
    "bank": ("ব্যাংক", "🏦"),
    "mobile": ("মোবাইল ব্যাংকিং", "📱"),
    "money": ("টাকা", "💰"),
    # --- আরও অ্যাপ / সার্ভিস ---
    "netflix": ("Netflix", "🎬"),
    "spotify": ("Spotify", "🎧"),
    "discord": ("Discord", "🎮"),
    "snapchat": ("Snapchat", "👻"),
    "pinterest": ("Pinterest", "📌"),
    "reddit": ("Reddit", "👽"),
    "zoom": ("Zoom", "🎥"),
    "canva": ("Canva", "🎨"),
    "chatgpt": ("ChatGPT", "🤖"),
    "steam": ("Steam", "🕹️"),
    "freefire": ("Free Fire", "🔥"),
    "visa": ("Visa / Card", "💳"),
    "amazon": ("Amazon", "📦"),
    "vpn": ("VPN", "🔐"),
    "playstore": ("Google Play", "🛍️"),
    "apple": ("Apple", "🍎"),
    # --- সিস্টেম বাটন ---
    "shop": ("শপ", "🛒"),
    "cart": ("কার্ট", "🧺"),
    "orders": ("অর্ডার", "🧾"),
    "wallet": ("ওয়ালেট", "👛"),
    "profile": ("প্রোফাইল", "👤"),
    "refer": ("রেফার", "🎁"),
    "support": ("সাপোর্ট", "☎️"),
    "history": ("হিস্টোরি", "📜"),
    "task": ("টাস্ক", "🎯"),
    "withdraw": ("উইথড্র", "💸"),
    "refund": ("রিফান্ড", "♻️"),
    "addmoney": ("এড মানি", "➕"),
    "offer": ("অফার", "🔥"),
    "bell": ("নোটিফিকেশন", "🔔"),
    "crown": ("প্রিমিয়াম", "👑"),
    "diamond": ("ডায়মন্ড", "💎"),
    "star": ("স্টার", "⭐"),
    "verified": ("ভেরিফাইড", "✅"),
    # --- ওয়েলকাম / ইনকাম মেসেজের স্টিকার ---
    "welcome": ("ওয়েলকাম", "🤑"),
    "cash": ("ক্যাশ / ইনকাম", "💵"),
    "auto": ("অটো পেমেন্ট", "🚀"),
    "instant": ("ইনস্ট্যান্ট (GO)", "🆗"),
    "invite": ("ইনভাইট / গিফট", "🎁"),
    "pay_method": ("পেমেন্ট মেথড", "👛"),
    "start_now": ("আজই শুরু করুন", "💻"),
    # --- আরও মোবাইল ব্যাংকিং / পেমেন্ট ---
    "surecash": ("SureCash", "💳"),
    "tap": ("Tap", "📲"),
    "okwallet": ("OK Wallet", "👝"),
    "mcash": ("mCash", "💴"),
    "dbbl": ("DBBL / Rocket Bank", "🏦"),
    "islamibank": ("ইসলামী ব্যাংক", "🕌"),
    "wise": ("Wise", "🌍"),
    "neteller": ("Neteller", "💚"),
    "perfectmoney": ("Perfect Money", "🔴"),
    "webmoney": ("WebMoney", "🔵"),
    "payeer": ("Payeer", "🔷"),
    "cashapp": ("Cash App", "💲"),
    "gpay": ("Google Pay", "🟢"),
    "applepay": ("Apple Pay", "🍏"),
    "binancepay": ("Binance Pay", "🟡"),
    "bybit": ("Bybit", "⚫"),
    "okx": ("OKX", "⬛"),
    "kucoin": ("KuCoin", "🟩"),
    "coinbase": ("Coinbase", "🔹"),
    "trustwallet": ("Trust Wallet", "🛡️"),
    "metamask": ("MetaMask", "🦊"),
    "ethereum": ("Ethereum", "💎"),
    "bnb": ("BNB", "🔶"),
    "tron": ("TRON (TRX)", "♦️"),
    "ton": ("TON", "💠"),
    "litecoin": ("Litecoin", "🪙"),
    "dogecoin": ("Dogecoin", "🐶"),
    "solana": ("Solana", "🟣"),
    # --- আরও অ্যাপ / সার্ভিস ---
    "threads": ("Threads", "🧵"),
    "imo": ("imo", "📞"),
    "viber": ("Viber", "📳"),
    "wechat": ("WeChat", "🗨️"),
    "line": ("LINE", "🟢"),
    "skype": ("Skype", "☁️"),
    "twitch": ("Twitch", "📺"),
    "pubg": ("PUBG", "🔫"),
    "roblox": ("Roblox", "🧱"),
    "minecraft": ("Minecraft", "⛏️"),
    "ml": ("Mobile Legends", "⚔️"),
    "codm": ("Call of Duty", "🎯"),
    "playstation": ("PlayStation", "🎮"),
    "xbox": ("Xbox", "🟩"),
    "daraz": ("Daraz", "🛒"),
    "foodpanda": ("Foodpanda", "🐼"),
    "pathao": ("Pathao", "🏍️"),
    "uber": ("Uber", "🚕"),
    "grameenphone": ("Grameenphone", "📶"),
    "robi": ("Robi", "📡"),
    "banglalink": ("Banglalink", "📱"),
    "airtel": ("Airtel", "📞"),
    "teletalk": ("Teletalk", "☎️"),
    "office": ("Microsoft Office", "📄"),
    "adobe": ("Adobe", "🅰️"),
    "capcut": ("CapCut", "✂️"),
    "grammarly": ("Grammarly", "✍️"),
    "gemini": ("Gemini / AI", "✨"),
    "tgpremium": ("Telegram Premium", "🌟"),
    "dropbox": ("Dropbox", "🗂️"),
    "github": ("GitHub", "🐙"),
    "wordpress": ("WordPress", "📝"),
    "shopify": ("Shopify", "🛍️"),
    "fiverr": ("Fiverr", "🟢"),
    "upwork": ("Upwork", "💼"),
    "hosting": ("হোস্টিং / ডোমেইন", "🌐"),
    "sms": ("SMS", "💬"),
    "fire": ("হট", "🔥"),
    "gift": ("গিফট", "🎁"),
    "trophy": ("ট্রফি", "🏆"),
    "lock": ("সিকিউর", "🔒"),
    "rocket_fast": ("স্পিড", "⚡"),
    "chart": ("চার্ট", "📈"),
    "users": ("ইউজার", "👥"),
    "link": ("লিংক", "🔗"),
    "info": ("ইনফো", "ℹ️"),
    "warning": ("সতর্কতা", "⚠️"),
    "settings": ("সেটিংস", "⚙️"),
    "home": ("হোম", "🏠"),
}
ICON_MAX = 300

# ডিফল্ট প্রিমিয়াম ইমোজি আইডি: "আইকনের কী": "ইমোজি আইডি"
# আইডি পেতে বটে /emojiid লিখে প্রিমিয়াম ইমোজি পাঠান/ফরওয়ার্ড করুন। এখানে বসালে বট চালুর সময় ওই আইকনে স্টিকার নিজে থেকেই সেট হবে
# (অ্যাডমিন প্যানেল থেকে আগে সেট করা স্টিকার বদলাবে না)। উদাহরণ: "bkash": "5123456789012345678",
DEFAULT_EMOJI_IDS = {
    # "bkash": "",
    # "nagad": "",
    # "binance": "",
}


# ============================== ডাটাবেস ==============================
def default_db():
    return {
        "settings": {
            "currency": "৳",
            "ref_bonus": 5.0,
            "ref_commission": 0.0,
            "welcome_bonus": 0.0,
            "min_withdraw": 50.0,
            "min_add": 10.0,
            "bot_name": "Good Income X",
            "support": "@admin",
            "msgs": {},
            "cancel_on": True,
            "force_admins": False,
            "copy": dict(COPY_DEFAULT),
            "copy_words": [],
        },
        "start": {"id": "start", "reply": "👋 স্বাগতম!", "photo": None, "inline": []},
        "menu": [],
        "users": {},
        "subs": {},
        "tasks": {},
        "force": [],
        "admins": [],
        "allowed": [],  # মূল বট ব্যবহারের অনুমতি পাওয়া ইউজার আইডি
        "bots": {},  # মূল বটে বানানো নতুন বটের তালিকা
        "wd_methods": [],
        "icons": {},
        "products": {},
        "orders": [],
        "categories": {},
        "addreqs": {},
        "refunds": {},
        "tx": [],
        "pay_methods": [
            {"id": "bkash", "text": "bKash", "number": "", "note": "Send Money করুন", "icon": "bkash", "style": "danger"},
            {"id": "nagad", "text": "Nagad", "number": "", "note": "Send Money করুন", "icon": "nagad", "style": None},
            {"id": "rocket", "text": "Rocket", "number": "", "note": "Send Money করুন", "icon": "rocket", "style": "primary"},
        ],
        "multi": {"names": [], "usernames": [], "firstnames": [], "lastnames": [], "numbers": [], "copy": dict(MN_COPY_DEFAULT)},
    }


_DBS = {}  # প্রতিটি বটের ডাটাবেস মেমরিতে থাকে (প্রতিবার ফাইল পড়া হয় না)


def load():
    c = cur()
    if c.key not in _DBS:
        db = default_db()
        if os.path.exists(c.db_file):
            try:
                with open(c.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                db.update(data)
                for k, v in default_db()["settings"].items():
                    db["settings"].setdefault(k, v)
                db["start"].setdefault("id", "start")
                db["start"].setdefault("inline", [])
                for k in ("tasks", "subs", "users", "products", "categories", "addreqs", "refunds"):
                    db.setdefault(k, {})
                for k in ("force", "admins", "wd_methods", "orders", "tx", "pay_methods"):
                    db.setdefault(k, [])
                db.setdefault("multi", {})
                for k in ("names", "usernames", "firstnames", "lastnames", "numbers"):
                    db["multi"].setdefault(k, [])
                db["multi"].setdefault("copy", dict(MN_COPY_DEFAULT))
            except Exception:
                logging.exception("data.json পড়া যায়নি, .broken নামে সরিয়ে রাখা হলো")
                try:
                    os.replace(c.db_file, c.db_file + ".broken")
                except Exception:
                    pass
                db = default_db()
        seed_icons(db)
        _DBS[c.key] = db
    return _DBS[c.key]


def save(db=None):
    c = cur()
    db = db or _DBS.get(c.key)
    os.makedirs(os.path.dirname(c.db_file) or ".", exist_ok=True)
    tmp = c.db_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, c.db_file)


def new_id():
    return uuid.uuid4().hex[:8]


def money(v):
    return f"{float(v):g}"


def esc(s):
    return html.escape(str(s))


def parse_num(text):
    try:
        return float(text.strip().replace(",", ""))
    except Exception:
        return None


# ---------- অ্যাডমিন ----------
def admin_ids(db):
    ids = [owner_id()]
    for a in db.get("admins", []):
        if a not in ids:
            ids.append(a)
    return ids


def is_admin(db, uid):
    return uid == owner_id() or uid in db.get("admins", [])


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        tg = getattr(event, "from_user", None)
        return bool(tg) and is_admin(load(), tg.id)


# ---------- বাটন ট্রি ----------
def walk(node):
    yield node
    for ib in node.get("inline", []):
        yield from walk(ib)
    for ch in node.get("children", []):
        yield from walk(ch)


def all_nodes(db):
    yield from walk(db["start"])
    for m in db["menu"]:
        yield from walk(m)


def menu_nodes(items):
    for it in items:
        yield it
        yield from menu_nodes(it.get("children", []))


def get_node(db, nid):
    for n in all_nodes(db):
        if n.get("id") == nid:
            return n
    return None


def find_menu(db, text):
    for it in menu_nodes(db["menu"]):
        if text in (it["text"], node_label(db, it)):
            return it
    return None


def remove_node(db, nid):
    db["menu"] = [x for x in db["menu"] if x["id"] != nid]
    for n in list(all_nodes(db)):
        if "inline" in n:
            n["inline"] = [x for x in n["inline"] if x["id"] != nid]
        if "children" in n:
            n["children"] = [x for x in n["children"] if x["id"] != nid]


def tree_lines(db):
    out = ["🌳 <b>সব বাটনের তালিকা</b>"]

    def rec(node, depth):
        pad = "   " * depth
        for ib in node.get("inline", []):
            _t = ib.get("type")
            kind = "🔗 লিংক" if _t == "url" else "🪟 Window (Web App)" if _t == "web" else KINDS.get(ib.get("kind", "text"), "")
            out.append(f"{pad}🔘 {esc(ib['text'])} [{ib.get('style') or 'default'}] → {kind}")
            rec(ib, depth + 1)
        for ch in node.get("children", []):
            out.append(f"{pad}⌨️ {esc(ch['text'])} → {KINDS.get(ch.get('kind', 'text'), '')}")
            rec(ch, depth + 1)

    rec(db["start"], 1)
    for m in db["menu"]:
        out.append(f"\n⌨️ <b>{esc(m['text'])}</b> [{m.get('style') or 'default'}] → {KINDS.get(m.get('kind', 'text'), '')}")
        rec(m, 1)
    kt = [t for t in db["tasks"].values() if t.get("place") == "keyboard"]
    if kt:
        out.append("\n🎯 <b>কিবোর্ডে থাকা টাস্ক বাটন</b>")
        for t in kt:
            out.append(f"⌨️ {esc(t['title'])} [{t.get('style') or 'default'}]")
    return "\n".join(out)


# ---------- ইউজার ----------
def ensure_user(db, tg_user):
    uid = str(tg_user.id)
    if uid in db["users"]:
        return db["users"][uid], False
    u = {
        "name": tg_user.full_name,
        "username": tg_user.username or "",
        "balance": float(db["settings"]["welcome_bonus"]),
        "refs": 0,
        "referred_by": None,
        "banned": False,
        "joined": int(time.time()),
    }
    db["users"][uid] = u
    return u, True


# ---------- উইথড্র মাধ্যম ----------
def method_min(db, m):
    v = float(m.get("min") or 0)
    return v if v > 0 else float(db["settings"]["min_withdraw"])


def global_min(db):
    ms = db.get("wd_methods", [])
    if ms:
        return min(method_min(db, m) for m in ms)
    return float(db["settings"]["min_withdraw"])


def get_method(db, mid):
    for m in db.get("wd_methods", []):
        if m["id"] == mid:
            return m
    return None


# ---------- স্টিকার / আইকন ----------
def seed_icons(db):
    icons = db.get("icons")
    if not isinstance(icons, dict):
        icons = db["icons"] = {}
    for k, (n, e) in ICON_PRESETS.items():
        icons.setdefault(k, {"name": n, "emoji": e, "cid": ""})
    for k, cid in DEFAULT_EMOJI_IDS.items():
        if k in icons and cid and not icons[k].get("cid"):
            icons[k]["cid"] = str(cid)
    for ic in icons.values():
        ic.setdefault("cid", "")
        ic.setdefault("emoji", "⭐")
        ic.setdefault("name", "?")


def emoji_lib_on(db):
    return bool(db.get("settings", {}).get("emoji_lib", True))


def emoji_fmt_on(db):
    return bool(db.get("settings", {}).get("emoji_fmt", True))


def icon_of(db, key):
    ic = db.get("icons", {}).get(key) if key else None
    if ic and not emoji_lib_on(db):
        return {**ic, "cid": ""}  # লাইব্রেরি বন্ধ: স্টিকার না, সাধারণ ইমোজি
    return ic


def icon_html(db, key):
    """মেসেজের ভেতরে বসানোর জন্য: স্টিকার থাকলে স্টিকার, না থাকলে সাধারণ ইমোজি"""
    ic = icon_of(db, key)
    if not ic:
        return ""
    if ic.get("cid"):
        return f'<tg-emoji emoji-id="{esc(ic["cid"])}">{esc(ic["emoji"])}</tg-emoji>'
    return esc(ic["emoji"])


IC_TOKEN = re.compile(r"\{ic:([A-Za-z0-9_]+)\}")


def apply_icon_tokens(db, text):
    """মেসেজে {ic:নাম} লিখলে সেই জায়গায় আইকন বসে (স্টিকার সেট থাকলে স্টিকার, নাহলে সাধারণ ইমোজি)"""
    if not text or "{ic:" not in text:
        return text
    icons = db.get("icons", {})
    if not emoji_fmt_on(db):
        return IC_TOKEN.sub(lambda m: esc(icons[m.group(1)]["emoji"]) if m.group(1) in icons else m.group(0), text)
    return IC_TOKEN.sub(lambda m: icon_html(db, m.group(1)) if m.group(1) in icons else m.group(0), text)


def method_text(db, mt):
    ic = icon_html(db, mt.get("icon"))
    return f"{ic} {esc(mt['name'])}" if ic else esc(mt["name"])


def method_label(db, mt):
    """কিবোর্ড বাটনের লেখা। স্টিকার সেট থাকলে স্টিকার আলাদা ফিল্ডে যায়, নাহলে সাধারণ ইমোজি লেখার আগে বসে"""
    ic = icon_of(db, mt.get("icon"))
    if ic and not ic.get("cid"):
        return f"{ic['emoji']} {mt['name']}"
    return mt["name"]


# ---------- বাটনের লেবেল (স্টিকারসহ) ও বিজনেস হেল্পার ----------
TX_ICON = {
    "add": "➕",
    "purchase": "🛒",
    "refund": "♻️",
    "reward": "🎁",
    "bonus": "🎉",
    "commission": "📈",
    "withdraw": "💸",
    "admin": "👮",
}


def node_label(db, n):
    """বাটনের লেখা: স্টিকার (প্রিমিয়াম) না থাকলে সাধারণ ইমোজি নামের আগে বসে"""
    ic = icon_of(db, n.get("icon"))
    if ic and not ic.get("cid"):
        return f"{ic['emoji']} {n['text']}"
    return n["text"]


def node_cid(db, n):
    ic = icon_of(db, n.get("icon"))
    return (ic or {}).get("cid") or None


def add_tx(db, uid, typ, amount, note=""):
    """লেনদেনের হিস্টোরিতে এন্ট্রি যোগ করে"""
    tx = db.setdefault("tx", [])
    t = {"id": new_id(), "uid": str(uid), "type": typ, "amount": round(float(amount), 2), "note": str(note)[:80], "time": int(time.time())}
    tx.append(t)
    if len(tx) > 5000:
        del tx[: len(tx) - 5000]
    return t


def is_manual(p):
    return p.get("mode") == "manual"


def avail(p):
    """স্টক আছে কিনা (ম্যানুয়াল প্রোডাক্টে অ্যাডমিন স্টক আউট না করলে সবসময় আছে)"""
    if is_manual(p):
        return not p.get("out")
    return bool(p.get("stock"))


def stock_short(p):
    if not avail(p):
        return "স্টক নেই"
    return "ম্যানুয়াল" if is_manual(p) else f"স্টক {len(p.get('stock', []))}"


def pm_text(db, mt):
    ic = icon_html(db, mt.get("icon"))
    return f"{ic} {esc(mt['text'])}" if ic else esc(mt["text"])


def custom_emojis(m):
    """মেসেজ/স্টিকারে থাকা প্রিমিয়াম (কাস্টম) ইমোজির তালিকা: [(id, ফলব্যাক ইমোজি)]"""
    out = []
    st = getattr(m, "sticker", None)
    if st is not None and getattr(st, "custom_emoji_id", None):
        out.append((st.custom_emoji_id, st.emoji or "⭐"))
    for src, ents in ((m.text, m.entities), (m.caption, m.caption_entities)):
        for e in ents or []:
            if e.type == "custom_emoji" and getattr(e, "custom_emoji_id", None):
                out.append((e.custom_emoji_id, (e.extract_from(src) if src else "") or "⭐"))
    return out


# ---------- মেসেজ টেমপ্লেট ----------
def get_msg(db, key):
    return db["settings"].get("msgs", {}).get(key) or DEFAULT_MSGS[key]


# ---------- মাল্টি নেম সিস্টেম ----------
# %name% %username% %firstname% %lastname% %number% — প্রতিবার আলাদা র‍্যান্ডম মান আসে
_MN_FIRST = [
    "Rahim", "Karim", "Sakib", "Tamim", "Rafi", "Nayeem", "Arif", "Hasan", "Imran", "Sohan",
    "Fahim", "Rakib", "Jahid", "Mahin", "Shuvo", "Nabil", "Tanvir", "Rubel", "Sajib", "Mehedi",
    "Ayesha", "Fatima", "Nusrat", "Sumaiya", "Tasnim", "Mim", "Jannat", "Riya", "Sadia", "Lamia",
    "Farhana", "Shabnam", "Mouri", "Tania", "Puja", "Nadia", "Sharmin", "Rumana", "Ishrat", "Anika",
]
_MN_LAST = [
    "Hossain", "Ahmed", "Islam", "Khan", "Uddin", "Rahman", "Chowdhury", "Sarker", "Mia", "Akter",
    "Begum", "Khatun", "Mondal", "Biswas", "Das", "Roy", "Sheikh", "Talukder", "Hasan", "Alam",
]
_MN_LAST_PICK = {}

MN_KEYS = {"name": "names", "username": "usernames", "firstname": "firstnames", "lastname": "lastnames", "number": "numbers"}
MN_ALIAS = {"first_name": "firstname", "last_name": "lastname", "nambr": "number", "phone": "number"}
MN_LABELS = {
    "name": "👤 নাম  %name%",
    "username": "🔖 ইউজারনেম  %username%",
    "firstname": "🅰️ ফার্স্ট নেম  %firstname%",
    "lastname": "🅱️ লাস্ট নেম  %lastname%",
    "number": "📞 নম্বর  %number%",
}
# কোনটায় টাচ করলে কপি হবে (অ্যাডমিন প্যানেল থেকে বদলানো যায়)
MN_COPY_DEFAULT = {"name": False, "username": False, "firstname": True, "lastname": True, "number": True}
MN_RE = re.compile(r"%\s*(username|firstname|first_name|lastname|last_name|name|number|nambr|phone)\s*%", re.I)


def mn_gen_name():
    return random.choice(_MN_FIRST) + " " + random.choice(_MN_LAST)


def mn_gen_username():
    f, l = random.choice(_MN_FIRST).lower(), random.choice(_MN_LAST).lower()
    style = random.randint(0, 4)
    if style == 0:
        return f"{f}_{l}"
    if style == 1:
        return f"{f}{random.randint(10, 9999)}"
    if style == 2:
        return f"{f}.{l}{random.randint(1, 99)}"
    if style == 3:
        return f"{l}_{f}_{random.randint(1, 999)}"
    return f"{f}{l[:3]}{random.randint(100, 999)}"


def mn_gen_number():
    return random.choice(["013", "014", "015", "016", "017", "018", "019"]) + "".join(random.choice("0123456789") for _ in range(8))


def mn_gen(key, mn):
    pool = mn.get(MN_KEYS[key]) or []
    if key in ("name", "username", "number"):
        if pool:
            return random.choice(pool)
        return {"name": mn_gen_name, "username": mn_gen_username, "number": mn_gen_number}[key]()
    names = mn.get("names") or []
    if key == "firstname":
        if pool:
            return random.choice(pool)
        if names:
            return random.choice(names).split()[0]
        return random.choice(_MN_FIRST)
    if pool:  # lastname
        return random.choice(pool)
    multi = [n.split(None, 1)[1] for n in names if len(n.split()) > 1]
    return random.choice(multi) if multi else random.choice(_MN_LAST)


def mn_pick(key, mn, used):
    v = ""
    for _ in range(12):
        v = mn_gen(key, mn)
        if v not in used and v != _MN_LAST_PICK.get(key):
            break
    _MN_LAST_PICK[key] = v
    used.add(v)
    return v


def multi_names(db, text):
    if not text or "%" not in text:
        return text
    mn = db.get("multi", {})
    copy = {**MN_COPY_DEFAULT, **mn.get("copy", {})}
    used = {k: set() for k in MN_KEYS}

    def sub(m):
        key = m.group(1).lower()
        key = MN_ALIAS.get(key, key)
        v = esc(mn_pick(key, mn, used[key]))
        return f"<code>{v}</code>" if copy.get(key) else v  # <code> এ টাচ করলেই কপি হয়

    return MN_RE.sub(sub, text)


def copy_map(db):
    return {**COPY_DEFAULT, **db["settings"].get("copy", {})}


def flat_code(text):
    """<code> এর ভেতরে <code> থাকলে টেলিগ্রাম এরর দেয়; তাই ভেতরের গুলো সরিয়ে দেয়"""
    out, depth = [], 0
    for part in re.split(r"(</?code>)", text):
        if part == "<code>":
            if depth == 0:
                out.append(part)
            depth += 1
        elif part == "</code>":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0:
                out.append(part)
        else:
            out.append(part)
    return "".join(out)


_TAG_SPLIT = re.compile(r"(<[^>]*>)")
_SKIP_TAG = re.compile(r"<(/?)\s*(code|pre|a)\b", re.I)


def apply_copy_words(db, text):
    """অ্যাডমিনের যোগ করা লেখাগুলো যেখানেই থাকুক, টাচ করলে কপি হওয়ার মতো করে দেয়"""
    words = [w for w in db["settings"].get("copy_words", []) if w]
    if not words or not text:
        return text
    pat = re.compile("|".join(re.escape(esc(w)) for w in sorted(words, key=len, reverse=True)))
    out, skip = [], 0
    for part in _TAG_SPLIT.split(text):
        if part.startswith("<") and part.endswith(">"):
            m = _SKIP_TAG.match(part)
            if m:
                skip = max(0, skip - 1) if m.group(1) else skip + 1
            out.append(part)
        elif skip:
            out.append(part)
        else:
            out.append(pat.sub(lambda m: f"<code>{m.group(0)}</code>", part))
    return "".join(out)


def render(text, db, uid, extra=None):
    u = db["users"].get(str(uid)) or {"balance": 0, "refs": 0, "name": "-"}
    s = db["settings"]
    methods = ", ".join(method_text(db, m) for m in db.get("wd_methods", [])) or "—"
    micons = " ".join(h for h in (icon_html(db, m.get("icon")) for m in db.get("wd_methods", [])) if h) or "—"
    rep = {
        "{balance}": money(u["balance"]),
        "{refs}": str(u["refs"]),
        "{link}": f"https://t.me/{cur().username}?start=ref_{uid}",
        "{bonus}": money(s["ref_bonus"]),
        "{currency}": s["currency"],
        "{min}": money(global_min(db)),
        "{name}": esc(u["name"]),
        "{id}": str(uid),
        "{support}": esc(s.get("support", "")),
        "{bot}": esc(s.get("bot_name", "")),
        "{methods}": methods,
        "{method_icons}": micons,
    }
    if extra:
        rep.update(extra)
    cp = copy_map(db)
    for k, v in rep.items():
        if cp.get(k.strip("{}")) and v and "<tg-emoji" not in v:
            v = f"<code>{v}</code>"  # <code> এ টাচ করলেই কপি হয়
        text = text.replace(k, v)
    return flat_code(multi_names(db, text))


def fmt_msg(db, key, uid, **kw):
    extra = {"{" + k + "}": (money(v) if isinstance(v, (int, float)) else esc(v)) for k, v in kw.items()}
    return render(get_msg(db, key), db, uid, extra)


def pay_commission(db, uid, reward):
    """রেফারারকে কমিশন দেয়; (referrer_id, amount) অথবা None রিটার্ন করে"""
    pct = float(db["settings"].get("ref_commission", 0))
    u = db["users"].get(uid)
    if pct <= 0 or not u or not u.get("referred_by") or reward <= 0:
        return None
    r = db["users"].get(u["referred_by"])
    if not r:
        return None
    amt = round(reward * pct / 100, 2)
    if amt <= 0:
        return None
    r["balance"] += amt
    add_tx(db, u["referred_by"], "commission", amt, "রেফার কমিশন")
    return u["referred_by"], amt


# ---------- টাস্ক ----------
def task_counts(db, tid):
    c = {"approved": 0, "pending": 0, "rejected": 0}
    for s in db["subs"].values():
        if s.get("type") == "task" and s.get("tid") == tid:
            c[s["status"]] = c.get(s["status"], 0) + 1
    return c


def task_taken(db, uid, tid):
    t = db["tasks"].get(tid) or {}
    if t.get("repeat"):  # বারবার জমা দেওয়া যায় এমন টাস্ক
        return False
    for s in db["subs"].values():
        if s.get("type") == "task" and s.get("tid") == tid and s["uid"] == uid and s["status"] in ("pending", "approved"):
            return True
    return False


def keyboard_tasks(db):
    return [t for t in db["tasks"].values() if t.get("active") and t.get("place") == "keyboard"]


def parent_tasks(db, nid, place):
    """কোনো বাটনের ভেতরে বসানো 'বাটন টাস্ক' (place: parent_kb = কিবোর্ড, parent_inline = ইনলাইন)"""
    return [t for t in db["tasks"].values() if t.get("active") and t.get("parent") == nid and t.get("place") == place]


def find_task_btn(db, text):
    for t in keyboard_tasks(db):
        if t["title"] == text:
            return t
    for t in db["tasks"].values():
        if t.get("active") and t.get("parent") and t.get("place") == "parent_kb" and t["title"] == text:
            return t
    return None


def task_place_label(db, t):
    if t.get("parent"):
        n = get_node(db, t["parent"])
        name = "স্টার্ট মেসেজ" if t["parent"] == "start" else (esc(n["text"]) if n else "ডিলিট হওয়া বাটন")
        return f"{'⌨️' if t.get('place') == 'parent_kb' else '🔘'} «{name}» এর ভেতরে"
    return "⌨️ কিবোর্ড" if t.get("place") == "keyboard" else "🔘 ইনলাইন"


def submission_text(db, s):
    u = db["users"].get(s["uid"], {"name": "?", "username": ""})
    cur = db["settings"]["currency"]
    title = "🎯 টাস্ক সাবমিশন" if s["type"] == "task" else "📥 নতুন সাবমিশন"
    cp = copy_map(db).get("user_msg")  # ইউজারের পাঠানো লেখা টাচ করলে কপি হবে কিনা

    def user_text(v, limit):
        v = esc(str(v)[:limit])
        return f"<code>{v}</code>" if cp and v else v

    if s.get("qa"):
        per = max(200, 3000 // len(s["qa"]))
        body = "\n\n".join(f"❓ {esc(a['q'])}\n💬 {user_text(a['a'], per)}" for a in s["qa"])
    else:
        body = f"💬 {user_text(s['content'], 3000)}"
    return (
        f"<b>{title}</b>\n"
        f"🔘 {esc(s['btn'])}\n"
        f"👤 {esc(u['name'])} (@{esc(u['username'] or '-')})\n"
        f"🆔 <code>{s['uid']}</code>\n"
        f"🎁 Approve করলে: {money(s.get('reward', 0))} {cur}\n\n"
        f"{body}"
    )


def withdraw_text(db, s):
    u = db["users"].get(s["uid"], {"name": "?", "username": ""})
    cur = db["settings"]["currency"]
    acc = esc(s["account"])
    if copy_map(db).get("user_msg"):
        acc = f"<code>{acc}</code>"
    return (
        f"💸 <b>নতুন উইথড্র রিকোয়েস্ট</b>\n"
        f"👤 {esc(u['name'])} (@{esc(u['username'] or '-')})\n"
        f"🆔 <code>{s['uid']}</code>\n"
        f"💰 পরিমাণ: <b>{money(s['amount'])} {cur}</b>\n"
        f"🏦 মাধ্যম: <b>{esc(s.get('method') or '-')}</b>\n"
        f"📮 অ্যাকাউন্ট: {acc}"
    )


# ============================== কিবোর্ড ==============================
def B(text, data=None, url=None, style=None, web_app=None, icon=None):
    kw = {"text": text}
    if icon:
        kw["icon_custom_emoji_id"] = icon
    if web_app:
        kw["web_app"] = WebAppInfo(url=web_app)
    if data:
        kw["callback_data"] = data
    if url:
        kw["url"] = url
    if style:
        kw["style"] = style
    return InlineKeyboardButton(**kw)


def KB(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


ICON_PAGE = 80
PER_PAGE = 20  # লাইব্রেরি ও ফরম্যাটিং ইমোজির তালিকায় প্রতি পাতায় ২০টি (১০ + ১০, দুই কলামে)


def icon_keys_sorted(db):
    """প্রিমিয়াম (স্টিকার সেট করা) আইকন আগে, বাকিগুলো পরে — আগের ক্রম বজায় রেখে"""
    keys = list(db["icons"])
    return [k for k in keys if db["icons"][k].get("cid")] + [k for k in keys if not db["icons"][k].get("cid")]


def icon_picker_kb(db, prefix, name="", back=None, page=0):
    """আইকন বাছাইয়ের ইনলাইন বাটন। নামের সাথে মিলে যাওয়া আইকন আগে দেখায় (পাতা ধরে)"""
    icons = db.get("icons", {})
    low = (name or "").strip().lower()

    def score(k):
        n = icons[k]["name"].lower()
        hit = low and (k in low or n in low or (len(low) >= 3 and low in n))
        return (0 if hit else 1, 0 if icons[k].get("cid") else 1, 0 if k.startswith("c_") else 1)

    rows, row = [], []
    ordered = sorted(icons, key=score)
    pages = max(1, (len(ordered) + ICON_PAGE - 1) // ICON_PAGE)
    page = max(0, min(page, pages - 1))
    for k in ordered[page * ICON_PAGE:(page + 1) * ICON_PAGE]:
        ic = icons[k]
        label = ic["name"] if ic.get("cid") else f"{ic['emoji']} {ic['name']}"
        row.append(B(label[:30], prefix + k, icon=ic.get("cid") or None))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(B("◀️ আগের পাতা", f"icpg:{page - 1}:{prefix}"))
        nav.append(B(f"📄 {page + 1}/{pages}", "icpg:noop"))
        if page < pages - 1:
            nav.append(B("পরের পাতা ▶️", f"icpg:{page + 1}:{prefix}"))
        rows.append(nav)
    rows.append([B("⛔ কোনো আইকন লাগবে না", prefix + "-")])
    if back:
        rows.append([B("🔙 পিছনে যান", back)])
    return KB(rows)


def method_kb(db, methods):
    """উইথড্র মাধ্যমের কিবোর্ড বাটন (রং ও স্টিকারসহ)"""
    rows, row = [], []
    for x in methods:
        kw = {"text": method_label(db, x)}
        if x.get("style"):
            kw["style"] = x["style"]
        ic = icon_of(db, x.get("icon"))
        if ic and ic.get("cid"):
            kw["icon_custom_emoji_id"] = ic["cid"]
        row.append(KeyboardButton(**kw))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if db["settings"].get("cancel_on", True):
        rows.append([KeyboardButton(text=CANCEL_TEXT, style="danger")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def rk_rows(items):
    db = load()
    rows, row = [], []
    for b in items:
        kw = {"text": node_label(db, b)}
        if b.get("style"):
            kw["style"] = b["style"]
        cid = node_cid(db, b)
        if cid:
            kw["icon_custom_emoji_id"] = cid
        row.append(KeyboardButton(**kw))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def main_kb(db):
    items = list(db["menu"]) + [{"text": t["title"], "style": t.get("style")} for t in keyboard_tasks(db)]
    rows = rk_rows(items)
    if cur().is_main:
        rows.insert(
            0,
            [
                KeyboardButton(text=BTN_ADD_BOT, style="success"),
                KeyboardButton(text=BTN_MY_BOTS, style="primary"),
                KeyboardButton(text=BTN_DEL_BOT, style="danger"),
            ],
        )
    if not rows:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def sub_kb(node):
    extra = [{"text": t["title"], "style": t.get("style")} for t in parent_tasks(load(), node.get("id"), "parent_kb")]
    rows = rk_rows(list(node.get("children", [])) + extra)
    rows.append([KeyboardButton(text=BACK_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def inline_kb(node):
    db = load()
    rows = []
    for ib in node.get("inline", []):
        txt, cid = node_label(db, ib), node_cid(db, ib)
        if ib.get("type") == "url":
            rows.append([B(txt, url=ib["value"], style=ib.get("style"), icon=cid)])
        elif ib.get("type") == "web":
            rows.append([B(txt, web_app=ib["value"], style=ib.get("style"), icon=cid)])
        else:
            rows.append([B(txt, "i:" + ib["id"], style=ib.get("style"), icon=cid)])
    for t in parent_tasks(db, node.get("id"), "parent_inline"):
        rows.append([B(t["title"][:60], "ubt:" + t["id"], style=t.get("style"))])
    return KB(rows) if rows else None


def panel_kb():
    extra = [[B("✅ অনুমোদিত ইউজার (বট ব্যবহারের অনুমতি)", "adm:allow", style="success")]] if cur().is_main else []
    return KB(
        extra
        + [
            [B("📊 ড্যাশবোর্ড", "adm:dash"), B("👥 ইউজার", "adm:users")],
            [B("🎯 টাস্ক", "adm:tasks"), B("💸 উইথড্র", "adm:wd")],
            [B("📥 পেন্ডিং সাবমিশন", "adm:pend"), B("🔘 বাটন কন্ট্রোল", "adm:btn")],
            [B("👮 অ্যাডমিন ম্যানেজ", "adm:admins"), B("💬 মেসেজ সেটিং", "adm:msgs")],
            [B("⚙️ সেটিংস", "adm:settings"), B("📢 ব্রডকাস্ট / ব্যাকআপ", "adm:more")],
            [B("🛍 বিজনেস বট (সেল / অটো ডেলিভারি)", "adm:biz", style="success")],
            [B("🎭 মাল্টি নেম সিস্টেম", "adm:mn")],
            [B("📋 কপি সেটিং (টাচ করলে কপি)", "adm:cp")],
            [B("🎨 স্টিকার / আইকন লাইব্রেরি", "adm:ic")],
            [B("✨ Message Formatting Emoji", "fe:p:0")],
            [B("🔛 ইমোজি অন / অফ", "adm:emsw")],
        ]
    )


def back_row(to="adm:home"):
    return [B("🔙 পিছনে যান", to)]


def btn_ctrl_kb():
    return KB(
        [
            [B("➕ মেইন মেনু বাটন যোগ", "adm:addmenu")],
            [B("➕ সাব-বাটন (মেনুর ভেতরে কিবোর্ড বাটন)", "adm:addsub")],
            [B("➕ ইনলাইন বাটন যোগ", "adm:addinline")],
            [B("✏️ বাটন এডিট (মেসেজ/নাম/রং/লিংক)", "adm:edit")],
            [B("🗑 বাটন ডিলিট", "adm:del")],
            [B("📋 সব বাটনের তালিকা", "adm:list")],
            back_row(),
        ]
    )


def color_kb():
    return KB([[B(v[0], "col:" + k)] for k, v in COLORS.items()])


def kinds_kb():
    return KB([[B(v, "knd:" + k)] for k, v in KINDS.items()])


def targets_kb(db, prefix, scope="inline"):
    """scope: inline = যেকোনো অ্যাকশন বাটন + স্টার্ট, menu = শুধু মেনু বাটন, edit = সব"""
    menu_ids = {n["id"] for n in menu_nodes(db["menu"])}
    rows = []
    if scope in ("inline", "edit"):
        rows.append([B("🏠 স্টার্ট মেসেজ", prefix + ":start")])
    for n in list(all_nodes(db))[1:]:
        if scope == "menu" and n["id"] not in menu_ids:
            continue
        if scope == "inline" and n.get("type") in ("url", "web"):
            continue
        icon = "⌨️" if n["id"] in menu_ids else "🔘"
        rows.append([B(f"{icon} {n['text']}"[:60], f"{prefix}:{n['id']}")])
    return KB(rows[:95])


def delete_kb(db):
    menu_ids = {n["id"] for n in menu_nodes(db["menu"])}
    rows = []
    for n in list(all_nodes(db))[1:]:
        icon = "⌨️" if n["id"] in menu_ids else "🔘"
        rows.append([B(f"🗑 {icon} {n['text']}"[:60], "del:" + n["id"])])
    rows = rows[:95]
    rows.append(back_row("adm:btn"))
    return KB(rows)


def settings_kb(db):
    rows = []
    for k, label in SET_LABELS.items():
        val = db["settings"][k]
        val = val if k in STR_KEYS else money(val)
        rows.append([B(f"{label}: {val}", "set:" + k)])
    on = lambda k, d=False: "চালু ✅" if db["settings"].get(k, d) else "বন্ধ ⛔"
    rows.append([B(f"❌ বাতিল বাটন (ইনপুটের সময়): {on('cancel_on', True)}", "tgl:cancel_on")])
    rows.append([B(f"🧪 Force Join অ্যাডমিনের জন্যও: {on('force_admins')}", "tgl:force_admins")])
    rows.append([B("🔒 Force Join (চ্যানেল জয়েন)", "adm:force")])
    rows.append(back_row())
    return KB(rows)


def users_kb():
    return KB(
        [
            [B("📋 ইউজার লিস্ট", "tl:list")],
            [B("🔍 ইউজার তথ্য (রেফার + হিস্টোরি)", "tl:info")],
            [B("💰 ব্যালেন্স যোগ/কমানো", "tl:adjust")],
            [B("🚫 ব্যান / আনব্যান", "tl:ban")],
            back_row(),
        ]
    )


def more_kb():
    return KB(
        [
            [B("📢 ব্রডকাস্ট", "tl:cast")],
            [B("💾 ব্যাকআপ নিন (data.json)", "adm:backup")],
            back_row(),
        ]
    )


def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_TEXT, style="danger")]], resize_keyboard=True
    )


def approve_kb(prefix, sid):
    return KB(
        [
            [
                B("✅ Approve", f"{prefix}:{sid}:y", style="success"),
                B("❌ Reject", f"{prefix}:{sid}:n", style="danger"),
            ]
        ]
    )


def join_kb(channels):
    rows = [[B("📢 " + (ch.get("title") or ch["chat"]), url=ch["url"])] for ch in channels]
    rows.append([B("✅ জয়েন করেছি", "chk")])
    return KB(rows)


# ============================== সাহায্যকারী ফাংশন ==============================
def _markup_buttons(markup):
    if isinstance(markup, InlineKeyboardMarkup):
        return [b for r in markup.inline_keyboard for b in r]
    if isinstance(markup, ReplyKeyboardMarkup):
        return [b for r in markup.keyboard for b in r]
    return []


def strip_icons(markup):
    """বাটনের স্টিকার (icon_custom_emoji_id) সরানো কপি; আইডি ভুল হলে মেসেজ যেন আটকে না যায়"""
    try:
        drop = {"icon_custom_emoji_id": None}
        if isinstance(markup, InlineKeyboardMarkup):
            return InlineKeyboardMarkup(inline_keyboard=[[b.model_copy(update=drop) for b in r] for r in markup.inline_keyboard])
        if isinstance(markup, ReplyKeyboardMarkup):
            return markup.model_copy(update={"keyboard": [[b.model_copy(update=drop) for b in r] for r in markup.keyboard]})
    except Exception:
        logging.exception("strip_icons failed")
    return None


async def deliver(bot, chat_id, text, markup=None, photo=None):
    """HTML দিয়ে পাঠায়; ব্যর্থ হলে স্টিকার ছাড়া / সাধারণ টেক্সটে পাঠায়"""
    text = text or ""
    try:
        text = apply_icon_tokens(load(), text)
    except Exception:
        logging.exception("icon tokens apply failed")
    try:
        text = apply_copy_words(load(), text)
    except Exception:
        logging.exception("copy words apply failed")
    plain = re.sub(r"</?tg-emoji[^>]*>", "", text)  # স্টিকার ট্যাগ বাদ দিলে শুধু ফলব্যাক ইমোজি থাকে
    attempts = [(ParseMode.HTML, text, markup)]
    if plain != text:
        attempts.append((ParseMode.HTML, plain, markup))
    attempts.append((None, plain, markup))
    if any(getattr(b, "icon_custom_emoji_id", None) for b in _markup_buttons(markup)):
        safe = strip_icons(markup)
        if safe is not None:
            attempts.append((ParseMode.HTML, plain, safe))
            attempts.append((None, plain, safe))
    for pm, tx, mk in attempts:
        try:
            if photo:
                await bot.send_photo(chat_id, photo, caption=tx[:1024], reply_markup=mk, parse_mode=pm)
            else:
                await bot.send_message(chat_id, tx, reply_markup=mk, parse_mode=pm)
            return True
        except TelegramBadRequest:
            continue
        except Exception:
            return False
    return False


# ---------- অ্যাডমিন প্যানেল: এক মেসেজেই এডিট, সব জায়গায় হোম বাটন, সব বাটনে রং ----------
ADM_CTX = contextvars.ContextVar("adm_ctx", default=None)
ADM_HOME = "adm:home"
# এই বাটনগুলো নোটিফিকেশন/রিকোয়েস্টের অ্যাকশন, তাই মেসেজ বদলানো হবে না (আগের মতো নতুন মেসেজ আসবে)
ADM_KEEP_MSG = ("ap:", "wd:", "amr:", "orddl:", "ordcx:", "rfa:", "tkr:")

_DANGER_WORDS = ("🗑", "🚫", "❌", "⛔", "বাতিল", "ডিলিট", "মুছ", "ব্যান", "রিজেক্ট", "Reject", "reject", "সরান")
_SUCCESS_WORDS = ("➕", "✅", "🟢", "💾", "সংরক্ষণ", "চালু", "অ্যাপ্রুভ", "Approve", "approve", "যোগ করুন", "নতুন")


def adm_style(btn, idx):
    """বাটনে রং না থাকলে অর্থ অনুযায়ী রং ঠিক করে: সবুজ = যোগ/সফল, লাল = ডিলিট/বাতিল/পিছনে, বাকিগুলো নীল-সবুজ পালাক্রমে"""
    t = btn.text or ""
    cb = btn.callback_data or ""
    if cb == ADM_HOME:
        return "success" if t.startswith("🏠") else "danger"
    if t.startswith("🔙"):
        return "danger"
    if any(w in t for w in _DANGER_WORDS):
        return "danger"
    if any(w in t for w in _SUCCESS_WORDS):
        return "success"
    return "primary" if idx % 2 == 0 else "success"


def adm_decorate(markup):
    """অ্যাডমিনের ইনলাইন কিবোর্ডে: সব বাটনে রং + মূল অ্যাডমিন প্যানেলে ফেরার বাটন"""
    if not isinstance(markup, InlineKeyboardMarkup):
        return markup
    try:
        rows = []
        for ri, r in enumerate(markup.inline_keyboard):
            nr = []
            for b in r:
                if not getattr(b, "style", None):
                    b = b.model_copy(update={"style": adm_style(b, ri)})
                nr.append(b)
            rows.append(nr)
        flat = [b for r in rows for b in r]
        cbs = {b.callback_data for b in flat}
        is_main_panel = "adm:dash" in cbs and "adm:btn" in cbs
        if ADM_HOME not in cbs and not is_main_panel and len(flat) < 100:
            rows.append([B("🏠 মূল অ্যাডমিন প্যানেল", ADM_HOME, style="success")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    except Exception:
        logging.exception("adm_decorate failed")
        return markup


async def edit_in_place(msg, text, markup):
    """আগের মেসেজটিই এডিট করে নতুন লেখা/বাটন বসায়; না পারলে False"""
    try:
        text = apply_copy_words(load(), apply_icon_tokens(load(), text or ""))
    except Exception:
        logging.exception("copy words apply failed")
    plain = re.sub(r"</?tg-emoji[^>]*>", "", text)
    attempts = [(ParseMode.HTML, text, markup)]
    if plain != text:
        attempts.append((ParseMode.HTML, plain, markup))
    if any(getattr(b, "icon_custom_emoji_id", None) for b in _markup_buttons(markup)):
        safe = strip_icons(markup)
        if safe is not None:
            attempts.append((ParseMode.HTML, plain, safe))
    for pm, tx, mk in attempts:
        try:
            await msg.edit_text(tx, reply_markup=mk, parse_mode=pm)
            return True
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return True
            continue
        except Exception:
            return False
    return False


class AdminCtxMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        cbm = None
        if isinstance(event, CallbackQuery) and event.message is not None:
            if not (event.data or "").startswith(ADM_KEEP_MSG):
                cbm = event.message
        tok = ADM_CTX.set({"cb": cbm, "used": False})
        try:
            return await handler(event, data)
        finally:
            ADM_CTX.reset(tok)


async def tell(msg, text, markup=None, photo=None):
    ctx = ADM_CTX.get()
    if ctx is not None:
        if markup is None or isinstance(markup, InlineKeyboardMarkup):
            markup = adm_decorate(markup if markup is not None else KB([]))
        cbm = ctx.get("cb")
        if (
            cbm is not None
            and not ctx["used"]
            and not photo
            and getattr(msg, "message_id", None) == cbm.message_id
            and msg.chat.id == cbm.chat.id
            and isinstance(markup, InlineKeyboardMarkup)
        ):
            ctx["used"] = True
            if await edit_in_place(msg, text, markup):
                return True
    return await deliver(msg.bot, msg.chat.id, text, markup, photo)


async def tell_flow(msg, db, text, ikb=None, photo=None):
    """ইনপুট নেওয়ার মেসেজ; বাতিল বাটন চালু থাকলে কিবোর্ডে বাতিল বাটন দেখায়"""
    if not db["settings"].get("cancel_on", True):
        return await tell(msg, text, ikb, photo)
    if ikb is None:
        return await tell(msg, text, cancel_kb(), photo)
    await tell(msg, text, ikb, photo)
    return await tell(msg, "👇 বাতিল করতে নিচের বাটন চাপুন", cancel_kb())


async def notify_admins(bot, text, markup=None):
    """সব অ্যাডমিনকে মেসেজ পাঠায়"""
    for aid in admin_ids(load()):
        await deliver(bot, aid, text, markup)


async def tell_long(msg, text):
    chunk = ""
    for line in text.split("\n"):
        if len(chunk) + len(line) + 1 > 3500:
            await tell(msg, chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await tell(msg, chunk)


async def show_panel(msg):
    await tell(msg, "🛠 <b>অ্যাডমিন প্যানেল</b>", panel_kb())


def extract_reply(m):
    if m.photo:
        return (m.caption or ""), m.photo[-1].file_id
    return m.text, None


_FJ_WARN = {}


def force_applies(db, uid):
    return bool(db["force"]) and (not is_admin(db, uid) or bool(db["settings"].get("force_admins")))


async def warn_force(bot, ch, err):
    now = time.time()
    if now - _FJ_WARN.get((cur().key, ch["chat"]), 0) < 1800:
        return
    _FJ_WARN[(cur().key, ch["chat"])] = now
    await deliver(
        bot,
        owner_id(),
        f"⚠️ <b>Force Join কাজ করছে না</b>\n📢 {esc(ch['chat'])}\nকারণ: {esc(str(err)[:150])}\n"
        "👉 বটকে ওই চ্যানেলের <b>অ্যাডমিন</b> বানান।",
    )


async def missing_channels(bot, db, uid):
    miss = []
    for ch in db["force"]:
        ref = ch["chat"]
        if ref.lstrip("-").isdigit():
            ref = int(ref)
        try:
            mem = await bot.get_chat_member(ref, uid)
            status = str(getattr(mem.status, "value", mem.status))
            if status in ("left", "kicked") or (status == "restricted" and not getattr(mem, "is_member", True)):
                miss.append(ch)
        except Exception as e:
            logging.warning("Force Join চেক করা যায়নি: %s (%s)", ch["chat"], e)
            await warn_force(bot, ch, e)
    return miss


# ============================== স্টেট ==============================
class NB(StatesGroup):  # নতুন বাটন
    parent = State()
    text = State()
    color = State()
    icon = State()
    type = State()
    url = State()
    kind = State()
    reply = State()
    done_msg = State()
    reward = State()
    cat = State()


class EN(StatesGroup):  # এডিট
    value = State()
    color = State()


class SetVal(StatesGroup):
    value = State()


class FJ(StatesGroup):
    add = State()
    link = State()


class TaskAdd(StatesGroup):
    title = State()
    desc = State()
    link = State()
    color = State()
    place = State()
    prompt = State()
    btnmenu = State()
    urltext = State()
    urlurl = State()
    step = State()
    stepmore = State()
    done = State()
    reward = State()
    repeat = State()
    parent = State()
    pplace = State()


class Tools(StatesGroup):
    info = State()
    adjust = State()
    ban = State()
    cast = State()


class AdminAdd(StatesGroup):
    uid = State()


class AllowAdd(StatesGroup):  # অনুমোদিত ইউজার যোগ (মূল বট)
    uid = State()


class BotAdd(StatesGroup):  # নতুন বট যোগ
    name = State()
    token = State()


class WM(StatesGroup):  # উইথড্র মাধ্যম (অ্যাডমিন)
    name = State()
    icon = State()
    color = State()
    minimum = State()
    hint = State()


class MsgEdit(StatesGroup):
    value = State()


class UserInput(StatesGroup):
    waiting = State()


class Withdraw(StatesGroup):
    amount = State()
    method = State()
    account = State()


class UserTask(StatesGroup):  # ধাপে ধাপে মেসেজ টাস্ক (ইউজার)
    answering = State()


# ============================== অ্যাডমিন প্যানেল ==============================
admin = Router()
admin.message.filter(IsAdmin())
admin.callback_query.filter(IsAdmin())
admin.message.middleware(AdminCtxMiddleware())
admin.callback_query.middleware(AdminCtxMiddleware())


@admin.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext):
    await state.clear()
    await show_panel(m)


@admin.message(Command("cancel"))
async def cancel_cmd(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("❎ বাতিল করা হয়েছে")
    await show_panel(m)


@admin.callback_query(F.data == "adm:home")
async def go_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_panel(c.message)
    await c.answer()


# ---------- ড্যাশবোর্ড ----------
@admin.callback_query(F.data == "adm:dash")
async def dashboard(c: CallbackQuery):
    db = load()
    cur = db["settings"]["currency"]
    today = datetime.now(TZ).date()
    users = db["users"].values()
    new_today = sum(1 for u in users if datetime.fromtimestamp(u["joined"], TZ).date() == today)
    total_bal = sum(u["balance"] for u in users)
    banned = sum(1 for u in users if u.get("banned"))
    wd_pend = [s for s in db["subs"].values() if s["type"] == "withdraw" and s["status"] == "pending"]
    wd_paid = sum(s["amount"] for s in db["subs"].values() if s["type"] == "withdraw" and s["status"] == "approved")
    rewards = sum(
        s.get("reward", 0) for s in db["subs"].values() if s["type"] in ("input", "task") and s["status"] == "approved"
    )
    sub_pend = sum(1 for s in db["subs"].values() if s["type"] in ("input", "task") and s["status"] == "pending")
    await tell(
        c.message,
        "📊 <b>ড্যাশবোর্ড</b>\n\n"
        f"👥 মোট ইউজার: <b>{len(db['users'])}</b>\n"
        f"🆕 আজকের নতুন ইউজার: <b>{new_today}</b>\n"
        f"🚫 ব্যান: <b>{banned}</b>\n"
        f"👮 অ্যাডমিন: <b>{len(admin_ids(db))}</b>\n\n"
        f"💰 ইউজারদের মোট ব্যালেন্স: <b>{money(total_bal)} {cur}</b>\n"
        f"⏳ পেন্ডিং উইথড্র: <b>{len(wd_pend)} টি ({money(sum(s['amount'] for s in wd_pend))} {cur})</b>\n"
        f"✅ মোট পেমেন্ট দেওয়া হয়েছে: <b>{money(wd_paid)} {cur}</b>\n"
        f"🎁 মোট রিওয়ার্ড দেওয়া হয়েছে: <b>{money(rewards)} {cur}</b>\n"
        f"📥 পেন্ডিং সাবমিশন: <b>{sub_pend}</b>\n"
        f"🎯 সক্রিয় টাস্ক: <b>{sum(1 for t in db['tasks'].values() if t['active'])}</b>",
        KB([back_row()]),
    )
    await c.answer()


# ---------- বাটন কন্ট্রোল ----------
@admin.callback_query(F.data == "adm:btn")
async def btn_ctrl(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await tell(
        c.message,
        "🔘 <b>বাটন কন্ট্রোল</b>\n\n"
        "⌨️ <b>মেইন মেনু বাটন</b> = নিচের কিবোর্ডে থাকা বাটন\n"
        "⌨️ <b>সাব-বাটন</b> = কোনো মেনু বাটনে চাপলে যে নতুন কিবোর্ড আসবে তার বাটন\n"
        "🔘 <b>ইনলাইন বাটন</b> = মেসেজের নিচে থাকা বাটন (লিংক, কাজ, ইনপুট ইত্যাদি)",
        btn_ctrl_kb(),
    )
    await c.answer()


@admin.callback_query(F.data == "adm:addmenu")
async def nb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(mode="menu", parent="root")
    await state.set_state(NB.text)
    await tell(c.message, "✍️ বাটনের নাম লিখুন:\n(বাতিল: /cancel)")
    await c.answer()


@admin.callback_query(F.data == "adm:addsub")
async def nb_sub(c: CallbackQuery, state: FSMContext):
    db = load()
    if not db["menu"]:
        await c.answer("আগে একটি মেইন মেনু বাটন যোগ করুন", show_alert=True)
        return
    await state.clear()
    await state.update_data(mode="sub")
    await state.set_state(NB.parent)
    await tell(c.message, "📂 কোন মেনু বাটনের ভেতরে সাব-বাটন যোগ করবেন?", targets_kb(db, "nbp", "menu"))
    await c.answer()


@admin.callback_query(F.data == "adm:addinline")
async def nb_inline(c: CallbackQuery, state: FSMContext):
    db = load()
    await state.clear()
    await state.update_data(mode="inline")
    await state.set_state(NB.parent)
    await tell(c.message, "📌 কোন মেসেজের নিচে ইনলাইন বাটন যোগ করবেন?", targets_kb(db, "nbp", "inline"))
    await c.answer()


@admin.callback_query(NB.parent, F.data.startswith("nbp:"))
async def nb_parent(c: CallbackQuery, state: FSMContext):
    await state.update_data(parent=c.data[4:])
    await state.set_state(NB.text)
    await tell(c.message, "✍️ বাটনের নাম লিখুন:")
    await c.answer()


@admin.message(NB.text, F.text)
async def nb_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(NB.color)
    await tell(m, "🎨 বাটনের রং বেছে নিন:", color_kb())


@admin.callback_query(NB.color, F.data.startswith("col:"))
async def nb_color(c: CallbackQuery, state: FSMContext):
    await state.update_data(style=COLORS[c.data[4:]][1])
    data = await state.get_data()
    await state.set_state(NB.icon)
    await tell(
        c.message,
        "🎨 বাটনের নামের আগে কোন <b>স্টিকার / আইকন</b> লাগাবেন? বেছে নিন:\n"
        "(নামের সাথে মিলে যাওয়া আইকন উপরে দেখাচ্ছে)",
        icon_picker_kb(load(), "nbi:", data.get("text", "")),
    )
    await c.answer()


@admin.callback_query(NB.icon, F.data.startswith("nbi:"))
async def nb_icon(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    db = load()
    if key != "-" and key not in db.get("icons", {}):
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    await state.update_data(icon="" if key == "-" else key)
    data = await state.get_data()
    if data["mode"] == "inline":
        await state.set_state(NB.type)
        await tell(
            c.message,
            "🔘 ইনলাইন বাটনের ধরন বেছে নিন:",
            KB(
                [
                    [B("🔗 URL ইনলাইন বাটন", "typ:url")],
                    [B("🪟 Window ইনলাইন বাটন (টেলিগ্রামের ভেতরেই খুলবে)", "typ:web")],
                    [B("⚡ অ্যাকশন বাটন (মেসেজ/ইনপুট/টাস্ক/শপ...)", "typ:act")],
                ]
            ),
        )
    else:
        await state.set_state(NB.kind)
        await tell(c.message, "⚙️ বাটনটি চাপলে কী হবে?", kinds_kb())
    await c.answer()


@admin.callback_query(NB.type, F.data.startswith("typ:"))
async def nb_type(c: CallbackQuery, state: FSMContext):
    t = c.data[4:]
    await state.update_data(ntype=t)
    if t in ("url", "web"):
        await state.set_state(NB.url)
        if t == "web":
            await tell(c.message, "🪟 Window (Web App) এর লিংক দিন। অবশ্যই <b>https://</b> দিয়ে শুরু হতে হবে:")
        else:
            await tell(c.message, "🔗 লিংক দিন (যেমন https://t.me/yourchannel):")
    else:
        await state.set_state(NB.kind)
        await tell(c.message, "⚙️ বাটনটি চাপলে কী হবে?", kinds_kb())
    await c.answer()


@admin.message(NB.url, F.text)
async def nb_url(m: Message, state: FSMContext):
    d = await state.get_data()
    if d.get("ntype") == "web":
        if not m.text.startswith("https://"):
            await m.answer("❌ Window বাটনের লিংক অবশ্যই https:// দিয়ে শুরু হতে হবে। আবার দিন:")
            return
    elif not m.text.startswith(("http://", "https://", "tg://")):
        await m.answer("❌ লিংক http:// অথবা https:// দিয়ে শুরু হতে হবে। আবার দিন:")
        return
    await state.update_data(url=m.text.strip())
    await finish_node(m, state)


@admin.callback_query(NB.kind, F.data.startswith("knd:"))
async def nb_kind(c: CallbackQuery, state: FSMContext):
    kind = c.data[4:]
    await state.update_data(kind=kind)
    if kind == "shopcat":
        db = load()
        if not db["categories"]:
            await c.answer("❌ আগে বিজনেস মেনু → ক্যাটাগরি থেকে একটি ক্যাটাগরি বানান", show_alert=True)
            return
        await state.set_state(NB.cat)
        rows = [[B(node_label(db, ct)[:50], "nkc:" + ct["id"], icon=node_cid(db, ct))] for ct in db["categories"].values()]
        await tell(c.message, "📂 কোন ক্যাটাগরির প্রডাক্ট লিস্ট দেখাবে? ক্যাটাগরি বেছে নিন:", KB(rows[:90]))
        await c.answer()
        return
    if kind == "input":
        await state.set_state(NB.reply)
        await tell(
            c.message,
            "✍️ ইউজার বাটন চাপলে কী মেসেজ দেখবে তা লিখুন (ছবি + ক্যাপশনও দেওয়া যায়)\n"
            "যেমন: <i>আপনার নম্বরটি পাঠান</i>\n\n"
            "ইউজার যা পাঠাবে (লেখা/ছবি) তা আপনার কাছে Approve/Reject বাটনসহ আসবে।",
        )
    elif kind == "text":
        await state.set_state(NB.reply)
        await tell(
            c.message,
            "✍️ বাটন চাপলে ইউজার যে মেসেজ দেখবে তা লিখুন।\n"
            "ছবি পাঠালে ক্যাপশনসহ ছবি যাবে।\n"
            "বোল্ড: &lt;b&gt;লেখা&lt;/b&gt;\n"
            "ব্যবহারযোগ্য: {name} {balance} {refs} {link} {currency} {support}\n"
            "🎭 %name% %username% %firstname% %lastname% %number% = প্রতিবার আলাদা র‍্যান্ডম\n"
            "✨ অ্যাপের ইমোজি: {ic:bkash} {ic:nagad} ... (কোড পেতে প্যানেল → ✨ Message Formatting Emoji)",
        )
    else:
        await finish_node(c.message, state)
    await c.answer()


@admin.callback_query(NB.cat, F.data.startswith("nkc:"))
async def nb_cat(c: CallbackQuery, state: FSMContext):
    cid = c.data[4:]
    if cid not in load()["categories"]:
        await c.answer("❌ ক্যাটাগরি পাওয়া যায়নি", show_alert=True)
        return
    await state.update_data(cat=cid)
    await finish_node(c.message, state)
    await c.answer()


@admin.message(NB.reply, F.text | F.photo)
async def nb_reply(m: Message, state: FSMContext):
    text, photo = extract_reply(m)
    await state.update_data(reply=text, photo=photo)
    data = await state.get_data()
    if data["kind"] == "input":
        await state.set_state(NB.done_msg)
        await tell(m, "✅ ইউজার সাবমিট করার পর কী মেসেজ পাবে তা লিখুন:")
    else:
        await finish_node(m, state)


@admin.message(NB.done_msg, F.text)
async def nb_done(m: Message, state: FSMContext):
    await state.update_data(done_msg=m.text)
    await state.set_state(NB.reward)
    await tell(m, "🎁 Approve করলে ইউজার কত রিওয়ার্ড পাবে? (সংখ্যা লিখুন, না দিলে 0)")


@admin.message(NB.reward, F.text)
async def nb_reward(m: Message, state: FSMContext):
    v = parse_num(m.text)
    if v is None or v < 0:
        await m.answer("❌ সঠিক সংখ্যা লিখুন (যেমন 10 অথবা 0):")
        return
    await state.update_data(reward=v)
    await finish_node(m, state)


async def finish_node(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    mode = data["mode"]
    node = {"id": new_id(), "text": data["text"], "style": data.get("style"), "icon": data.get("icon", "")}
    if data.get("ntype") in ("url", "web"):
        node.update(type=data["ntype"], value=data["url"])
    else:
        kind = data["kind"]
        # ব্যালেন্স/রেফার/উইথড্র: মেসেজ সেটিং থেকে প্রিমিয়াম টেমপ্লেট আসবে, তাই এখানে খালি রাখা হয়
        default_text = "" if kind in TPL_KINDS or kind == "shopcat" else DEFAULT_REPLY.get(kind, "")
        node.update(
            type="act",
            kind=kind,
            reply=data.get("reply") or default_text,
            photo=data.get("photo"),
            inline=[],
        )
        if mode in ("menu", "sub"):
            node["children"] = []
        if kind == "shopcat":
            node["cat"] = data.get("cat", "")
        if kind == "input":
            node["done_msg"] = data.get("done_msg", "✅ আপনার সাবমিশন জমা হয়েছে")
            node["reward"] = float(data.get("reward", 0))
    parent = None
    if mode == "menu":
        db["menu"].append(node)
    else:
        parent = get_node(db, data.get("parent", ""))
        if parent is None:
            await state.clear()
            await tell(m, "❌ মূল বাটন পাওয়া যায়নি")
            return
        key = "children" if mode == "sub" else "inline"
        parent.setdefault(key, []).append(node)
    save(db)
    await state.clear()
    await tell(m, "✅ বাটন যোগ হয়েছে!", main_kb(db))
    if mode == "inline":
        await deliver(m.bot, m.chat.id, "প্রিভিউ:", inline_kb(parent))
    await show_panel(m)


# ---------- এডিট ----------
@admin.callback_query(F.data == "adm:edit")
async def edit_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await tell(c.message, "✏️ কোনটি এডিট করবেন?", targets_kb(load(), "edt", "edit"))
    await c.answer()


@admin.callback_query(F.data.startswith("edt:"))
async def edit_pick(c: CallbackQuery):
    db = load()
    nid = c.data[4:]
    n = get_node(db, nid)
    if n is None:
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    rows = []
    is_url = n.get("type") in ("url", "web")
    if not is_url:
        rows.append([B("📝 মেসেজ / ছবি বদলান", f"ef:reply:{nid}")])
    if nid != "start":
        rows.append([B("✏️ বাটনের নাম বদলান", f"ef:text:{nid}")])
        rows.append([B("🎨 বাটনের রং বদলান", f"ef:color:{nid}")])
        rows.append([B("🌟 স্টিকার / আইকন বদলান", f"ef:icon:{nid}")])
    if is_url:
        rows.append([B("🔗 লিংক বদলান", f"ef:url:{nid}")])
    if n.get("kind") == "input":
        rows.append([B("✅ সাবমিট-পরবর্তী মেসেজ", f"ef:done:{nid}")])
        rows.append([B("🎁 Approve রিওয়ার্ড", f"ef:reward:{nid}")])
    rows.append(back_row("adm:btn"))
    await tell(c.message, f"✏️ <b>{esc(n.get('text', 'স্টার্ট মেসেজ'))}</b> — কী বদলাবেন?", KB(rows))
    await c.answer()


@admin.callback_query(F.data.startswith("ef:"))
async def edit_field(c: CallbackQuery, state: FSMContext):
    _, field, nid = c.data.split(":")
    await state.clear()
    if field == "icon":
        db = load()
        n = get_node(db, nid)
        if n is None:
            await c.answer("❌ পাওয়া যায়নি", show_alert=True)
            return
        await tell(
            c.message,
            f"🌟 <b>{esc(n['text'])}</b> এর জন্য স্টিকার / আইকন বেছে নিন:",
            icon_picker_kb(db, f"nei:{nid}:", n["text"], back=f"edt:{nid}"),
        )
        await c.answer()
        return
    await state.update_data(field=field, nid=nid)
    if field == "color":
        await state.set_state(EN.color)
        await tell(c.message, "🎨 নতুন রং বেছে নিন:", color_kb())
    else:
        await state.set_state(EN.value)
        hint = {
            "reply": "📝 নতুন মেসেজ লিখুন (ছবি দিতে চাইলে ছবি + ক্যাপশন পাঠান)\nব্যবহারযোগ্য: {balance} {refs} {link} {bonus} {currency} {min} {name} {id} {support} {bot} {methods} {method_icons}\n🎭 %name% %username% %firstname% %lastname% %number% = প্রতিবার আলাদা র‍্যান্ডম",
            "text": "✏️ নতুন নাম লিখুন:",
            "url": "🔗 নতুন লিংক দিন:",
            "done": "✅ নতুন মেসেজ লিখুন:",
            "reward": "🎁 নতুন রিওয়ার্ড (সংখ্যা) লিখুন:",
        }[field]
        await tell(c.message, hint)
    await c.answer()


@admin.callback_query(F.data.startswith("nei:"))
async def edit_icon_pick(c: CallbackQuery):
    _, nid, key = c.data.split(":", 2)
    db = load()
    n = get_node(db, nid)
    if n is None or (key != "-" and key not in db.get("icons", {})):
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    n["icon"] = "" if key == "-" else key
    save(db)
    await c.answer("✅ আইকন বদলানো হয়েছে")
    await tell(c.message, "✅ স্টিকার / আইকন সেট হয়েছে!", main_kb(db))
    await show_panel(c.message)


@admin.callback_query(EN.color, F.data.startswith("col:"))
async def edit_color(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db = load()
    n = get_node(db, data["nid"])
    if n is not None:
        n["style"] = COLORS[c.data[4:]][1]
        save(db)
    await state.clear()
    await tell(c.message, "✅ রং বদলানো হয়েছে!", main_kb(db))
    await show_panel(c.message)
    await c.answer()


@admin.message(EN.value, F.text | F.photo)
async def edit_value(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    n = get_node(db, data["nid"])
    field = data["field"]
    if n is None:
        await state.clear()
        await m.answer("❌ বাটন পাওয়া যায়নি")
        return
    if field == "reply":
        text, photo = extract_reply(m)
        n["reply"] = text
        n["photo"] = photo
    else:
        if not m.text:
            await m.answer("❌ লেখা পাঠান:")
            return
        if field == "text":
            n["text"] = m.text
        elif field == "url":
            if n.get("type") == "web":
                if not m.text.startswith("https://"):
                    await m.answer("❌ Window বাটনের লিংক অবশ্যই https:// দিয়ে শুরু হতে হবে:")
                    return
            elif not m.text.startswith(("http://", "https://", "tg://")):
                await m.answer("❌ লিংক http:// অথবা https:// দিয়ে শুরু হতে হবে:")
                return
            n["value"] = m.text.strip()
        elif field == "done":
            n["done_msg"] = m.text
        elif field == "reward":
            v = parse_num(m.text)
            if v is None or v < 0:
                await m.answer("❌ সঠিক সংখ্যা দিন:")
                return
            n["reward"] = v
    save(db)
    await state.clear()
    await tell(m, "✅ আপডেট হয়েছে!", main_kb(db))
    await show_panel(m)


# ---------- ডিলিট / লিস্ট ----------
@admin.callback_query(F.data == "adm:del")
async def del_list(c: CallbackQuery):
    await tell(c.message, "🗑 যে বাটন ডিলিট করবেন তাতে চাপুন:\n(ভেতরের সব সাব-বাটন ও ইনলাইন বাটনও মুছে যাবে)", delete_kb(load()))
    await c.answer()


@admin.callback_query(F.data.startswith("del:"))
async def del_do(c: CallbackQuery):
    db = load()
    remove_node(db, c.data[4:])
    save(db)
    try:
        await c.message.edit_reply_markup(reply_markup=delete_kb(db))
    except TelegramBadRequest:
        pass
    await tell(c.message, "✅ ডিলিট হয়েছে", main_kb(db))
    await c.answer()


@admin.callback_query(F.data == "adm:list")
async def list_all(c: CallbackQuery):
    await tell_long(c.message, tree_lines(load()))
    await c.answer()


# ---------- সেটিংস ----------
@admin.callback_query(F.data == "adm:settings")
async def settings_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await tell(c.message, "⚙️ <b>সেটিংস</b>\nযেটি বদলাবেন তাতে চাপুন:", settings_kb(load()))
    await c.answer()


@admin.callback_query(F.data.startswith("set:"))
async def settings_pick(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    await state.clear()
    await state.set_state(SetVal.value)
    await state.update_data(key=key)
    await tell(c.message, f"{SET_LABELS[key]} — নতুন মান লিখুন:")
    await c.answer()


@admin.message(SetVal.value, F.text)
async def settings_val(m: Message, state: FSMContext):
    data = await state.get_data()
    key = data["key"]
    db = load()
    if key in STR_KEYS:
        db["settings"][key] = m.text.strip()[:5 if key == "currency" else 40]
    else:
        v = parse_num(m.text)
        if v is None or v < 0 or (key == "ref_commission" and v > 100):
            await m.answer("❌ সঠিক সংখ্যা দিন:")
            return
        db["settings"][key] = v
    save(db)
    await state.clear()
    await tell(m, "✅ সেভ হয়েছে!", settings_kb(db))


@admin.callback_query(F.data.startswith("tgl:"))
async def toggle_setting(c: CallbackQuery):
    key = c.data[4:]
    if key not in ("cancel_on", "force_admins"):
        await c.answer()
        return
    db = load()
    db["settings"][key] = not db["settings"].get(key, key == "cancel_on")
    save(db)
    try:
        await c.message.edit_reply_markup(reply_markup=settings_kb(db))
    except TelegramBadRequest:
        pass
    await c.answer("✅ সেভ হয়েছে")


# ---------- Force Join ----------
async def force_menu(msg):
    db = load()
    lines = ["🔒 <b>Force Join</b>"]
    rows = []
    for i, ch in enumerate(db["force"]):
        lines.append(f"📢 {esc(ch.get('title') or ch['chat'])} ({esc(ch['chat'])})")
        rows.append([B("🗑 " + ch["chat"], f"fj:del:{i}")])
    if not db["force"]:
        lines.append("কোনো চ্যানেল নেই (বন্ধ আছে)")
    lines.append("\n⚠️ বটকে সেই চ্যানেলে <b>অ্যাডমিন</b> বানাতে হবে\n🧪 অ্যাডমিন আইডি দিয়ে টেস্ট করলে লক দেখা যায় না — সেটিংসে 'Force Join অ্যাডমিনের জন্যও' চালু করুন")
    rows.append([B("➕ চ্যানেল যোগ করুন", "fj:add")])
    rows.append(back_row("adm:settings"))
    await tell(msg, "\n".join(lines), KB(rows))


@admin.callback_query(F.data == "adm:force")
async def force_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await force_menu(c.message)
    await c.answer()


@admin.callback_query(F.data.startswith("fj:del:"))
async def force_del(c: CallbackQuery):
    db = load()
    i = int(c.data.split(":")[2])
    if 0 <= i < len(db["force"]):
        db["force"].pop(i)
        save(db)
    await force_menu(c.message)
    await c.answer()


@admin.callback_query(F.data == "fj:add")
async def force_add(c: CallbackQuery, state: FSMContext):
    await state.set_state(FJ.add)
    await tell(
        c.message,
        "📢 চ্যানেলের @ইউজারনেম দিন (যেমন @mychannel)\n"
        "প্রাইভেট চ্যানেল হলে -100 দিয়ে শুরু হওয়া আইডি দিন (যেমন -1001234567890)",
    )
    await c.answer()


async def fj_verify(m: Message, ref):
    me = await m.bot.me()
    mem = await m.bot.get_chat_member(ref, me.id)
    status = str(getattr(mem.status, "value", mem.status))
    if status not in ("administrator", "creator"):
        raise ValueError("বট এই চ্যানেলের অ্যাডমিন নয়")
    try:
        return (await m.bot.get_chat(ref)).title or ""
    except Exception:
        return ""


@admin.message(FJ.add, F.text)
async def force_add_val(m: Message, state: FSMContext):
    ch = m.text.strip()
    is_id = ch.startswith("-") and ch.lstrip("-").isdigit()
    if not is_id and not (ch.startswith("@") and len(ch) >= 3):
        await m.answer("❌ @ইউজারনেম অথবা -100... আইডি দিন (বাতিল: /cancel):")
        return
    try:
        title = await fj_verify(m, int(ch) if is_id else ch)
    except Exception as e:
        await m.answer(f"❌ চ্যানেল পাওয়া যায়নি অথবা বট সেখানে অ্যাডমিন নয়।\nকারণ: {esc(str(e)[:150])}\nঠিক করে আবার দিন:")
        return
    if is_id:
        await state.update_data(chat=ch, title=title)
        await state.set_state(FJ.link)
        await m.answer("🔗 চ্যানেলের ইনভাইট লিংক দিন (https://t.me/+...):")
        return
    db = load()
    db["force"].append({"chat": ch, "url": "https://t.me/" + ch[1:], "title": title})
    save(db)
    await state.clear()
    await force_menu(m)


@admin.message(FJ.link, F.text)
async def force_add_link(m: Message, state: FSMContext):
    url = m.text.strip()
    if not url.startswith("https://"):
        await m.answer("❌ লিংক https:// দিয়ে শুরু হতে হবে:")
        return
    data = await state.get_data()
    db = load()
    db["force"].append({"chat": data["chat"], "url": url, "title": data.get("title", "")})
    save(db)
    await state.clear()
    await force_menu(m)


# ---------- ইউজার ম্যানেজ ----------
@admin.callback_query(F.data == "adm:users")
async def users_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    db = load()
    await tell(
        c.message,
        f"👥 মোট ইউজার: <b>{len(db['users'])}</b>\n"
        f"🚫 ব্যান: <b>{sum(1 for u in db['users'].values() if u.get('banned'))}</b>",
        users_kb(),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("tl:"))
async def tools_pick(c: CallbackQuery, state: FSMContext):
    act = c.data[3:]
    db = load()
    await state.clear()
    if act == "list":
        cur = db["settings"]["currency"]
        items = list(db["users"].items())[-40:]
        lines = ["📋 <b>সর্বশেষ ৪০ জন ইউজার</b>"]
        for uid, u in items:
            flag = "🚫" if u.get("banned") else "✅"
            lines.append(f"{flag} <code>{uid}</code> {esc(u['name'])} — {money(u['balance'])} {cur} | 👥{u['refs']}")
        await tell_long(c.message, "\n".join(lines))
    elif act == "info":
        await state.set_state(Tools.info)
        await tell(c.message, "🔍 ইউজারের Telegram ID দিন:")
    elif act == "adjust":
        await state.set_state(Tools.adjust)
        await tell(
            c.message,
            "💰 ফরম্যাট: <code>আইডি পরিমাণ</code>\n"
            "যেমন <code>123456789 50</code> (যোগ) অথবা <code>123456789 -20</code> (কমানো)",
        )
    elif act == "ban":
        await state.set_state(Tools.ban)
        await tell(c.message, "🚫 ব্যান/আনব্যান করতে Telegram ID দিন:")
    elif act == "cast":
        await state.set_state(Tools.cast)
        await tell(c.message, "📢 সবাইকে যে মেসেজ পাঠাতে চান তা পাঠান (লেখা/ছবি/যেকোনো):")
    await c.answer()


@admin.message(Tools.info, F.text)
async def tools_info(m: Message, state: FSMContext):
    db = load()
    uid = m.text.strip()
    u = db["users"].get(uid)
    await state.clear()
    if not u:
        await m.answer("❌ এই আইডির ইউজার পাওয়া যায়নি")
        return
    cur = db["settings"]["currency"]
    refs = [(i, x) for i, x in db["users"].items() if x.get("referred_by") == uid]
    subs = sorted((s for s in db["subs"].values() if s["uid"] == uid), key=lambda s: s["time"], reverse=True)[:10]
    lines = [
        f"👤 <b>{esc(u['name'])}</b> (@{esc(u['username'] or '-')})",
        f"🆔 <code>{uid}</code>",
        f"💰 ব্যালেন্স: {money(u['balance'])} {cur}",
        f"👥 রেফার: {u['refs']} জন",
        f"🔗 যার রেফারে এসেছে: {u['referred_by'] or '-'}",
        f"🚫 ব্যান: {'হ্যাঁ' if u.get('banned') else 'না'}",
        f"\n<b>👥 রেফার করা ইউজার ({len(refs)})</b>",
    ]
    for i, x in refs[:15]:
        lines.append(f"• {esc(x['name'])} (<code>{i}</code>)")
    lines.append("\n<b>📜 সাম্প্রতিক হিস্টোরি (সর্বোচ্চ ১০)</b>")
    if not subs:
        lines.append("কিছু নেই")
    for s in subs:
        if s["type"] == "withdraw":
            lines.append(f"{STATUS_ICON[s['status']]} 💸 উইথড্র {money(s['amount'])} {cur} ({esc(s.get('method') or '-')})")
        else:
            lines.append(f"{STATUS_ICON[s['status']]} {esc(s['btn'])} — {money(s.get('reward', 0))} {cur}")
    await tell_long(m, "\n".join(lines))


@admin.message(Tools.adjust, F.text)
async def tools_adjust(m: Message, state: FSMContext):
    parts = m.text.split()
    db = load()
    if len(parts) != 2 or parts[0] not in db["users"] or parse_num(parts[1]) is None:
        await m.answer("❌ ফরম্যাট ঠিক নেই অথবা ইউজার নেই। আবার দিন (বাতিল: /cancel):")
        return
    amt = parse_num(parts[1])
    u = db["users"][parts[0]]
    u["balance"] = max(0.0, u["balance"] + amt)
    add_tx(db, parts[0], "admin", amt, "অ্যাডমিন অ্যাডজাস্ট")
    save(db)
    await state.clear()
    cur = db["settings"]["currency"]
    await m.answer(f"✅ নতুন ব্যালেন্স: {money(u['balance'])} {cur}")
    await deliver(
        m.bot,
        int(parts[0]),
        f"💰 অ্যাডমিন আপনার ব্যালেন্সে {'যোগ করেছেন' if amt >= 0 else 'কমিয়েছেন'}: {money(abs(amt))} {cur}\n"
        f"💎 বর্তমান ব্যালেন্স: {money(u['balance'])} {cur}",
    )


@admin.message(Tools.ban, F.text)
async def tools_ban(m: Message, state: FSMContext):
    db = load()
    u = db["users"].get(m.text.strip())
    if not u:
        await m.answer("❌ এই আইডির ইউজার পাওয়া যায়নি। আবার দিন (বাতিল: /cancel):")
        return
    u["banned"] = not u.get("banned", False)
    save(db)
    await state.clear()
    await m.answer("🚫 ইউজার ব্যান হয়েছে" if u["banned"] else "✅ ইউজার আনব্যান হয়েছে")


@admin.message(Tools.cast)
async def tools_cast(m: Message, state: FSMContext):
    await state.clear()
    db = load()
    ok = fail = 0
    await m.answer("⏳ পাঠানো হচ্ছে...")
    for uid, u in list(db["users"].items()):
        if u.get("banned"):
            continue
        try:
            await m.copy_to(int(uid))
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await m.answer(f"📢 ব্রডকাস্ট শেষ — সফল: {ok}, ব্যর্থ: {fail}")
    await show_panel(m)


# ---------- ব্রডকাস্ট / ব্যাকআপ ----------
@admin.callback_query(F.data == "adm:more")
async def more_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await tell(c.message, "📢 <b>ব্রডকাস্ট ও ব্যাকআপ</b>", more_kb())
    await c.answer()


@admin.callback_query(F.data == "adm:backup")
async def backup(c: CallbackQuery):
    save(load())
    await c.message.answer_document(FSInputFile(cur().db_file), caption="💾 ব্যাকআপ " + datetime.now(TZ).strftime("%d-%m-%Y %H:%M"))
    await c.answer()


# ============================== 👮 অ্যাডমিন ম্যানেজ (শুধু Owner) ==============================
async def admins_menu(msg):
    db = load()
    lines = ["👮 <b>অ্যাডমিন ম্যানেজমেন্ট</b>", f"👑 Owner: <code>{owner_id()}</code>"]
    rows = []
    for a in db["admins"]:
        u = db["users"].get(str(a))
        name = esc(u["name"]) if u else "অজানা"
        lines.append(f"👮 <code>{a}</code> — {name}")
        rows.append([B(f"🗑 {a} বাদ দিন", f"adr:{a}")])
    if not db["admins"]:
        lines.append("\nঅতিরিক্ত কোনো অ্যাডমিন নেই")
    lines.append("\nℹ️ নতুন অ্যাডমিনকে আগে বটে /start দিতে হবে")
    rows.append([B("➕ নতুন অ্যাডমিন যোগ", "ada")])
    rows.append(back_row())
    await tell(msg, "\n".join(lines), KB(rows))


@admin.callback_query(F.data == "adm:admins")
async def admins_open(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != owner_id():
        await c.answer("⛔ শুধু Owner এটি ব্যবহার করতে পারবেন", show_alert=True)
        return
    await state.clear()
    await admins_menu(c.message)
    await c.answer()


@admin.callback_query(F.data == "ada")
async def admin_add(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != owner_id():
        await c.answer("⛔ শুধু Owner", show_alert=True)
        return
    await state.set_state(AdminAdd.uid)
    await tell(c.message, "🆔 নতুন অ্যাডমিনের Telegram ID দিন:\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(AdminAdd.uid, F.text)
async def admin_add_val(m: Message, state: FSMContext):
    if m.from_user.id != owner_id():
        return
    t = m.text.strip()
    if not t.isdigit():
        await m.answer("❌ শুধু সংখ্যার আইডি দিন (বাতিল: /cancel):")
        return
    aid = int(t)
    db = load()
    if aid == owner_id() or aid in db["admins"]:
        await m.answer("ℹ️ ইনি আগে থেকেই অ্যাডমিন")
        await state.clear()
        return
    db["admins"].append(aid)
    save(db)
    await state.clear()
    await deliver(m.bot, aid, "👮 আপনাকে অ্যাডমিন বানানো হয়েছে!\nপ্যানেল খুলতে /admin লিখুন।")
    await admins_menu(m)


@admin.callback_query(F.data.startswith("adr:"))
async def admin_remove(c: CallbackQuery):
    if c.from_user.id != owner_id():
        await c.answer("⛔ শুধু Owner", show_alert=True)
        return
    db = load()
    aid = int(c.data[4:])
    if aid in db["admins"]:
        db["admins"].remove(aid)
        save(db)
        await deliver(c.bot, aid, "ℹ️ আপনাকে অ্যাডমিন থেকে সরানো হয়েছে।")
    await admins_menu(c.message)
    await c.answer("✅ বাদ দেওয়া হয়েছে")


# ============================== 💬 মেসেজ সেটিং ==============================
@admin.callback_query(F.data == "adm:msgs")
async def msgs_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = [[B(label, "msg:" + k)] for k, label in MSG_LABELS.items()]
    rows.append([B("🔄 সব ব্যালেন্স/রেফার/উইথড্র বাটনে এই মেসেজ প্রয়োগ", "msgapply")])
    rows.append(back_row())
    await tell(
        c.message,
        "💬 <b>মেসেজ সেটিং</b>\nইউজার যে প্রিমিয়াম মেসেজ দেখে সেগুলো এখান থেকে বদলাতে পারবেন।\n"
        "যেটি বদলাবেন তাতে চাপুন:",
        KB(rows),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("msg:"))
async def msg_pick(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    if key not in MSG_LABELS:
        await c.answer()
        return
    db = load()
    await state.clear()
    await state.set_state(MsgEdit.value)
    await state.update_data(key=key)
    extra = "{amount} {method} {account} " if key.startswith("wd_") else ""
    await tell(
        c.message,
        f"{MSG_LABELS[key]}\n\n<b>বর্তমান মেসেজ:</b>\n<pre>{esc(get_msg(db, key))}</pre>\n"
        f"নতুন মেসেজ লিখুন (HTML চলবে, যেমন &lt;b&gt;বোল্ড&lt;/b&gt;)\n"
        f"ব্যবহারযোগ্য: {extra}{{balance}} {{refs}} {{link}} {{bonus}} {{currency}} {{min}} {{name}} {{id}} {{support}} {{methods}} {{method_icons}}\n\n"
        "(বাতিল: /cancel)",
        KB([[B("♻️ ডিফল্টে ফিরুন", "msgr:" + key)]]),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("msgr:"))
async def msg_reset(c: CallbackQuery, state: FSMContext):
    key = c.data[5:]
    db = load()
    db["settings"].setdefault("msgs", {}).pop(key, None)
    save(db)
    await state.clear()
    await tell(c.message, "♻️ ডিফল্ট প্রিমিয়াম মেসেজে ফেরানো হয়েছে")
    await c.answer()


@admin.message(MsgEdit.value, F.text)
async def msg_set(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    db["settings"].setdefault("msgs", {})[data["key"]] = m.text
    save(db)
    await state.clear()
    await m.answer("✅ মেসেজ সেভ হয়েছে!")
    await show_panel(m)


@admin.callback_query(F.data == "msgapply")
async def msg_apply(c: CallbackQuery):
    db = load()
    n = 0
    for node in all_nodes(db):
        if node.get("kind") in TPL_KINDS and node.get("reply"):
            node["reply"] = ""
            n += 1
    save(db)
    await tell(c.message, f"✅ {n} টি বাটনে প্রিমিয়াম মেসেজ প্রয়োগ হয়েছে")
    await c.answer()


# ============================== 🎯 টাস্ক ম্যানেজ ==============================
@admin.callback_query(F.data == "adm:tasks")
async def tasks_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    db = load()
    cur = db["settings"]["currency"]
    lines = ["🎯 <b>টাস্ক লিস্ট</b>"]
    rows = []
    for t in db["tasks"].values():
        n = task_counts(db, t["id"])
        kind = f"💬 মেসেজ টাস্ক ({len(t['steps'])} ধাপ)" if t.get("steps") else ("💬 মেসেজ টাস্ক" if t.get("prompt") else "📋 সাধারণ টাস্ক")
        place = task_place_label(db, t)
        if t.get("parent"):
            kind = kind.replace("💬 মেসেজ টাস্ক", "🔘 বাটন টাস্ক")
        rep = "🔁 বারবার" if t.get("repeat") else "☝️ একবার"
        lines.append(
            f"\n{'🟢' if t['active'] else '🔴'} <b>{esc(t['title'])}</b> — {money(t['reward'])} {cur}\n"
            f"   {kind} | {place} | {rep} | 🎨 {t.get('style') or 'default'}\n"
            f"   🔗 {esc(t['link'] or '-')}\n"
            f"   ✅ {n['approved']} | ⏳ {n['pending']} | ❌ {n['rejected']}"
        )
        rows.append(
            [
                B(("🔴 বন্ধ করুন: " if t["active"] else "🟢 চালু করুন: ") + t["title"][:20], "atk:tog:" + t["id"]),
                B("🗑", "atk:del:" + t["id"]),
            ]
        )
    if not db["tasks"]:
        lines.append("\nকোনো টাস্ক নেই")
    rows.append([B("➕ নতুন টাস্ক যোগ", "atk:add")])
    rows.append(back_row())
    await tell_long(c.message, "\n".join(lines))
    await tell(c.message, "👇 অপশন:", KB(rows))
    await c.answer()


@admin.callback_query(F.data.startswith("atk:tog:"))
async def task_toggle(c: CallbackQuery):
    db = load()
    t = db["tasks"].get(c.data.split(":")[2])
    if t:
        t["active"] = not t["active"]
        save(db)
    await c.answer("🟢 চালু" if t and t["active"] else "🔴 বন্ধ")
    await tell(c.message, "✅ আপডেট হয়েছে", main_kb(db))
    await tell(c.message, "টাস্ক লিস্টে ফিরুন:", KB([[B("🔙 টাস্ক লিস্ট", "adm:tasks")]]))


@admin.callback_query(F.data.startswith("atk:del:"))
async def task_delete(c: CallbackQuery):
    db = load()
    db["tasks"].pop(c.data.split(":")[2], None)
    save(db)
    await c.answer("🗑 ডিলিট হয়েছে")
    await tell(c.message, "🗑 টাস্ক ডিলিট হয়েছে", main_kb(db))
    await tell(c.message, "টাস্ক লিস্টে ফিরুন:", KB([[B("🔙 টাস্ক লিস্ট", "adm:tasks")]]))


@admin.callback_query(F.data == "atk:add")
async def task_add(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await tell(
        c.message,
        "➕ <b>কোন ধরনের টাস্ক যোগ করবেন?</b>\n\n"
        "📋 <b>সাধারণ টাস্ক</b> = নাম + লিংক + রিওয়ার্ড (ইউজার একবারই জমা দিতে পারবে)\n\n"
        "💬 <b>মেসেজ টাস্ক</b> = লিংক লাগবে না। আপনি যত খুশি ধাপ বানাতে পারবেন (যেমন: নাম → নম্বর → আবেদনের কারণ), "
        "ইউজার একের পর এক উত্তর দেবে। প্রতি ধাপে URL বাটনও দেওয়া যাবে\n\n"
        "🔘 <b>বাটন টাস্ক</b> = বাটনের নাম লিখবেন, কোন বাটন চাপলে এটি আসবে তা বেছে নেবেন, তারপর ইউজার কী পাঠাবে তা ধাপে ধাপে লিখবেন",
        KB(
            [
                [B("📋 সাধারণ টাস্ক", "atk:new:simple")],
                [B("💬 মেসেজ টাস্ক (কাস্টম)", "atk:new:msg")],
                [B("🔘 বাটন টাস্ক (বাটনের ভেতরে বসবে)", "atk:new:btn")],
                back_row("adm:tasks"),
            ]
        ),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("atk:new:"))
async def task_new(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(ttype=c.data.split(":")[2], steps=[], task_btns=[], cur_btns=[])
    await state.set_state(TaskAdd.title)
    await tell(c.message, "✍️ টাস্কের নাম লিখুন (এটিই বাটনের নাম হবে):\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(TaskAdd.title, F.text)
async def task_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:60])
    data = await state.get_data()
    if data["ttype"] == "btn":
        await state.set_state(TaskAdd.color)
        await tell(m, "🎨 বাটনের রং বেছে নিন:", color_kb())
    elif data["ttype"] == "msg":
        await state.set_state(TaskAdd.desc)
        await tell(m, "📝 <b>কোন কাজ করতে হবে</b> তা লিখুন (ইউজার টাস্ক খুললে এই বিবরণ দেখবে):")
    else:
        await state.set_state(TaskAdd.link)
        await tell(m, "🔗 টাস্কের লিংক দিন (লিংক না থাকলে - লিখুন):")


@admin.message(TaskAdd.link, F.text)
async def task_link(m: Message, state: FSMContext):
    link = m.text.strip()
    if link != "-" and not link.startswith(("http://", "https://", "tg://")):
        await m.answer("❌ লিংক http:// অথবা https:// দিয়ে শুরু হতে হবে, অথবা - লিখুন:")
        return
    await state.update_data(link="" if link == "-" else link)
    await state.set_state(TaskAdd.reward)
    await tell(m, "🎁 Approve করলে ইউজার কত রিওয়ার্ড পাবে? (সংখ্যা):")


@admin.message(TaskAdd.desc, F.text)
async def task_desc(m: Message, state: FSMContext):
    await state.update_data(desc=m.text)
    await state.set_state(TaskAdd.color)
    await tell(m, "🎨 টাস্ক বাটনের রং বেছে নিন:", color_kb())


async def ask_btns(msg, state: FSMContext, target):
    await state.update_data(target=target)
    await state.set_state(TaskAdd.btnmenu)
    data = await state.get_data()
    lst = data.get("task_btns" if target == "task" else "cur_btns", [])
    where = "টাস্কের বিবরণের নিচে" if target == "task" else "এই মেসেজের নিচে"
    await tell(
        msg,
        f"🔗 {where} URL বাটন যোগ করবেন?\n(এখন পর্যন্ত যোগ হয়েছে: {len(lst)} টি)",
        KB([[B("➕ URL বাটন যোগ", "tb:add")], [B("➡️ এগিয়ে যান", "tb:next")]]),
    )


@admin.callback_query(TaskAdd.btnmenu, F.data == "tb:add")
async def tb_add(c: CallbackQuery, state: FSMContext):
    await state.set_state(TaskAdd.urltext)
    await tell(c.message, "✍️ URL বাটনের নাম লিখুন (যেমন: চ্যানেলে যান):")
    await c.answer()


@admin.message(TaskAdd.urltext, F.text)
async def tb_text(m: Message, state: FSMContext):
    await state.update_data(btn_text=m.text.strip()[:40])
    await state.set_state(TaskAdd.urlurl)
    await tell(m, "🔗 বাটনের লিংক দিন (https://...):")


@admin.message(TaskAdd.urlurl, F.text)
async def tb_url(m: Message, state: FSMContext):
    url = m.text.strip()
    if not url.startswith(("http://", "https://", "tg://")):
        await m.answer("❌ লিংক http:// অথবা https:// দিয়ে শুরু হতে হবে:")
        return
    data = await state.get_data()
    key = "task_btns" if data.get("target") == "task" else "cur_btns"
    lst = list(data.get(key, []))
    lst.append({"text": data["btn_text"], "url": url})
    await state.update_data({key: lst})
    await ask_btns(m, state, data.get("target"))


@admin.callback_query(TaskAdd.btnmenu, F.data == "tb:next")
async def tb_next(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("target") == "task":
        await state.set_state(TaskAdd.color)
        await tell(c.message, "🎨 টাস্ক বাটনের রং বেছে নিন:", color_kb())
    else:
        steps = list(data.get("steps", []))
        steps.append({"q": data["cur_q"], "buttons": data.get("cur_btns", [])})
        await state.update_data(steps=steps, cur_btns=[], cur_q="")
        await state.set_state(TaskAdd.stepmore)
        await tell(
            c.message,
            f"✅ ধাপ {len(steps)} যোগ হয়েছে।\nআরও মেসেজ (প্রশ্ন) যোগ করবেন?",
            KB(
                [
                    [B(f"➕ ধাপ {len(steps) + 1} যোগ করুন", "stm:more")],
                    [B("✅ শেষ, এগিয়ে যান", "stm:end")],
                ]
            ),
        )
    await c.answer()


@admin.callback_query(TaskAdd.color, F.data.startswith("col:"))
async def task_color(c: CallbackQuery, state: FSMContext):
    await state.update_data(style=COLORS[c.data[4:]][1])
    if (await state.get_data()).get("ttype") == "btn":
        await state.set_state(TaskAdd.parent)
        await tell(
            c.message,
            "📌 <b>কোন বাটন চাপলে এই বাটনটি আসবে?</b>\nনিচ থেকে বেছে নিন:\n(বাতিল: /cancel)",
            targets_kb(load(), "tbp", "inline"),
        )
        await c.answer()
        return
    await state.set_state(TaskAdd.place)
    await tell(
        c.message,
        "📍 <b>বাটনটি কোথায় থাকবে?</b>\n\n"
        "⌨️ <b>কিবোর্ড বাটন</b> = নিচের মেইন কিবোর্ডে আলাদা বাটন হিসেবে\n"
        "🔘 <b>মেনু/ইনলাইন বাটন</b> = '🎯 টাস্ক' লিস্টের ভেতরে ইনলাইন বাটন হিসেবে",
        KB([[B("⌨️ কিবোর্ড বাটন", "tpl:keyboard")], [B("🔘 মেনু / ইনলাইন বাটন", "tpl:inline")]]),
    )
    await c.answer()


@admin.callback_query(TaskAdd.place, F.data.startswith("tpl:"))
async def task_place(c: CallbackQuery, state: FSMContext):
    await state.update_data(place=c.data[4:])
    await state.set_state(TaskAdd.step)
    await tell(
        c.message,
        "💬 <b>ধাপ ১</b>: ইউজারকে প্রথম কী মেসেজ দেখাবেন তা লিখুন।\n"
        "ইউজার এর উত্তর পাঠালে পরের ধাপের মেসেজ আসবে।\n"
        "যেমন: <i>আপনার নাম লিখুন</i>",
    )
    await c.answer()


BTN_STEP1 = (
    "💬 <b>ধাপ ১</b>: ইউজারকে কী পাঠাতে বলবেন তা লিখুন।\n"
    "ইউজার পাঠালে পরের ধাপের মেসেজ আসবে।\n"
    "যেমন: <i>আপনার নম্বরটি পাঠান</i>"
)


@admin.callback_query(TaskAdd.parent, F.data.startswith("tbp:"))
async def task_parent(c: CallbackQuery, state: FSMContext):
    db = load()
    pid = c.data[4:]
    if get_node(db, pid) is None:
        await c.answer("❌ বাটন পাওয়া যায়নি", show_alert=True)
        return
    await state.update_data(parent=pid)
    if pid in {n["id"] for n in menu_nodes(db["menu"])}:
        await state.set_state(TaskAdd.pplace)
        await tell(
            c.message,
            "📍 <b>বাটনটি কীভাবে আসবে?</b>\n\n"
            "⌨️ <b>কিবোর্ড বাটন</b> = ওই মেনুর নিচের কিবোর্ডে আসবে\n"
            "🔘 <b>ইনলাইন বাটন</b> = ওই বাটনের মেসেজের নিচে আসবে",
            KB([[B("⌨️ কিবোর্ড বাটন", "tpp:kb")], [B("🔘 ইনলাইন বাটন", "tpp:inline")]]),
        )
    else:
        await state.update_data(place="parent_inline")
        await state.set_state(TaskAdd.step)
        await tell(c.message, BTN_STEP1)
    await c.answer()


@admin.callback_query(TaskAdd.pplace, F.data.startswith("tpp:"))
async def task_pplace(c: CallbackQuery, state: FSMContext):
    await state.update_data(place="parent_kb" if c.data[4:] == "kb" else "parent_inline")
    await state.set_state(TaskAdd.step)
    await tell(c.message, BTN_STEP1)
    await c.answer()


@admin.message(TaskAdd.step, F.text)
async def task_step(m: Message, state: FSMContext):
    data = await state.get_data()
    steps = list(data.get("steps", []))
    steps.append({"q": m.text, "buttons": []})
    await state.update_data(steps=steps)
    await state.set_state(TaskAdd.stepmore)
    await tell(
        m,
        f"✅ ধাপ {len(steps)} যোগ হয়েছে।\nআরও মেসেজ (প্রশ্ন) যোগ করবেন?",
        KB(
            [
                [B(f"➕ ধাপ {len(steps) + 1} যোগ করুন", "stm:more")],
                [B("✅ শেষ, এগিয়ে যান", "stm:end")],
            ]
        ),
    )


@admin.callback_query(TaskAdd.stepmore, F.data == "stm:more")
async def stm_more(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    n = len(data.get("steps", [])) + 1
    await state.set_state(TaskAdd.step)
    await tell(c.message, f"💬 <b>ধাপ {n}</b>: আগের উত্তরের পর ইউজার কোন মেসেজ দেখবে তা লিখুন:")
    await c.answer()


@admin.callback_query(TaskAdd.stepmore, F.data == "stm:end")
async def stm_end(c: CallbackQuery, state: FSMContext):
    await state.set_state(TaskAdd.done)
    hint = "\n(ডিফল্ট মেসেজের জন্য - লিখুন)" if (await state.get_data()).get("ttype") == "btn" else ""
    await tell(c.message, "✅ সব ধাপ শেষ হলে ইউজার কী মেসেজ পাবে তা লিখুন:" + hint)
    await c.answer()


@admin.message(TaskAdd.done, F.text)
async def task_done_msg(m: Message, state: FSMContext):
    d = await state.get_data()
    dm = "" if d.get("ttype") == "btn" and m.text.strip() == "-" else m.text
    await state.update_data(done_msg=dm)
    await state.set_state(TaskAdd.reward)
    await tell(m, "🎁 প্রতিবার Approve করলে ইউজার কত রিওয়ার্ড পাবে? (সংখ্যা):")


@admin.message(TaskAdd.reward, F.text)
async def task_reward(m: Message, state: FSMContext):
    v = parse_num(m.text)
    if v is None or v < 0:
        await m.answer("❌ সঠিক সংখ্যা দিন:")
        return
    await state.update_data(reward=v)
    data = await state.get_data()
    if data["ttype"] in ("msg", "btn"):
        await state.set_state(TaskAdd.repeat)
        await tell(
            m,
            "🔁 <b>ইউজার কি একই টাস্কে বারবার মেসেজ পাঠাতে পারবে?</b>",
            KB([[B("🔁 হ্যাঁ, বারবার পারবে", "trp:1")], [B("☝️ না, একবারই", "trp:0")]]),
        )
    else:
        await finish_task(m, state, repeat=False)


@admin.callback_query(TaskAdd.repeat, F.data.startswith("trp:"))
async def task_repeat(c: CallbackQuery, state: FSMContext):
    await finish_task(c.message, state, repeat=c.data[4:] == "1")
    await c.answer()


async def finish_task(m, state: FSMContext, repeat: bool):
    data = await state.get_data()
    db = load()
    tid = new_id()
    is_msg = data.get("ttype") in ("msg", "btn")
    db["tasks"][tid] = {
        "id": tid,
        "title": data["title"],
        "desc": data.get("desc", ""),
        "link": data.get("link", ""),
        "btns": data.get("task_btns", []) if is_msg else [],
        "steps": data.get("steps", []) if is_msg else [],
        "reward": data["reward"],
        "style": data.get("style"),
        "place": data.get("place", "inline"),
        "parent": data.get("parent", "") if data.get("ttype") == "btn" else "",
        "prompt": "",
        "done_msg": data.get("done_msg", "") if is_msg else "",
        "repeat": repeat,
        "active": True,
        "time": int(time.time()),
    }
    save(db)
    await state.clear()
    await tell(m, "✅ টাস্ক যোগ হয়েছে!", main_kb(db))
    await show_panel(m)


# ============================== 💸 উইথড্র (অ্যাডমিন) ==============================
@admin.callback_query(F.data == "adm:wd")
async def wd_open(c: CallbackQuery):
    db = load()
    cur = db["settings"]["currency"]
    subs = [(sid, s) for sid, s in db["subs"].items() if s["type"] == "withdraw"]
    pend = [(sid, s) for sid, s in subs if s["status"] == "pending"]
    ok = sum(1 for _, s in subs if s["status"] == "approved")
    rej = sum(1 for _, s in subs if s["status"] == "rejected")
    await tell(
        c.message,
        f"💸 <b>উইথড্র ম্যানেজ</b>\n"
        f"⏳ পেন্ডিং: {len(pend)} | ✅ সফল: {ok} | ❌ বাতিল: {rej}\n"
        f"💳 ন্যূনতম: {money(global_min(db))} {cur}\n"
        f"🏦 মাধ্যম: {len(db['wd_methods'])} টি",
        KB(
            [
                [B("🏦 উইথড্র মাধ্যম সেট করুন", "adm:wdm")],
                [B("✏️ সাধারণ ন্যূনতম উইথড্র বদলান", "set:min_withdraw")],
                back_row(),
            ]
        ),
    )
    for sid, s in pend[:15]:
        await tell(c.message, withdraw_text(db, s), approve_kb("wd", sid))
    if len(pend) > 15:
        await tell(c.message, f"➕ আরও {len(pend) - 15} টি পেন্ডিং আছে, এগুলো শেষ করে আবার খুলুন")
    await c.answer()


def color_label(style):
    return next((v[0] for v in COLORS.values() if v[1] == style), COLORS["none"][0])


async def methods_menu(msg):
    db = load()
    cur = db["settings"]["currency"]
    lines = ["🏦 <b>উইথড্র মাধ্যম</b>"]
    rows = []
    for m in db["wd_methods"]:
        ic = icon_of(db, m.get("icon"))
        lines.append(
            f"\n💳 <b>{method_text(db, m)}</b>\n"
            f"   ন্যূনতম: {money(method_min(db, m))} {cur}\n"
            f"   নির্দেশ: {esc(m.get('hint') or '-')}\n"
            f"   বাটনের রং: {color_label(m.get('style'))}"
        )
        rows.append(
            [
                B(("✏️ " + m["name"])[:30], "awm:ed:" + m["id"], style=m.get("style"), icon=(ic or {}).get("cid") or None),
                B(("🗑 " + m["name"])[:30], "awm:del:" + m["id"]),
            ]
        )
    if not db["wd_methods"]:
        lines.append("\nকোনো মাধ্যম নেই। মাধ্যম না থাকলে ইউজার সরাসরি অ্যাকাউন্ট নম্বর লিখবে।")
    rows.append([B("➕ নতুন মাধ্যম যোগ", "awm:add")])
    rows.append(back_row("adm:wd"))
    await tell(msg, "\n".join(lines), KB(rows))


@admin.callback_query(F.data == "adm:wdm")
async def methods_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await methods_menu(c.message)
    await c.answer()


@admin.callback_query(F.data.startswith("awm:del:"))
async def method_del(c: CallbackQuery):
    db = load()
    mid = c.data.split(":")[2]
    db["wd_methods"] = [m for m in db["wd_methods"] if m["id"] != mid]
    save(db)
    await methods_menu(c.message)
    await c.answer("🗑 ডিলিট হয়েছে")


@admin.callback_query(F.data == "awm:add")
async def method_add(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(WM.name)
    await tell(c.message, "🏦 মাধ্যমের নাম লিখুন (যেমন bKash, Nagad, Rocket, Binance):\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(WM.name, F.text)
async def method_name(m: Message, state: FSMContext):
    name = m.text.strip()[:30]
    await state.update_data(name=name)
    await state.set_state(WM.icon)
    await tell(
        m,
        f"🎨 <b>{esc(name)}</b> বাটনের নামের আগে কোন স্টিকার / আইকন লাগাবেন? বেছে নিন:\n"
        "(নামের সাথে মিলে যাওয়া আইকন উপরে দেখাচ্ছে)",
        icon_picker_kb(load(), "wmi:", name),
    )


@admin.callback_query(WM.icon, F.data.startswith("wmi:"))
async def method_icon_pick(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    db = load()
    if key != "-" and key not in db.get("icons", {}):
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    await state.update_data(icon="" if key == "-" else key)
    await state.set_state(WM.color)
    await tell(c.message, "🌈 কিবোর্ড বাটনের রং বেছে নিন:", color_kb())
    await c.answer()


@admin.callback_query(WM.color, F.data.startswith("col:"))
async def method_color_pick(c: CallbackQuery, state: FSMContext):
    await state.update_data(style=COLORS[c.data[4:]][1])
    await state.set_state(WM.minimum)
    await tell(c.message, "💳 এই মাধ্যমে ন্যূনতম কত উইথড্র করা যাবে? (সংখ্যা, সাধারণ ন্যূনতম ব্যবহার করতে 0 লিখুন):")
    await c.answer()


@admin.message(WM.icon)
@admin.message(WM.color)
async def method_pick_hint(m: Message):
    await m.answer("👆 উপরের বাটন থেকে বেছে নিন (বাতিল: /cancel)")


@admin.message(WM.minimum, F.text)
async def method_min_val(m: Message, state: FSMContext):
    v = parse_num(m.text)
    if v is None or v < 0:
        await m.answer("❌ সঠিক সংখ্যা দিন:")
        return
    await state.update_data(minimum=v)
    await state.set_state(WM.hint)
    await tell(m, "✍️ ইউজার অ্যাকাউন্ট দেওয়ার সময় কী নির্দেশ দেখবে? (যেমন: আপনার bKash নম্বর লিখুন):")


@admin.message(WM.hint, F.text)
async def method_hint(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    db["wd_methods"].append(
        {
            "id": new_id(),
            "name": data["name"],
            "min": data["minimum"],
            "hint": m.text.strip(),
            "icon": data.get("icon", ""),
            "style": data.get("style"),
        }
    )
    save(db)
    await state.clear()
    await m.answer("✅ মাধ্যম যোগ হয়েছে!")
    await methods_menu(m)


# ---------- মাধ্যম এডিট (আইকন / রং) ----------
async def method_edit_menu(msg, mid):
    db = load()
    mt = get_method(db, mid)
    if not mt:
        await methods_menu(msg)
        return
    ic = icon_of(db, mt.get("icon"))
    await tell(
        msg,
        f"✏️ <b>{method_text(db, mt)}</b>\n{LINE}\n"
        f"🎨 আইকন: {esc(ic['name']) if ic else 'নেই'}"
        f"{' (স্টিকার সেট আছে ✅)' if ic and ic.get('cid') else ''}\n"
        f"🌈 বাটনের রং: {color_label(mt.get('style'))}",
        KB(
            [
                [B("🎨 আইকন / স্টিকার বদলান", "awm:ei:" + mid)],
                [B("🌈 বাটনের রং বদলান", "awm:ec:" + mid)],
                back_row("adm:wdm"),
            ]
        ),
    )


@admin.callback_query(F.data.startswith("awm:ed:"))
async def method_edit_open(c: CallbackQuery):
    await method_edit_menu(c.message, c.data.split(":")[2])
    await c.answer()


@admin.callback_query(F.data.startswith("awm:ei:"))
async def method_edit_icon(c: CallbackQuery):
    db = load()
    mid = c.data.split(":")[2]
    mt = get_method(db, mid)
    if not mt:
        await c.answer("❌ মাধ্যম পাওয়া যায়নি", show_alert=True)
        return
    await tell(
        c.message,
        f"🎨 <b>{esc(mt['name'])}</b> এর জন্য স্টিকার / আইকন বেছে নিন:",
        icon_picker_kb(db, f"wme:{mid}:", mt["name"], back="awm:ed:" + mid),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("wme:"))
async def method_edit_icon_pick(c: CallbackQuery):
    _, mid, key = c.data.split(":", 2)
    db = load()
    mt = get_method(db, mid)
    if not mt or (key != "-" and key not in db.get("icons", {})):
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    mt["icon"] = "" if key == "-" else key
    save(db)
    await c.answer("✅ আইকন বদলানো হয়েছে")
    await method_edit_menu(c.message, mid)


@admin.callback_query(F.data.startswith("awm:ec:"))
async def method_edit_color(c: CallbackQuery):
    mid = c.data.split(":")[2]
    await tell(
        c.message,
        "🌈 বাটনের রং বেছে নিন:",
        KB([[B(v[0], f"wmc:{mid}:{k}")] for k, v in COLORS.items()] + [back_row("awm:ed:" + mid)]),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("wmc:"))
async def method_edit_color_pick(c: CallbackQuery):
    _, mid, k = c.data.split(":", 2)
    db = load()
    mt = get_method(db, mid)
    if not mt or k not in COLORS:
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    mt["style"] = COLORS[k][1]
    save(db)
    await c.answer("✅ রং বদলানো হয়েছে")
    await method_edit_menu(c.message, mid)


# ---------- পেন্ডিং সাবমিশন ----------
@admin.callback_query(F.data == "adm:pend")
async def pend_open(c: CallbackQuery):
    db = load()
    pend = [(sid, s) for sid, s in db["subs"].items() if s["type"] in ("input", "task") and s["status"] == "pending"]
    if not pend:
        await tell(c.message, "✅ কোনো পেন্ডিং সাবমিশন নেই", KB([back_row()]))
    for sid, s in pend[:15]:
        await tell(c.message, submission_text(db, s), approve_kb("ap", sid))
    if len(pend) > 15:
        await tell(c.message, f"➕ আরও {len(pend) - 15} টি আছে")
    await c.answer()


# ---------- Approve / Reject ----------
async def clear_markup(c: CallbackQuery):
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


@admin.callback_query(F.data.startswith("ap:"))
async def approve_input(c: CallbackQuery):
    _, sid, act = c.data.split(":")
    db = load()
    sub = db["subs"].get(sid)
    if not sub or sub["status"] != "pending":
        await c.answer("⚠️ এটি আগেই প্রসেস হয়েছে", show_alert=True)
        await clear_markup(c)
        return
    cur = db["settings"]["currency"]
    u = db["users"].get(sub["uid"])
    reward = float(sub.get("reward", 0))
    comm = None
    if act == "y":
        sub["status"] = "approved"
        if u and reward > 0:
            u["balance"] += reward
            add_tx(db, sub["uid"], "reward", reward, sub["btn"])
            comm = pay_commission(db, sub["uid"], reward)
        msg = f"✅ <b>আপনার সাবমিশন Approve হয়েছে!</b>\n🔘 {esc(sub['btn'])}"
        if reward > 0:
            msg += f"\n🎁 রিওয়ার্ড: <b>{money(reward)} {cur}</b>"
            if u:
                msg += f"\n💎 বর্তমান ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>"
    else:
        sub["status"] = "rejected"
        msg = f"❌ <b>আপনার সাবমিশন Reject হয়েছে</b>\n🔘 {esc(sub['btn'])}"
    save(db)
    await deliver(c.bot, int(sub["uid"]), msg)
    if comm:
        await deliver(c.bot, int(comm[0]), f"📈 রেফার কমিশন পেয়েছেন: <b>{money(comm[1])} {cur}</b>")
    await clear_markup(c)
    await c.message.answer("✅ Approve করা হয়েছে" if act == "y" else "❌ Reject করা হয়েছে")
    await c.answer()


@admin.callback_query(F.data.startswith("wd:"))
async def approve_withdraw(c: CallbackQuery):
    _, sid, act = c.data.split(":")
    db = load()
    sub = db["subs"].get(sid)
    if not sub or sub["status"] != "pending":
        await c.answer("⚠️ এটি আগেই প্রসেস হয়েছে", show_alert=True)
        await clear_markup(c)
        return
    u = db["users"].get(sub["uid"])
    if act == "y":
        sub["status"] = "approved"
        key = "wd_ok"
    else:
        sub["status"] = "rejected"
        if u:
            u["balance"] += sub["amount"]
            add_tx(db, sub["uid"], "refund", sub["amount"], "উইথড্র বাতিল")
        key = "wd_no"
    save(db)
    msg = fmt_msg(
        db, key, sub["uid"], amount=sub["amount"], method=sub.get("method") or "-", account=sub["account"]
    )
    await deliver(c.bot, int(sub["uid"]), msg)
    await clear_markup(c)
    await c.message.answer("✅ উইথড্র সফল হিসেবে মার্ক করা হয়েছে" if act == "y" else "❌ বাতিল করে টাকা ব্যালেন্সে ফেরত দেওয়া হয়েছে")
    await c.answer()


# ============================== 🛍 বিজনেস বট (অ্যাডমিন) ==============================
class ProdAdd(StatesGroup):
    name = State()
    price = State()
    desc = State()
    photo = State()
    mode = State()
    cat = State()


class StockAdd(StatesGroup):
    items = State()


class ProdEdit(StatesGroup):
    value = State()


def products(db):
    return db.setdefault("products", {})


def stock_n(p):
    return len(p.get("stock", []))


def split_items(text):
    """প্রতি লাইন = ১টি আইটেম; আর '---' লাইন থাকলে সেটি দিয়ে আইটেম আলাদা হয়"""
    text = text.replace("\r", "")
    if re.search(r"(?m)^\s*---\s*$", text):
        parts = re.split(r"(?m)^\s*---\s*$", text)
    else:
        parts = text.split("\n")
    return [x.strip() for x in parts if x.strip()]


async def send_blocks(msg, blocks, markup=None):
    chunk = ""
    for b in blocks:
        if chunk and len(chunk) + len(b) + 2 > 3500:
            await tell(msg, chunk.strip())
            chunk = ""
        chunk += b + "\n\n"
    if chunk.strip():
        await tell(msg, chunk.strip(), markup)


def biz_kb():
    return KB(
        [
            [B("➕ নতুন প্রোডাক্ট যোগ", "biz:add", style="success"), B("📦 প্রোডাক্ট ও স্টক", "biz:list")],
            [B("📂 ক্যাটাগরি", "bz:cat"), B("🧾 অর্ডার / ডেলিভারি", "biz:ord")],
            [B("💳 এড মানি রিকোয়েস্ট", "bz:am", style="success"), B("🏦 পেমেন্ট নাম্বার", "bz:pm")],
            [B("♻️ রিফান্ড রিকোয়েস্ট", "bz:rf")],
            [B("🧩 ইউজার মেনুতে সিস্টেম বাটন যোগ", "bz:sys")],
            [B("👥 ইউজার / ব্যালেন্স / ব্যান", "adm:users"), B("📢 ব্রডকাস্ট (অফার)", "tl:cast")],
            back_row(),
        ]
    )


async def biz_menu(msg):
    db = load()
    cur = db["settings"]["currency"]
    ps = list(products(db).values())
    ok = sum(1 for p in ps if avail(p))
    orders = db.get("orders", [])
    rev = sum(o["price"] for o in orders if o.get("status") != "refunded")
    pend_o = sum(1 for o in orders if o.get("status") == "pending")
    pend_a = sum(1 for r in db["addreqs"].values() if r["status"] == "pending")
    pend_r = sum(1 for r in db["refunds"].values() if r["status"] == "pending")
    await tell(
        msg,
        f"🛍 <b>বিজনেস বট</b>\n{LINE}\n"
        f"📦 প্রোডাক্ট: <b>{len(ps)}</b> (🟢 স্টকে {ok} | 🔴 শেষ {len(ps) - ok})\n"
        f"📂 ক্যাটাগরি: <b>{len(db['categories'])}</b>\n"
        f"🧾 মোট অর্ডার: <b>{len(orders)}</b> (⏳ ম্যানুয়াল পেন্ডিং {pend_o})\n"
        f"💰 মোট বিক্রি: <b>{money(rev)} {cur}</b>\n"
        f"💳 পেন্ডিং এড মানি: <b>{pend_a}</b> | ♻️ পেন্ডিং রিফান্ড: <b>{pend_r}</b>\n{LINE}\n"
        "ইউজার ব্যালেন্স দিয়ে কিনবে। অটো প্রোডাক্টে স্টক থেকে সাথে সাথে ডেলিভারি, "
        "ম্যানুয়াল প্রোডাক্টে আপনার কাছে অর্ডার আসবে।\n"
        "স্টক থাকলে বাটন 🟢 সবুজ, শেষ হলে 🔴 লাল।",
        biz_kb(),
    )


@admin.callback_query(F.data == "adm:biz")
async def biz_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await biz_menu(c.message)
    await c.answer()


# ---------- প্রোডাক্ট যোগ ----------
@admin.callback_query(F.data == "biz:add")
async def biz_add(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ProdAdd.name)
    await tell(c.message, "✍️ প্রোডাক্টের নাম লিখুন:\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(ProdAdd.name, F.text)
async def biz_add_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip()[:50])
    await state.set_state(ProdAdd.price)
    await tell(m, "💰 প্রোডাক্টের দাম লিখুন (সংখ্যা):")


@admin.message(ProdAdd.price, F.text)
async def biz_add_price(m: Message, state: FSMContext):
    v = parse_num(m.text)
    if v is None or v <= 0:
        await m.answer("❌ সঠিক দাম লিখুন (যেমন 50):")
        return
    await state.update_data(price=v)
    await state.set_state(ProdAdd.desc)
    await tell(m, "📝 প্রোডাক্টের বিবরণ লিখুন (না লাগলে - লিখুন):")


@admin.message(ProdAdd.desc, F.text)
async def biz_add_desc(m: Message, state: FSMContext):
    t = m.text.strip()
    await state.update_data(desc="" if t == "-" else t)
    await state.set_state(ProdAdd.photo)
    await tell(m, "🖼 প্রোডাক্টের ছবি পাঠান (না লাগলে - লিখুন):")


@admin.message(ProdAdd.photo, F.text | F.photo)
async def biz_add_photo(m: Message, state: FSMContext):
    photo = m.photo[-1].file_id if m.photo else None
    if not photo and (m.text or "").strip() != "-":
        await m.answer("❌ ছবি পাঠান অথবা - লিখুন:")
        return
    await state.update_data(photo=photo)
    await state.set_state(ProdAdd.mode)
    await tell(
        m,
        "🚚 <b>ডেলিভারির ধরন বেছে নিন:</b>\n\n"
        "⚡ <b>অটো</b> = আপনি স্টক (কোড/লগইন/লিংক) যোগ করবেন, কেনার সাথে সাথে ক্রেতা পাবে\n"
        "🧑‍💼 <b>ম্যানুয়াল</b> = কেউ কিনলে আপনার কাছে অর্ডার আসবে, আপনি নিজে পণ্য পাঠাবেন",
        KB(
            [
                [B("⚡ অটো ডেলিভারি", "pdm:auto", style="success")],
                [B("🧑‍💼 ম্যানুয়াল ডেলিভারি", "pdm:manual")],
            ]
        ),
    )


async def create_product(msg, state: FSMContext, cat):
    data = await state.get_data()
    db = load()
    pid = new_id()
    mode = data.get("mode", "auto")
    products(db)[pid] = {
        "id": pid,
        "name": data["name"],
        "price": float(data["price"]),
        "desc": data.get("desc", ""),
        "photo": data.get("photo"),
        "stock": [],
        "sold": 0,
        "active": True,
        "mode": mode,
        "cat": cat,
        "out": False,
    }
    save(db)
    await state.clear()
    if mode == "manual":
        await tell(
            msg,
            "✅ প্রোডাক্ট যোগ হয়েছে!\n🧑‍💼 ম্যানুয়াল ডেলিভারি — স্টক লাগবে না। কেউ কিনলে আপনার কাছে অর্ডার আসবে।",
            KB([[B("📦 প্রোডাক্ট দেখুন", f"biz:p:{pid}")], [B("🔙 বিজনেস মেনু", "adm:biz")]]),
        )
    else:
        await tell(
            msg,
            "✅ প্রোডাক্ট যোগ হয়েছে!\n🔴 এখন স্টক নেই, তাই ইউজারদের কাছে লাল বাটন দেখাবে। স্টক যোগ করলেই সবুজ হয়ে যাবে।",
            KB([[B("📦 এখনই স্টক যোগ করুন", f"biz:st:{pid}", style="success")], [B("🔙 বিজনেস মেনু", "adm:biz")]]),
        )


@admin.callback_query(ProdAdd.mode, F.data.startswith("pdm:"))
async def biz_add_mode(c: CallbackQuery, state: FSMContext):
    await state.update_data(mode="manual" if c.data[4:] == "manual" else "auto")
    db = load()
    cats = list(db["categories"].values())
    if cats:
        await state.set_state(ProdAdd.cat)
        rows = [[B(node_label(db, x)[:40], "pdc:" + x["id"], icon=node_cid(db, x))] for x in cats[:90]]
        rows.append([B("⛔ ক্যাটাগরি ছাড়া", "pdc:-")])
        await tell(c.message, "📂 কোন ক্যাটাগরিতে রাখবেন?", KB(rows))
    else:
        await create_product(c.message, state, "")
    await c.answer()


@admin.callback_query(ProdAdd.cat, F.data.startswith("pdc:"))
async def biz_add_cat(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    db = load()
    if key != "-" and key not in db["categories"]:
        await c.answer("❌ ক্যাটাগরি পাওয়া যায়নি", show_alert=True)
        return
    await create_product(c.message, state, "" if key == "-" else key)
    await c.answer()


# ---------- স্টক যোগ ----------
@admin.callback_query(F.data.startswith("biz:st:"))
async def biz_stock_start(c: CallbackQuery, state: FSMContext):
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if not p:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    await state.clear()
    await state.update_data(pid=p["id"])
    await state.set_state(StockAdd.items)
    await tell(
        c.message,
        f"📦 <b>{esc(p['name'])}</b> — বর্তমান স্টক: <b>{stock_n(p)}</b>\n\n"
        "✍️ স্টকের আইটেম পাঠান। এগুলোই ক্রেতা অটো ডেলিভারিতে পাবে (কোড / লগইন / লিংক ইত্যাদি)।\n"
        "• <b>প্রতি লাইন = ১টি আইটেম</b>\n"
        "• একটি আইটেমে একাধিক লাইন লাগলে আইটেমগুলোর মাঝে আলাদা লাইনে <code>---</code> লিখুন\n"
        "• বেশি হলে কয়েকবারে পাঠাতে পারেন\n"
        "(বাতিল: /cancel)",
    )
    await c.answer()


@admin.message(StockAdd.items, F.text)
async def biz_stock_add(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    p = products(db).get(data.get("pid", ""))
    if not p:
        await state.clear()
        await m.answer("❌ প্রোডাক্ট পাওয়া যায়নি")
        return
    items = split_items(m.text)
    if not items:
        await m.answer("❌ কোনো আইটেম পাওয়া যায়নি, আবার পাঠান:")
        return
    p.setdefault("stock", []).extend(items)
    save(db)
    await state.clear()
    await tell(
        m,
        f"✅ <b>{len(items)}</b> টি স্টক যোগ হয়েছে।\n📦 মোট স্টক: <b>{stock_n(p)}</b>\n🟢 ইউজারদের কাছে এখন সবুজ বাটন দেখাবে।",
        KB([[B("➕ আরও স্টক যোগ", f"biz:st:{p['id']}")], [B("🔙 প্রোডাক্ট", f"biz:p:{p['id']}")]]),
    )


# ---------- প্রোডাক্ট লিস্ট / ম্যানেজ ----------
@admin.callback_query(F.data == "biz:list")
async def biz_list(c: CallbackQuery, state: FSMContext):
    await state.clear()
    db = load()
    cur = db["settings"]["currency"]
    ps = list(products(db).values())
    if not ps:
        await tell(c.message, "📭 এখনো কোনো প্রোডাক্ট নেই।", KB([[B("➕ নতুন প্রোডাক্ট", "biz:add", style="success")], [B("🔙 বিজনেস মেনু", "adm:biz")]]))
        await c.answer()
        return
    rows = []
    for p in ps[:90]:
        ok = avail(p)
        mark = ("🟢" if ok else "🔴") + ("" if p.get("active", True) else "⏸") + ("🧑‍💼" if is_manual(p) else "")
        rows.append(
            [B(f"{mark} {p['name']} • {money(p['price'])}{cur} • {stock_short(p)}"[:60], f"biz:p:{p['id']}", style="success" if ok else "danger")]
        )
    rows.append([B("🔙 বিজনেস মেনু", "adm:biz")])
    await tell(c.message, "📦 <b>প্রোডাক্ট লিস্ট</b>\n🟢 স্টক আছে | 🔴 স্টক নেই | ⏸ বন্ধ করা | 🧑‍💼 ম্যানুয়াল", KB(rows))
    await c.answer()


async def show_prod(msg, db, p):
    cur = db["settings"]["currency"]
    n = stock_n(p)
    on = p.get("active", True)
    pid = p["id"]
    man = is_manual(p)
    cat = db["categories"].get(p.get("cat") or "")
    if man:
        stock_line = "🧑‍💼 ডেলিভারি: <b>ম্যানুয়াল</b> " + ("🔴 (স্টক আউট করা)" if p.get("out") else "🟢 (স্টকে আছে)")
    else:
        stock_line = f"⚡ ডেলিভারি: <b>অটো</b>\n📦 স্টক: <b>{n}</b> {'🟢' if n else '🔴 (শেষ)'}"
    text = (
        f"🛍 <b>{esc(p['name'])}</b>\n{LINE}\n"
        f"💰 দাম: <b>{money(p['price'])} {cur}</b>\n"
        f"{stock_line}\n"
        f"📂 ক্যাটাগরি: <b>{esc(cat['text']) if cat else 'নেই'}</b>\n"
        f"🛒 মোট বিক্রি: <b>{p.get('sold', 0)}</b>\n"
        f"📌 অবস্থা: <b>{'চালু ✅' if on else 'বন্ধ ⏸ (ইউজার দেখবে না)'}</b>"
    )
    if p.get("desc"):
        text += f"\n\n📝 {p['desc']}"
    rows = []
    if man:
        rows.append([B("🟢 স্টকে আনুন" if p.get("out") else "🔴 স্টক আউট করুন", f"bz:out:{pid}")])
    else:
        rows.append([B("➕ স্টক যোগ করুন", f"biz:st:{pid}", style="success")])
        rows.append([B("👁 স্টকের আইটেম দেখুন", f"biz:vs:{pid}")])
    rows += [
        [B("💲 দাম", f"biz:ed:price:{pid}"), B("✏️ নাম", f"biz:ed:name:{pid}")],
        [B("📝 বিবরণ", f"biz:ed:desc:{pid}"), B("🖼 ছবি", f"biz:ed:photo:{pid}")],
        [B("📂 ক্যাটাগরি", f"bz:pc:{pid}"), B("🔁 ডেলিভারি: " + ("→ অটো" if man else "→ ম্যানুয়াল"), f"bz:md:{pid}")],
        [B("⏸ বন্ধ করুন" if on else "▶️ চালু করুন", f"biz:tg:{pid}")],
    ]
    if not man:
        rows.append([B("🗑 স্টক খালি", f"biz:clr:{pid}", style="danger")])
    rows.append([B("❌ প্রোডাক্ট ডিলিট", f"biz:del:{pid}", style="danger")])
    rows.append([B("🔙 প্রোডাক্ট লিস্ট", "biz:list")])
    await tell(msg, text, KB(rows), p.get("photo"))


@admin.callback_query(F.data.startswith("biz:p:"))
async def biz_prod(c: CallbackQuery, state: FSMContext):
    await state.clear()
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if not p:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    await show_prod(c.message, db, p)
    await c.answer()


@admin.callback_query(F.data.startswith("biz:vs:"))
async def biz_view_stock(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if not p:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    items = p.get("stock", [])
    if not items:
        await c.answer("📭 স্টক খালি", show_alert=True)
        return
    blocks = [f"👁 <b>{esc(p['name'])}</b> — মোট {len(items)} টি (প্রথম {min(len(items), 30)} টি দেখানো হলো)"]
    for i, it in enumerate(items[:30], 1):
        blocks.append(f"{i}. <code>{esc(it[:200])}</code>")
    await send_blocks(c.message, blocks, KB([[B("🔙 প্রোডাক্ট", f"biz:p:{p['id']}")]]))
    await c.answer()


@admin.callback_query(F.data.startswith("biz:tg:"))
async def biz_toggle(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if not p:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    p["active"] = not p.get("active", True)
    save(db)
    await c.answer("▶️ চালু হয়েছে" if p["active"] else "⏸ বন্ধ হয়েছে")
    await show_prod(c.message, db, p)


@admin.callback_query(F.data.startswith("biz:clr:"))
async def biz_clear_ask(c: CallbackQuery):
    pid = c.data.split(":")[2]
    await tell(
        c.message,
        "⚠️ <b>সব স্টক মুছে ফেলবেন?</b> এটি ফেরত আনা যাবে না।",
        KB([[B("✅ হ্যাঁ, খালি করুন", f"biz:cly:{pid}", style="danger")], [B("❌ না", f"biz:p:{pid}")]]),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("biz:cly:"))
async def biz_clear_do(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if p:
        p["stock"] = []
        save(db)
        await c.answer("🗑 স্টক খালি হয়েছে")
        await show_prod(c.message, db, p)
    else:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)


@admin.callback_query(F.data.startswith("biz:del:"))
async def biz_del_ask(c: CallbackQuery):
    pid = c.data.split(":")[2]
    await tell(
        c.message,
        "⚠️ <b>প্রোডাক্টটি পুরোপুরি ডিলিট করবেন?</b> স্টকসহ মুছে যাবে।",
        KB([[B("✅ হ্যাঁ, ডিলিট করুন", f"biz:dly:{pid}", style="danger")], [B("❌ না", f"biz:p:{pid}")]]),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("biz:dly:"))
async def biz_del_do(c: CallbackQuery):
    db = load()
    products(db).pop(c.data.split(":")[2], None)
    save(db)
    await c.answer("🗑 ডিলিট হয়েছে")
    await tell(c.message, "🗑 প্রোডাক্ট ডিলিট হয়েছে", KB([[B("🔙 প্রোডাক্ট লিস্ট", "biz:list")]]))


@admin.callback_query(F.data.startswith("biz:ed:"))
async def biz_edit(c: CallbackQuery, state: FSMContext):
    _, _, field, pid = c.data.split(":")
    db = load()
    if pid not in products(db):
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    await state.clear()
    await state.update_data(pid=pid, field=field)
    await state.set_state(ProdEdit.value)
    hint = {
        "price": "💲 নতুন দাম লিখুন (সংখ্যা):",
        "name": "✏️ নতুন নাম লিখুন:",
        "desc": "📝 নতুন বিবরণ লিখুন (মুছতে - লিখুন):",
        "photo": "🖼 নতুন ছবি পাঠান (মুছতে - লিখুন):",
    }[field]
    await tell(c.message, hint + "\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(ProdEdit.value, F.text | F.photo)
async def biz_edit_val(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    p = products(db).get(data.get("pid", ""))
    field = data.get("field")
    if not p:
        await state.clear()
        await m.answer("❌ প্রোডাক্ট পাওয়া যায়নি")
        return
    t = (m.text or "").strip()
    if field == "photo":
        if m.photo:
            p["photo"] = m.photo[-1].file_id
        elif t == "-":
            p["photo"] = None
        else:
            await m.answer("❌ ছবি পাঠান অথবা - লিখুন:")
            return
    else:
        if not t:
            await m.answer("❌ লেখা পাঠান:")
            return
        if field == "price":
            v = parse_num(t)
            if v is None or v <= 0:
                await m.answer("❌ সঠিক দাম লিখুন:")
                return
            p["price"] = v
        elif field == "name":
            p["name"] = t[:50]
        else:
            p["desc"] = "" if t == "-" else t
    save(db)
    await state.clear()
    await m.answer("✅ আপডেট হয়েছে!")
    await show_prod(m, db, p)


# ---------- অর্ডার ----------
ORDER_ST = {"pending": "⏳ পেন্ডিং", "done": "✅ ডেলিভারড", "refunded": "♻️ রিফান্ড"}


def order_status(o):
    return o.get("status") or "done"


def find_order(db, oid):
    for o in db.get("orders", []):
        if o["id"] == oid:
            return o
    return None


def order_admin_text(db, o):
    u = db["users"].get(o["uid"], {"name": "?", "username": ""})
    cur = db["settings"]["currency"]
    when = datetime.fromtimestamp(o["time"], TZ).strftime("%d/%m %H:%M")
    return (
        f"🧾 <b>অর্ডার #{o['id']}</b> • {ORDER_ST[order_status(o)]}\n"
        f"🛍 {esc(o['name'])} • {money(o['price'])} {cur}\n"
        f"👤 {esc(u['name'])} (@{esc(u.get('username') or '-')})\n"
        f"🆔 <code>{o['uid']}</code> • {when}"
    )


def order_btns(o):
    return KB(
        [
            [
                B("📦 ডেলিভারি দিন", f"ord:dl:{o['id']}", style="success"),
                B("❌ ক্যানসেল + রিফান্ড", f"ord:cx:{o['id']}", style="danger"),
            ]
        ]
    )


@admin.callback_query(F.data == "biz:ord")
async def biz_orders(c: CallbackQuery):
    db = load()
    cur = db["settings"]["currency"]
    orders = db.get("orders", [])
    rev = sum(o["price"] for o in orders if order_status(o) != "refunded")
    pend = [o for o in orders if order_status(o) == "pending"]
    blocks = [
        f"🧾 <b>অর্ডার হিসাব</b>\n{LINE}\n🛒 মোট অর্ডার: <b>{len(orders)}</b>\n"
        f"⏳ ম্যানুয়াল পেন্ডিং: <b>{len(pend)}</b>\n💰 মোট বিক্রি: <b>{money(rev)} {cur}</b>"
    ]
    for o in reversed(orders[-15:]):
        u = db["users"].get(o["uid"], {"name": "?"})
        when = datetime.fromtimestamp(o["time"], TZ).strftime("%d/%m %H:%M")
        blocks.append(
            f"#{o['id']} • <b>{esc(o['name'])}</b> • {money(o['price'])} {cur} • {ORDER_ST[order_status(o)]}\n"
            f"👤 {esc(u['name'])} (<code>{o['uid']}</code>) • {when}"
        )
    if not orders:
        blocks.append("📭 এখনো কোনো অর্ডার হয়নি")
    await send_blocks(c.message, blocks, KB([[B("🔙 বিজনেস মেনু", "adm:biz")]]))
    for o in pend[-10:]:
        await tell(c.message, order_admin_text(db, o), order_btns(o))
    await c.answer()


# ---------- শপ বাটন (ইউজারের মেনুতে) ----------
@admin.callback_query(F.data == "biz:shopbtn")
async def biz_shop_button(c: CallbackQuery):
    db = load()
    if any(n.get("kind") == "shop" for n in menu_nodes(db["menu"])):
        await c.answer("✅ শপ বাটন আগে থেকেই মেনুতে আছে", show_alert=True)
        return
    db["menu"].append(
        {
            "id": new_id(),
            "text": "🛒 শপ",
            "style": "success",
            "type": "act",
            "kind": "shop",
            "reply": DEFAULT_REPLY["shop"],
            "photo": None,
            "inline": [],
            "children": [],
        }
    )
    save(db)
    await tell(c.message, "✅ ইউজারের মেইন মেনুতে <b>🛒 শপ</b> বাটন যোগ হয়েছে!\n(নাম/রং বদলাতে: বাটন কন্ট্রোল → এডিট)", main_kb(db))
    await biz_menu(c.message)
    await c.answer()


# ============================== 🧩 বিজনেস বট — ক্যাটাগরি / পেমেন্ট / এড মানি / রিফান্ড / ডেলিভারি ==============================
class CatAdd(StatesGroup):
    name = State()
    icon = State()


class PMA(StatesGroup):
    name = State()
    number = State()
    icon = State()
    edit = State()


class Deliver(StatesGroup):
    content = State()


class TkReply(StatesGroup):
    msg = State()


# ---------- প্রোডাক্ট সেটিং (স্টক আউট / ধরন / ক্যাটাগরি) ----------
@admin.callback_query(F.data.startswith("bz:out:"))
async def bz_out(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if not p:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    p["out"] = not p.get("out", False)
    save(db)
    await c.answer("🔴 স্টক আউট করা হয়েছে" if p["out"] else "🟢 স্টকে আনা হয়েছে")
    await show_prod(c.message, db, p)


@admin.callback_query(F.data.startswith("bz:md:"))
async def bz_mode(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data.split(":")[2])
    if not p:
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    p["mode"] = "auto" if is_manual(p) else "manual"
    save(db)
    await c.answer("⚡ অটো ডেলিভারি" if p["mode"] == "auto" else "🧑‍💼 ম্যানুয়াল ডেলিভারি")
    await show_prod(c.message, db, p)


@admin.callback_query(F.data.startswith("bz:pc:"))
async def bz_prod_cat(c: CallbackQuery):
    db = load()
    pid = c.data.split(":")[2]
    if pid not in products(db):
        await c.answer("❌ প্রোডাক্ট পাওয়া যায়নি", show_alert=True)
        return
    rows = [[B(node_label(db, x)[:40], f"bz:pcs:{pid}:{x['id']}", icon=node_cid(db, x))] for x in list(db["categories"].values())[:90]]
    rows.append([B("⛔ ক্যাটাগরি ছাড়া", f"bz:pcs:{pid}:-")])
    rows.append([B("➕ নতুন ক্যাটাগরি বানান", "bz:cat:add")])
    rows.append([B("🔙 প্রোডাক্ট", f"biz:p:{pid}")])
    await tell(c.message, "📂 এই প্রোডাক্ট কোন ক্যাটাগরিতে থাকবে?", KB(rows))
    await c.answer()


@admin.callback_query(F.data.startswith("bz:pcs:"))
async def bz_prod_cat_set(c: CallbackQuery):
    _, _, pid, cid = c.data.split(":")
    db = load()
    p = products(db).get(pid)
    if not p or (cid != "-" and cid not in db["categories"]):
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    p["cat"] = "" if cid == "-" else cid
    save(db)
    await c.answer("✅ ক্যাটাগরি সেট হয়েছে")
    await show_prod(c.message, db, p)


# ---------- ক্যাটাগরি ----------
async def cat_menu(msg):
    db = load()
    lines = [f"📂 <b>প্রোডাক্ট ক্যাটাগরি</b>\n{LINE}"]
    rows = []
    for ct in db["categories"].values():
        cnt = sum(1 for p in products(db).values() if p.get("cat") == ct["id"])
        lines.append(f"• {pm_text(db, ct)} — {cnt} টি প্রোডাক্ট")
        rows.append(
            [
                B(("📌 " + ct["text"])[:40], "bz:cat:mk:" + ct["id"], style="primary"),
                B("🗑 ডিলিট", "bz:cat:del:" + ct["id"], style="danger"),
            ]
        )
    if not db["categories"]:
        lines.append("কোনো ক্যাটাগরি নেই (ক্যাটাগরি ছাড়া সব প্রোডাক্ট সরাসরি শপে দেখাবে)")
    lines.append("\n📌 ক্যাটাগরির নামে চাপলে ইউজারের মেইন মেনুতে ওই ক্যাটাগরির <b>প্রডাক্ট লিস্ট</b> দেখানোর বাটন যোগ হবে।")
    lines.append("ℹ️ প্রোডাক্টের পেজ থেকে '📂 ক্যাটাগরি' চেপে প্রোডাক্ট ক্যাটাগরিতে রাখুন।")
    rows.append([B("➕ নতুন ক্যাটাগরি", "bz:cat:add", style="success")])
    rows.append([B("🔙 বিজনেস মেনু", "adm:biz")])
    await tell(msg, "\n".join(lines), KB(rows))


@admin.callback_query(F.data == "bz:cat")
async def bz_cat(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await cat_menu(c.message)
    await c.answer()


@admin.callback_query(F.data == "bz:cat:add")
async def bz_cat_add(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(CatAdd.name)
    await tell(c.message, "✍️ ক্যাটাগরির নাম লিখুন (যেমন: Facebook Service, YouTube Service, Premium Account):\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(CatAdd.name, F.text)
async def bz_cat_name(m: Message, state: FSMContext):
    name = m.text.strip()[:30]
    await state.update_data(name=name)
    await state.set_state(CatAdd.icon)
    await tell(m, f"🌟 <b>{esc(name)}</b> এর জন্য স্টিকার / আইকন বেছে নিন:", icon_picker_kb(load(), "cti:", name))


@admin.callback_query(CatAdd.icon, F.data.startswith("cti:"))
async def bz_cat_icon(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    db = load()
    if key != "-" and key not in db["icons"]:
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    name = (await state.get_data()).get("name", "ক্যাটাগরি")
    cid = new_id()
    db["categories"][cid] = {"id": cid, "text": name, "icon": "" if key == "-" else key}
    save(db)
    await state.clear()
    await c.answer("✅ ক্যাটাগরি যোগ হয়েছে")
    await cat_menu(c.message)


@admin.callback_query(F.data.startswith("bz:cat:mk:"))
async def bz_cat_mk(c: CallbackQuery):
    db = load()
    ct = db["categories"].get(c.data.split(":")[3])
    if not ct:
        await c.answer("❌ ক্যাটাগরি পাওয়া যায়নি", show_alert=True)
        return
    if any(n.get("kind") == "shopcat" and n.get("cat") == ct["id"] for n in menu_nodes(db["menu"])):
        await c.answer("✅ এই ক্যাটাগরির বাটন আগে থেকেই মেনুতে আছে", show_alert=True)
        return
    db["menu"].append(
        {
            "id": new_id(),
            "text": ct["text"],
            "style": "primary",
            "icon": ct.get("icon", ""),
            "type": "act",
            "kind": "shopcat",
            "cat": ct["id"],
            "reply": "",
            "photo": None,
            "inline": [],
            "children": [],
        }
    )
    save(db)
    await c.answer("✅ মেইন মেনুতে বাটন যোগ হয়েছে", show_alert=True)
    await cat_menu(c.message)


@admin.callback_query(F.data.startswith("bz:cat:del:"))
async def bz_cat_del(c: CallbackQuery):
    db = load()
    cid = c.data.split(":")[3]
    db["categories"].pop(cid, None)
    for p in products(db).values():
        if p.get("cat") == cid:
            p["cat"] = ""
    save(db)
    await c.answer("🗑 ক্যাটাগরি মুছেছে (প্রোডাক্ট ক্যাটাগরি ছাড়া হয়েছে)")
    await cat_menu(c.message)


# ---------- পেমেন্ট নাম্বার (বিকাশ / নগদ / রকেট ...) ----------
async def pm_menu(msg):
    db = load()
    lines = [f"🏦 <b>পেমেন্ট নাম্বার (এড মানির জন্য)</b>\n{LINE}"]
    rows = []
    for mt in db["pay_methods"]:
        num = f"<code>{esc(mt['number'])}</code>" if mt.get("number") else "❌ সেট করা নেই (ইউজার দেখবে না)"
        lines.append(f"\n💳 <b>{pm_text(db, mt)}</b>\n   📮 {num}\n   📝 {esc(mt.get('note') or '-')}")
        rows.append([B(("✏️ " + mt["text"])[:30], "bz:pme:" + mt["id"], style=mt.get("style"), icon=node_cid(db, mt))])
    rows.append([B("➕ নতুন মাধ্যম যোগ", "bz:pm:add", style="success")])
    rows.append([B("🔙 বিজনেস মেনু", "adm:biz")])
    await tell(msg, "\n".join(lines), KB(rows))


async def pm_detail(msg, mid):
    db = load()
    mt = next((x for x in db["pay_methods"] if x["id"] == mid), None)
    if not mt:
        await pm_menu(msg)
        return
    await tell(
        msg,
        f"✏️ <b>{pm_text(db, mt)}</b>\n{LINE}\n"
        f"📮 নাম্বার: {('<code>' + esc(mt['number']) + '</code>') if mt.get('number') else '❌ সেট নেই'}\n"
        f"📝 নির্দেশ: {esc(mt.get('note') or '-')}",
        KB(
            [
                [B("📮 নাম্বার চেঞ্জ করুন", f"bz:pmf:num:{mid}", style="success")],
                [B("📝 নির্দেশ বদলান", f"bz:pmf:note:{mid}")],
                [B("🌟 স্টিকার / আইকন বদলান", f"bz:pmf:icon:{mid}")],
                [B("🗑 মাধ্যম ডিলিট", f"bz:pmd:{mid}", style="danger")],
                [B("🔙 পেমেন্ট নাম্বার", "bz:pm")],
            ]
        ),
    )


@admin.callback_query(F.data == "bz:pm")
async def bz_pm(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await pm_menu(c.message)
    await c.answer()


@admin.callback_query(F.data.startswith("bz:pme:"))
async def bz_pme(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await pm_detail(c.message, c.data.split(":")[2])
    await c.answer()


@admin.callback_query(F.data == "bz:pm:add")
async def bz_pm_add(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PMA.name)
    await tell(c.message, "🏦 মাধ্যমের নাম লিখুন (যেমন bKash, Nagad, Rocket, Binance):\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(PMA.name, F.text)
async def bz_pm_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip()[:30])
    await state.set_state(PMA.number)
    await tell(m, "📮 এই মাধ্যমের নাম্বার / অ্যাকাউন্ট / Pay ID লিখুন:")


@admin.message(PMA.number, F.text)
async def bz_pm_number(m: Message, state: FSMContext):
    await state.update_data(number=m.text.strip()[:60])
    await state.set_state(PMA.icon)
    name = (await state.get_data()).get("name", "")
    await tell(m, f"🌟 <b>{esc(name)}</b> এর জন্য স্টিকার / আইকন বেছে নিন:", icon_picker_kb(load(), "pmi:", name))


@admin.callback_query(PMA.icon, F.data.startswith("pmi:"))
async def bz_pm_icon(c: CallbackQuery, state: FSMContext):
    key = c.data[4:]
    db = load()
    if key != "-" and key not in db["icons"]:
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    d = await state.get_data()
    db["pay_methods"].append(
        {"id": new_id(), "text": d["name"], "number": d["number"], "note": "Send Money করুন", "icon": "" if key == "-" else key, "style": None}
    )
    save(db)
    await state.clear()
    await c.answer("✅ মাধ্যম যোগ হয়েছে")
    await pm_menu(c.message)


@admin.callback_query(F.data.startswith("bz:pmf:"))
async def bz_pm_field(c: CallbackQuery, state: FSMContext):
    _, _, field, mid = c.data.split(":")
    db = load()
    mt = next((x for x in db["pay_methods"] if x["id"] == mid), None)
    if not mt:
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    await state.clear()
    if field == "icon":
        await tell(c.message, f"🌟 <b>{esc(mt['text'])}</b> এর জন্য স্টিকার / আইকন বেছে নিন:", icon_picker_kb(db, f"pmj:{mid}:", mt["text"], back=f"bz:pme:{mid}"))
    else:
        await state.update_data(mid=mid, field=field)
        await state.set_state(PMA.edit)
        await tell(c.message, "📮 নতুন নাম্বার লিখুন:" if field == "num" else "📝 ইউজার যে নির্দেশ দেখবে তা লিখুন (যেমন: Send Money করুন):")
    await c.answer()


@admin.callback_query(F.data.startswith("pmj:"))
async def bz_pm_icon_set(c: CallbackQuery):
    _, mid, key = c.data.split(":", 2)
    db = load()
    mt = next((x for x in db["pay_methods"] if x["id"] == mid), None)
    if not mt or (key != "-" and key not in db["icons"]):
        await c.answer("❌ পাওয়া যায়নি", show_alert=True)
        return
    mt["icon"] = "" if key == "-" else key
    save(db)
    await c.answer("✅ আইকন বদলানো হয়েছে")
    await pm_detail(c.message, mid)


@admin.message(PMA.edit, F.text)
async def bz_pm_edit(m: Message, state: FSMContext):
    d = await state.get_data()
    db = load()
    mt = next((x for x in db["pay_methods"] if x["id"] == d.get("mid")), None)
    await state.clear()
    if not mt:
        await m.answer("❌ মাধ্যম পাওয়া যায়নি")
        return
    if d.get("field") == "num":
        mt["number"] = m.text.strip()[:60]
    else:
        mt["note"] = m.text.strip()[:100]
    save(db)
    await m.answer("✅ আপডেট হয়েছে!")
    await pm_detail(m, mt["id"])


@admin.callback_query(F.data.startswith("bz:pmd:"))
async def bz_pm_del(c: CallbackQuery):
    db = load()
    mid = c.data.split(":")[2]
    db["pay_methods"] = [x for x in db["pay_methods"] if x["id"] != mid]
    save(db)
    await c.answer("🗑 ডিলিট হয়েছে")
    await pm_menu(c.message)


# ---------- এড মানি রিকোয়েস্ট ----------
def addreq_text(db, r):
    u = db["users"].get(r["uid"], {"name": "?", "username": ""})
    cur = db["settings"]["currency"]
    return (
        "💳 <b>নতুন এড মানি রিকোয়েস্ট</b>\n"
        f"👤 {esc(u['name'])} (@{esc(u.get('username') or '-')})\n"
        f"🆔 <code>{r['uid']}</code>\n"
        f"🏦 মাধ্যম: <b>{esc(r['method'])}</b>\n"
        f"💸 পরিমাণ: <b>{money(r['amount'])} {cur}</b>\n"
        f"🧾 TrxID: <code>{esc(r['trx'])}</code>"
    )


@admin.callback_query(F.data == "bz:am")
async def bz_am(c: CallbackQuery):
    db = load()
    cur = db["settings"]["currency"]
    reqs = list(db["addreqs"].values())
    pend = [r for r in reqs if r["status"] == "pending"]
    ok = sum(r["amount"] for r in reqs if r["status"] == "approved")
    await tell(
        c.message,
        f"💳 <b>এড মানি রিকোয়েস্ট</b>\n{LINE}\n⏳ পেন্ডিং: <b>{len(pend)}</b>\n✅ মোট এপ্রুভ হয়েছে: <b>{money(ok)} {cur}</b>",
        KB([[B("🏦 পেমেন্ট নাম্বার বদলান", "bz:pm")], [B("🔙 বিজনেস মেনু", "adm:biz")]]),
    )
    for r in pend[-15:]:
        await tell(c.message, addreq_text(db, r), approve_kb("amr", r["id"]))
    await c.answer()


@admin.callback_query(F.data.startswith("amr:"))
async def bz_am_decide(c: CallbackQuery):
    _, rid, act = c.data.split(":")
    db = load()
    r = db["addreqs"].get(rid)
    if not r or r["status"] != "pending":
        await c.answer("⚠️ এটি আগেই প্রসেস হয়েছে", show_alert=True)
        await clear_markup(c)
        return
    cur = db["settings"]["currency"]
    u = db["users"].get(r["uid"])
    comm = None
    if act == "y":
        r["status"] = "approved"
        if u:
            u["balance"] = round(u["balance"] + r["amount"], 2)
        add_tx(db, r["uid"], "add", r["amount"], "এড মানি • " + r["method"])
        comm = pay_commission(db, r["uid"], r["amount"])
        msg = (
            f"✅ <b>আপনার এড মানি রিকোয়েস্ট এপ্রুভ হয়েছে!</b>\n{LINE}\n"
            f"💸 যোগ হয়েছে: <b>{money(r['amount'])} {cur}</b>\n"
            f"👛 বর্তমান ব্যালেন্স: <b>{money(u['balance']) if u else '-'} {cur}</b>"
        )
    else:
        r["status"] = "rejected"
        msg = (
            f"❌ <b>আপনার এড মানি রিকোয়েস্ট রিজেক্ট হয়েছে</b>\n{LINE}\n"
            f"💸 পরিমাণ: {money(r['amount'])} {cur}\n🧾 TrxID: <code>{esc(r['trx'])}</code>\n"
            f"☎️ সমস্যা থাকলে যোগাযোগ করুন: {esc(db['settings'].get('support', ''))}"
        )
    save(db)
    await deliver(c.bot, int(r["uid"]), msg)
    if comm:
        await deliver(c.bot, int(comm[0]), f"📈 রেফার কমিশন পেয়েছেন: <b>{money(comm[1])} {cur}</b>")
    await clear_markup(c)
    await c.message.answer("✅ এপ্রুভ করা হয়েছে, ব্যালেন্স যোগ হয়েছে" if act == "y" else "❌ রিজেক্ট করা হয়েছে")
    await c.answer()


# ---------- ম্যানুয়াল ডেলিভারি ----------
@admin.callback_query(F.data.startswith("ord:dl:"))
async def ord_dl_start(c: CallbackQuery, state: FSMContext):
    db = load()
    o = find_order(db, c.data.split(":")[2])
    if not o or order_status(o) != "pending":
        await c.answer("⚠️ এটি আগেই প্রসেস হয়েছে", show_alert=True)
        await clear_markup(c)
        return
    await state.clear()
    await state.update_data(oid=o["id"])
    await state.set_state(Deliver.content)
    await tell(
        c.message,
        f"📦 <b>{esc(o['name'])}</b> (#{o['id']})\nক্রেতার কাছে যা পাঠাতে চান তা পাঠান (লেখা / ছবি / ফাইল):\n(বাতিল: /cancel)",
    )
    await c.answer()


@admin.message(Deliver.content)
async def ord_dl_got(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load()
    o = find_order(db, data.get("oid", ""))
    if not o or order_status(o) != "pending":
        await state.clear()
        await m.answer("⚠️ এই অর্ডার আগেই প্রসেস হয়েছে")
        return
    uid = int(o["uid"])
    head = (
        f"✅ <b>আপনার অর্ডার এপ্রুভ হয়েছে!</b>\n{LINE}\n"
        f"🛍 {esc(o['name'])}\n🆔 অর্ডার: <code>{o['id']}</code>\n📦 আপনার পণ্য নিচে 👇"
    )
    if not await deliver(m.bot, uid, head):
        await m.answer("❌ ইউজারকে মেসেজ পাঠানো যায়নি (বট ব্লক করেছে?)। আবার চেষ্টা করুন অথবা /cancel")
        return
    try:
        await m.copy_to(uid)
    except Exception:
        await m.answer("⚠️ পণ্যটি পাঠানো যায়নি। আবার পাঠান অথবা /cancel")
        return
    o["status"] = "done"
    o["item"] = (m.text or m.caption or "[ফাইল/ছবি]")[:1000]
    save(db)
    await state.clear()
    await m.answer("✅ ডেলিভারি সম্পন্ন হয়েছে!")
    await biz_menu(m)


@admin.callback_query(F.data.startswith("ord:cx:"))
async def ord_cancel(c: CallbackQuery):
    db = load()
    o = find_order(db, c.data.split(":")[2])
    if not o or order_status(o) != "pending":
        await c.answer("⚠️ এটি আগেই প্রসেস হয়েছে", show_alert=True)
        await clear_markup(c)
        return
    cur = db["settings"]["currency"]
    o["status"] = "refunded"
    u = db["users"].get(o["uid"])
    if u:
        u["balance"] = round(u["balance"] + o["price"], 2)
    add_tx(db, o["uid"], "refund", o["price"], "অর্ডার ক্যানসেল • " + o["name"])
    save(db)
    await deliver(
        c.bot,
        int(o["uid"]),
        f"❌ <b>আপনার অর্ডার ক্যানসেল হয়েছে</b>\n{LINE}\n🛍 {esc(o['name'])} (#{o['id']})\n"
        f"↩️ <b>{money(o['price'])} {cur}</b> আপনার ব্যালেন্সে ফেরত দেওয়া হয়েছে\n"
        f"☎️ যোগাযোগ: {esc(db['settings'].get('support', ''))}",
    )
    await clear_markup(c)
    await c.message.answer("❌ অর্ডার ক্যানসেল করে টাকা ফেরত দেওয়া হয়েছে")
    await c.answer()


# ---------- রিফান্ড রিকোয়েস্ট ----------
def refund_text(db, r):
    u = db["users"].get(r["uid"], {"name": "?", "username": ""})
    cur = db["settings"]["currency"]
    o = find_order(db, r["oid"])
    return (
        "♻️ <b>নতুন রিফান্ড রিকোয়েস্ট</b>\n"
        f"👤 {esc(u['name'])} (@{esc(u.get('username') or '-')})\n"
        f"🆔 <code>{r['uid']}</code>\n"
        f"🧾 অর্ডার: <code>{r['oid']}</code> • {esc(o['name']) if o else '?'} • {money(o['price']) if o else '?'} {cur}\n"
        f"📝 কারণ: {esc(r['reason'])}"
    )


@admin.callback_query(F.data == "bz:rf")
async def bz_rf(c: CallbackQuery):
    db = load()
    pend = [r for r in db["refunds"].values() if r["status"] == "pending"]
    done = sum(1 for r in db["refunds"].values() if r["status"] == "approved")
    await tell(
        c.message,
        f"♻️ <b>রিফান্ড রিকোয়েস্ট</b>\n{LINE}\n⏳ পেন্ডিং: <b>{len(pend)}</b> | ✅ এপ্রুভ: <b>{done}</b>",
        KB([[B("🔙 বিজনেস মেনু", "adm:biz")]]),
    )
    for r in pend[-15:]:
        await tell(c.message, refund_text(db, r), approve_kb("rfa", r["id"]))
    await c.answer()


@admin.callback_query(F.data.startswith("rfa:"))
async def bz_rf_decide(c: CallbackQuery):
    _, rid, act = c.data.split(":")
    db = load()
    r = db["refunds"].get(rid)
    if not r or r["status"] != "pending":
        await c.answer("⚠️ এটি আগেই প্রসেস হয়েছে", show_alert=True)
        await clear_markup(c)
        return
    cur = db["settings"]["currency"]
    o = find_order(db, r["oid"])
    if act == "y":
        if not o or order_status(o) == "refunded":
            r["status"] = "rejected"
            save(db)
            await c.answer("⚠️ অর্ডারটি আগেই রিফান্ড হয়েছে", show_alert=True)
            await clear_markup(c)
            return
        r["status"] = "approved"
        o["status"] = "refunded"
        u = db["users"].get(r["uid"])
        if u:
            u["balance"] = round(u["balance"] + o["price"], 2)
        add_tx(db, r["uid"], "refund", o["price"], "রিফান্ড • " + o["name"])
        msg = (
            f"✅ <b>আপনার রিফান্ড এপ্রুভ হয়েছে!</b>\n{LINE}\n"
            f"🧾 অর্ডার: <code>{o['id']}</code> • {esc(o['name'])}\n"
            f"↩️ ফেরত: <b>{money(o['price'])} {cur}</b>\n"
            f"👛 বর্তমান ব্যালেন্স: <b>{money(u['balance']) if u else '-'} {cur}</b>"
        )
    else:
        r["status"] = "rejected"
        msg = (
            f"❌ <b>আপনার রিফান্ড রিকোয়েস্ট রিজেক্ট হয়েছে</b>\n{LINE}\n"
            f"🧾 অর্ডার: <code>{r['oid']}</code>\n☎️ সমস্যা থাকলে যোগাযোগ করুন: {esc(db['settings'].get('support', ''))}"
        )
    save(db)
    await deliver(c.bot, int(r["uid"]), msg)
    await clear_markup(c)
    await c.message.answer("✅ রিফান্ড এপ্রুভ করা হয়েছে" if act == "y" else "❌ রিজেক্ট করা হয়েছে")
    await c.answer()


# ---------- সাপোর্ট রিপ্লাই ----------
@admin.callback_query(F.data.startswith("tkr:"))
async def tk_reply_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(uid=c.data[4:])
    await state.set_state(TkReply.msg)
    await tell(c.message, f"↩️ <code>{esc(c.data[4:])}</code> কে যে উত্তর পাঠাতে চান তা পাঠান (লেখা / ছবি / ফাইল):\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(TkReply.msg)
async def tk_reply_got(m: Message, state: FSMContext):
    uid = (await state.get_data()).get("uid", "")
    await state.clear()
    try:
        await deliver(m.bot, int(uid), "☎️ <b>সাপোর্ট থেকে উত্তর এসেছে:</b>")
        await m.copy_to(int(uid))
        await m.answer("✅ উত্তর পাঠানো হয়েছে")
    except Exception:
        await m.answer("❌ ইউজারকে পাঠানো যায়নি")


# ---------- ইউজারের মেনুতে সিস্টেম বাটন যোগ ----------
SYS_BTNS = [
    ("shop", "শপ", "success", "shop"),
    ("addmoney", "এড মানি", "success", "addmoney"),
    ("cart", "কার্ট", None, "cart"),
    ("orders", "আমার অর্ডার", None, "orders"),
    ("wallet", "ওয়ালেট", "primary", "wallet"),
    ("profile", "প্রোফাইল", None, "profile"),
    ("refer", "রেফার", None, "refer"),
    ("refund", "রিফান্ড", None, "refund"),
    ("ticket", "সাপোর্টে মেসেজ", None, "support"),
]


def sys_kb(db):
    have = {n.get("kind") for n in menu_nodes(db["menu"])}
    rows = []
    for kind, name, style, _ in SYS_BTNS:
        on = kind in have
        rows.append([B(f"{'✅' if on else '➕'} {name}", "bz:sysadd:" + kind, style=None if on else style)])
    rows.append([B("🔙 বিজনেস মেনু", "adm:biz")])
    return KB(rows)


@admin.callback_query(F.data == "bz:sys")
async def bz_sys(c: CallbackQuery):
    await tell(
        c.message,
        "🧩 <b>ইউজারের মেইন মেনুতে সিস্টেম বাটন</b>\n"
        "➕ চাপলেই ওই বাটন মেইন মেনুতে যোগ হবে (✅ = আগে থেকেই আছে)।\n\n"
        "ℹ️ নাম / রং / স্টিকার বদলাতে: <b>বাটন কন্ট্রোল → এডিট</b>।\n"
        "ℹ️ নিজের মতো করে বানাতে: <b>বাটন কন্ট্রোল → বাটন যোগ</b> করে 'বাটনটি চাপলে কী হবে' তে এই সিস্টেমগুলো পাবেন।",
        sys_kb(load()),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("bz:sysadd:"))
async def bz_sys_add(c: CallbackQuery):
    kind = c.data.split(":")[2]
    row = next((x for x in SYS_BTNS if x[0] == kind), None)
    db = load()
    if not row:
        await c.answer()
        return
    if any(n.get("kind") == kind for n in menu_nodes(db["menu"])):
        await c.answer("✅ এই বাটন আগে থেকেই মেনুতে আছে", show_alert=True)
        return
    _, name, style, ik = row
    db["menu"].append(
        {
            "id": new_id(),
            "text": name,
            "style": style,
            "icon": ik if ik in db["icons"] else "",
            "type": "act",
            "kind": kind,
            "reply": "" if kind in TPL_KINDS else DEFAULT_REPLY.get(kind, ""),
            "photo": None,
            "inline": [],
            "children": [],
        }
    )
    save(db)
    await c.answer("✅ মেনুতে যোগ হয়েছে")
    await tell(c.message, f"✅ ইউজারের মেইন মেনুতে <b>{esc(name)}</b> বাটন যোগ হয়েছে!", main_kb(db))
    await tell(c.message, "🧩 সিস্টেম বাটন:", sys_kb(db))


# ============================== 🎨 স্টিকার / আইকন লাইব্রেরি (অ্যাডমিন) ==============================
class IC(StatesGroup):
    sticker = State()
    name = State()
    newsticker = State()
    bulk = State()
    rename = State()


def ic_kb(db, page=0):
    rows, row = [], []
    keys = icon_keys_sorted(db)
    pages = max(1, (len(keys) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, pages - 1))
    for k in keys[page * PER_PAGE:(page + 1) * PER_PAGE]:
        ic = db["icons"][k]
        label = (ic["name"] + " ✅") if ic.get("cid") else f"{ic['emoji']} {ic['name']}"
        row.append(B(label[:30], "ic:v:" + k, icon=ic.get("cid") or None))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(B("◀️ আগের পাতা", f"ic:pg:{page - 1}"))
        nav.append(B(f"📄 {page + 1}/{pages}", "icpg:noop"))
        if page < pages - 1:
            nav.append(B("পরের পাতা ▶️", f"ic:pg:{page + 1}"))
        rows.append(nav)
    rows.append([B("📦 একসাথে অনেক স্টিকার সেট", "ic:bulk", style="primary")])
    rows.append([B("➕ নতুন আইকন যোগ", "ic:new", style="success")])
    rows.append(back_row())
    return KB(rows)


async def ic_menu(msg, page=0):
    db = load()
    have = sum(1 for i in db["icons"].values() if i.get("cid"))
    await tell(
        msg,
        f"🎨 <b>স্টিকার / আইকন লাইব্রেরি</b>\n{LINE}\n"
        "মেনু বাটন, ইনলাইন বাটন, উইথড্র/পেমেন্ট মাধ্যম ও ক্যাটাগরির নামের আগে যে ছোট স্টিকার বসবে, তার তালিকা। "
        "এখানে নতুন আইকন যোগ করলে সব জায়গার বাছাইয়ের তালিকায় দেখাবে। ✅ = স্টিকার সেট করা আছে।\n\n"
        "<b>স্টিকার সেট করার নিয়ম:</b>\n"
        "১) তালিকা থেকে একটি আইকন চাপুন\n"
        "২) <b>🎯 স্টিকার সেট করুন</b> চেপে ওই প্রিমিয়াম ইমোজিটি পাঠান "
        "(অথবা যে মেসেজে ইমোজিটি আছে সেটি ফরওয়ার্ড করুন)\n\n"
        "⚠️ টেলিগ্রামের নিয়ম: বাটনে ও মেসেজে স্টিকার দেখাতে বটের মালিকের Telegram Premium লাগে। "
        "স্টিকার সেট না থাকলে বা না দেখালে সাধারণ ইমোজি দেখাবে।\n"
        f"{LINE}\n🖼 মোট আইকন: <b>{len(db['icons'])}</b> | ✅ স্টিকার সেট: <b>{have}</b>",
        ic_kb(db, page),
    )


@admin.callback_query(F.data == "adm:ic")
async def ic_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if not emoji_lib_on(load()):
        await tell(c.message, "🔒 <b>ইমোজি লাইব্রেরি এখন বন্ধ আছে।</b>\nচালু করতে: প্যানেল → 🔛 ইমোজি অন / অফ", KB([[B("🔛 ইমোজি অন / অফ", "adm:emsw")]]))
        await c.answer()
        return
    await ic_menu(c.message)
    await c.answer()


@admin.callback_query(F.data.startswith("ic:pg:"))
async def ic_page(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await ic_menu(c.message, int(c.data.split(":")[2]))
    await c.answer()


@admin.callback_query(F.data == "icpg:noop")
async def icpg_noop(c: CallbackQuery):
    await c.answer()


@admin.callback_query(F.data.startswith("icpg:"))
async def icpg_picker(c: CallbackQuery):
    """আইকন বাছাইয়ের তালিকার পাতা বদল (লেখা একই থাকে, শুধু বাটন বদলায়)"""
    _, pg, prefix = c.data.split(":", 2)
    kb = adm_decorate(icon_picker_kb(load(), prefix, "", None, int(pg)))
    try:
        await c.message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest:
        pass
    await c.answer()


def _bulk_targets(db):
    return [k for k, ic in db["icons"].items() if not ic.get("cid")][:40]


@admin.callback_query(F.data == "ic:bulk")
async def ic_bulk_start(c: CallbackQuery, state: FSMContext):
    db = load()
    keys = _bulk_targets(db)
    if not keys:
        await c.answer("✅ সব আইকনেই স্টিকার সেট করা আছে", show_alert=True)
        return
    await state.clear()
    await state.update_data(keys=keys)
    await state.set_state(IC.bulk)
    lines = [f"{i}. {db['icons'][k]['emoji']} {esc(db['icons'][k]['name'])}" for i, k in enumerate(keys, 1)]
    await tell(
        c.message,
        "📦 <b>একসাথে অনেক স্টিকার সেট</b>\n" + LINE + "\n"
        "নিচের তালিকার ক্রম অনুযায়ী প্রিমিয়াম ইমোজিগুলো <b>একটি মেসেজে</b> পাঠান "
        "(অথবা ওই ইমোজিসহ মেসেজ ফরওয়ার্ড করুন)। ১ম ইমোজি ১ নম্বরে, ২য় ইমোজি ২ নম্বরে বসবে।\n"
        "ক্রম মিলিয়ে পাঠান; কম পাঠালে শুধু ততগুলোই সেট হবে।\n\n"
        + "\n".join(lines)
        + "\n\n(বাতিল: /cancel)",
        KB([back_row("adm:ic")]),
    )
    await c.answer()


@admin.message(IC.bulk)
async def ic_bulk_got(m: Message, state: FSMContext):
    got = custom_emojis(m)
    if not got:
        await m.answer("❌ এই মেসেজে কোনো প্রিমিয়াম (কাস্টম) ইমোজি পাওয়া যায়নি। আবার পাঠান। (বাতিল: /cancel)")
        return
    keys = (await state.get_data()).get("keys", [])
    db = load()
    n = 0
    for k, (cid, _em) in zip(keys, got):
        if k in db["icons"]:
            db["icons"][k]["cid"] = cid
            n += 1
    save(db)
    await state.clear()
    await m.answer(f"✅ {n} টি আইকনে স্টিকার সেট হয়েছে!")
    await ic_menu(m)


async def ic_detail(msg, key):
    db = load()
    ic = db["icons"].get(key)
    if not ic:
        await tell(msg, "❌ আইকন পাওয়া যায়নি", KB([back_row("adm:ic")]))
        return
    has = bool(ic.get("cid"))
    rows = [[B("🔄 স্টিকার বদলান" if has else "🎯 স্টিকার সেট করুন", "ic:set:" + key, style="success")]]
    if has:
        rows.append([B("🧹 স্টিকার সরান", "ic:clr:" + key)])
    rows.append([B("✏️ নাম বদলান", "ic:ren:" + key)])
    if key.startswith(("c_", "e_")):
        rows.append([B("🗑 আইকন মুছুন", "ic:del:" + key, style="danger")])
    rows.append(back_row("adm:ic"))
    await tell(
        msg,
        f"{icon_html(db, key)} <b>{esc(ic['name'])}</b>\n{LINE}\n"
        f"সাধারণ ইমোজি: {esc(ic['emoji'])}\n"
        f"স্টিকার: {'✅ সেট করা আছে' if has else '❌ সেট করা নেই'}",
        KB(rows),
    )


@admin.callback_query(F.data.startswith("ic:v:"))
async def ic_view(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await ic_detail(c.message, c.data[5:])
    await c.answer()


@admin.callback_query(F.data.startswith("ic:set:"))
async def ic_set_start(c: CallbackQuery, state: FSMContext):
    key = c.data[7:]
    if key not in load()["icons"]:
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    await state.clear()
    await state.update_data(key=key)
    await state.set_state(IC.sticker)
    await tell(
        c.message,
        "🎯 এখন যে প্রিমিয়াম (অ্যানিমেটেড/কাস্টম) ইমোজিটি লাগাতে চান সেটি পাঠান।\n"
        "💡 আপনার Premium না থাকলে, যে মেসেজে ওই ইমোজি আছে সেই মেসেজটি এখানে ফরওয়ার্ড করুন।\n"
        "(বাতিল: /cancel)",
    )
    await c.answer()


@admin.message(IC.sticker)
async def ic_set_got(m: Message, state: FSMContext):
    got = custom_emojis(m)
    if not got:
        await m.answer(
            "❌ এই মেসেজে কোনো প্রিমিয়াম (কাস্টম) ইমোজি পাওয়া যায়নি। "
            "প্রিমিয়াম ইমোজি পাঠান অথবা ইমোজিসহ মেসেজ ফরওয়ার্ড করুন। (বাতিল: /cancel)"
        )
        return
    key = (await state.get_data()).get("key")
    db = load()
    ic = db["icons"].get(key)
    await state.clear()
    if not ic:
        return
    ic["cid"] = got[0][0]
    save(db)
    note = f"\nℹ️ মেসেজে {len(got)} টি ইমোজি ছিল, প্রথমটি নেওয়া হয়েছে।" if len(got) > 1 else ""
    await m.answer(f"✅ স্টিকার সেট হয়েছে! এভাবে দেখাবে: {icon_html(db, key)}{note}")
    await ic_detail(m, key)


@admin.callback_query(F.data.startswith("ic:ren:"))
async def ic_rename_start(c: CallbackQuery, state: FSMContext):
    key = c.data[7:]
    if key not in load()["icons"]:
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    await state.clear()
    await state.update_data(key=key)
    await state.set_state(IC.rename)
    await tell(c.message, "✏️ আইকনের নতুন নাম লিখুন:\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(IC.rename, F.text)
async def ic_rename_got(m: Message, state: FSMContext):
    key = (await state.get_data()).get("key")
    db = load()
    await state.clear()
    if key in db["icons"]:
        db["icons"][key]["name"] = m.text.strip()[:25]
        save(db)
        await ic_detail(m, key)


@admin.callback_query(F.data.startswith("ic:clr:"))
async def ic_clear(c: CallbackQuery):
    key = c.data[7:]
    db = load()
    if key in db["icons"]:
        db["icons"][key]["cid"] = ""
        save(db)
    await c.answer("🧹 স্টিকার সরানো হয়েছে")
    await ic_detail(c.message, key)


@admin.callback_query(F.data.startswith("ic:del:"))
async def ic_delete(c: CallbackQuery):
    key = c.data[7:]
    db = load()
    if key.startswith(("c_", "e_")):
        db["icons"].pop(key, None)
        for mt in list(db.get("wd_methods", [])) + list(db.get("pay_methods", [])) + list(db.get("categories", {}).values()):
            if mt.get("icon") == key:
                mt["icon"] = ""
        for nd in all_nodes(db):
            if nd.get("icon") == key:
                nd["icon"] = ""
        save(db)
    await c.answer("🗑 মুছে ফেলা হয়েছে")
    await ic_menu(c.message)


@admin.callback_query(F.data == "ic:new")
async def ic_new(c: CallbackQuery, state: FSMContext):
    if len(load()["icons"]) >= ICON_MAX:
        await c.answer(f"❌ সর্বোচ্চ {ICON_MAX} টি আইকন রাখা যাবে", show_alert=True)
        return
    await state.clear()
    await state.set_state(IC.name)
    await tell(c.message, "✍️ নতুন আইকনের নাম লিখুন (যেমন: Telegram Channel):\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(IC.name, F.text)
async def ic_new_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip()[:25])
    await state.set_state(IC.newsticker)
    await tell(
        m,
        "🎯 এবার প্রিমিয়াম ইমোজিটি পাঠান (অথবা ইমোজিসহ মেসেজ ফরওয়ার্ড করুন)।\n"
        "শুধু সাধারণ ইমোজি পাঠালে সেটি সাধারণ আইকন হিসেবে সেভ হবে, পরে স্টিকার সেট করা যাবে।\n(বাতিল: /cancel)",
    )


@admin.message(IC.newsticker)
async def ic_new_got(m: Message, state: FSMContext):
    got = custom_emojis(m)
    if got:
        cid, emoji = got[0]
    elif m.text and m.text.strip():
        cid, emoji = "", m.text.strip()[:4]
    else:
        await m.answer("❌ ইমোজি পাঠান। (বাতিল: /cancel)")
        return
    name = (await state.get_data()).get("name") or "আইকন"
    db = load()
    key = "c_" + new_id()[:6]
    db["icons"][key] = {"name": name, "emoji": emoji, "cid": cid}
    save(db)
    await state.clear()
    await m.answer("✅ নতুন আইকন যোগ হয়েছে!")
    await ic_detail(m, key)


# ============================== 🔛 ইমোজি অন / অফ (অ্যাডমিন) ==============================
async def emsw_menu(msg):
    db = load()
    lib, fmt = emoji_lib_on(db), emoji_fmt_on(db)
    await tell(
        msg,
        f"🔛 <b>ইমোজি অন / অফ</b>\n{LINE}\n"
        f"🎨 স্টিকার / আইকন লাইব্রেরি: <b>{'✅ চালু' if lib else '⛔ বন্ধ'}</b>\n"
        f"✨ Message Formatting Emoji: <b>{'✅ চালু' if fmt else '⛔ বন্ধ'}</b>\n\n"
        "• লাইব্রেরি বন্ধ করলে বাটন ও মেসেজের কোথাও স্টিকার দেখাবে না, সব জায়গায় সাধারণ ইমোজি দেখাবে।\n"
        "• Message Formatting Emoji বন্ধ করলে মেসেজে লেখা <code>{ic&#58;নাম}</code> কোড স্টিকারের বদলে সাধারণ ইমোজি হবে।\n"
        "সেভ করা স্টিকার মুছে যায় না, আবার চালু করলেই ফিরে আসবে।",
        KB(
            [
                [B(("⛔ লাইব্রেরি বন্ধ করুন" if lib else "✅ লাইব্রেরি চালু করুন"), "emsw:lib", style="danger" if lib else "success")],
                [B(("⛔ ফরম্যাটিং ইমোজি বন্ধ করুন" if fmt else "✅ ফরম্যাটিং ইমোজি চালু করুন"), "emsw:fmt", style="danger" if fmt else "success")],
                back_row(),
            ]
        ),
    )


@admin.callback_query(F.data == "adm:emsw")
async def emsw_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await emsw_menu(c.message)
    await c.answer()


@admin.callback_query(F.data.startswith("emsw:"))
async def emsw_toggle(c: CallbackQuery):
    key = {"lib": "emoji_lib", "fmt": "emoji_fmt"}.get(c.data[5:])
    if not key:
        await c.answer()
        return
    db = load()
    db["settings"][key] = not bool(db["settings"].get(key, True))
    save(db)
    await c.answer("✅ চালু হয়েছে" if db["settings"][key] else "⛔ বন্ধ হয়েছে")
    await emsw_menu(c.message)


# ============================== 🆔 /emojiid (অ্যাডমিন) ==============================
class EID(StatesGroup):
    wait = State()


@admin.message(Command("emojiid"))
async def emojiid_cmd(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(EID.wait)
    await m.answer(
        "🆔 প্রিমিয়াম ইমোজিসহ মেসেজ পাঠান বা ফরওয়ার্ড করুন, আমি ইমোজির আইডি লিখে দেব।\n"
        "একের পর এক পাঠাতে পারবেন। শেষ করতে /cancel লিখুন।"
    )


@admin.message(EID.wait)
async def emojiid_got(m: Message, state: FSMContext):
    got = custom_emojis(m)
    if not got:
        await m.answer("❌ এই মেসেজে প্রিমিয়াম ইমোজি পাওয়া যায়নি। আবার পাঠান। (শেষ: /cancel)")
        return
    db = load()
    have = {ic.get("cid"): k for k, ic in db["icons"].items() if ic.get("cid")}
    seen, lines, added = set(), [], 0
    for cid, em in got:
        if cid in seen:
            continue
        seen.add(cid)
        if cid in have:
            key, tag = have[cid], "আগে থেকেই আছে"
        elif len(db["icons"]) >= ICON_MAX:
            lines.append(f"{esc(em)} <code>{esc(cid)}</code> — ❌ লাইব্রেরি পূর্ণ")
            continue
        else:
            n = sum(1 for k in db["icons"] if k.startswith("e_")) + 1
            key = "e_" + re.sub(r"\W", "", cid)[-10:]
            db["icons"][key] = {"name": f"প্রিমিয়াম {n}", "emoji": em or "⭐", "cid": cid}
            have[cid] = key
            added += 1
            tag = "লাইব্রেরিতে যোগ হয়েছে"
        lines.append(f"{icon_html(db, key)} <code>{esc(cid)}</code>\n   🔖 কোড: <code>{{ic&#58;{key}}}</code> — {tag}")
    if added:
        save(db)
    await m.answer(
        "🆔 <b>ইমোজি আইডি</b>\n" + "\n".join(lines)
        + f"\n\n✅ নতুন যোগ: {added} টি\nনাম বদলাতে: 🎨 স্টিকার / আইকন লাইব্রেরি → আইকন → ✏️ নাম বদলান"
    )


# ============================== ✨ Message Formatting Emoji (অ্যাডমিন) ==============================
FE_PAGE = 20


async def fe_page(msg, page=0):
    db = load()
    keys = icon_keys_sorted(db)
    pages = max(1, (len(keys) + FE_PAGE - 1) // FE_PAGE)
    page = max(0, min(page, pages - 1))
    rows, row = [], []
    for k in keys[page * FE_PAGE:(page + 1) * FE_PAGE]:
        ic = db["icons"][k]
        label = ic["name"] if ic.get("cid") else f"{ic['emoji']} {ic['name']}"
        row.append(B(label[:30], f"fe:v:{k}:{page}", icon=ic.get("cid") or None))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(B("◀️ আগের পাতা", f"fe:p:{page - 1}"))
    nav.append(B(f"📄 {page + 1}/{pages}", "fe:noop"))
    if page < pages - 1:
        nav.append(B("পরের পাতা ▶️", f"fe:p:{page + 1}"))
    rows.append(nav)
    rows.append(back_row())
    await tell(
        msg,
        f"✨ <b>Message Formatting Emoji</b>\n{LINE}\n"
        "যেকোনো মেসেজ / বাটনের লেখায় নিচের আইকনগুলো বসাতে পারবেন। একটি আইকনে চাপলে তার কোড পাবেন "
        "(যেমন <code>{ic&#58;bkash}</code>), কোডটি মেসেজে লিখলেই সেখানে আইকন দেখাবে।\n"
        "স্টিকার সেট থাকলে স্টিকার, না থাকলে সাধারণ ইমোজি দেখাবে।\n"
        f"📄 প্রতি পাতায় {FE_PAGE} টি (১০ + ১০) | মোট {len(keys)} টি",
        KB(rows),
    )


@admin.callback_query(F.data.startswith("fe:p:"))
async def fe_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if not emoji_fmt_on(load()):
        await tell(c.message, "🔒 <b>Message Formatting Emoji এখন বন্ধ আছে।</b>\nচালু করতে: প্যানেল → 🔛 ইমোজি অন / অফ", KB([[B("🔛 ইমোজি অন / অফ", "adm:emsw")]]))
        await c.answer()
        return
    await fe_page(c.message, int(c.data.split(":")[2]))
    await c.answer()


@admin.callback_query(F.data == "fe:noop")
async def fe_noop(c: CallbackQuery):
    await c.answer()


@admin.callback_query(F.data.startswith("fe:v:"))
async def fe_view(c: CallbackQuery):
    _, _, key, page = c.data.split(":")
    db = load()
    ic = db["icons"].get(key)
    if not ic:
        await c.answer("❌ আইকন পাওয়া যায়নি", show_alert=True)
        return
    await tell(
        c.message,
        f"{icon_html(db, key)} <b>{esc(ic['name'])}</b>\n{LINE}\n"
        f"📋 কোড (চেপে কপি করুন):\n<code>{{ic&#58;{key}}}</code>\n\n"
        f"এভাবে লিখুন: <code>আজই আয় করুন {{ic&#58;{key}}}</code>\n"
        f"স্টিকার: {'✅ সেট আছে' if ic.get('cid') else '❌ নেই (সাধারণ ইমোজি দেখাবে)'}",
        KB([[B("🔙 তালিকায় ফিরুন", f"fe:p:{page}")]]),
    )
    await c.answer()


# ============================== 📋 কপি সেটিং (অ্যাডমিন) ==============================
class CP(StatesGroup):
    word = State()


def cp_kb(db):
    cp = copy_map(db)
    rows = []
    for k, label in COPY_LABELS.items():
        on = cp.get(k)
        rows.append([B(f"{'✅ কপি হবে' if on else '⛔ সাধারণ লেখা'} — {label}"[:60], "cpt:" + k, style="success" if on else None)])
    n = len(db["settings"].get("copy_words", []))
    rows.append([B(f"✍️ নিজের লেখা যোগ করুন ({n} টি আছে)", "cp:add", style="success")])
    rows.append([B("🗑 যোগ করা লেখা দেখুন / মুছুন", "cp:list")])
    rows.append([B("🎭 মাল্টি নেমের কপি সেটিং", "mn:copy")])
    rows.append(back_row())
    return KB(rows)


async def cp_menu(msg):
    db = load()
    await tell(
        msg,
        f"📋 <b>কপি সেটিং</b>\n{LINE}\n"
        "যেটা ✅ থাকবে, বটের মেসেজে সেই লেখার উপর টাচ করলে ইউজারের কাছে কপি হয়ে যাবে।\n\n"
        "• নিচের তালিকা থেকে চাপ দিয়ে চালু/বন্ধ করুন\n"
        "• <b>✍️ নিজের লেখা যোগ</b> দিয়ে যেকোনো লেখা (যেমন নম্বর, @ইউজারনেম, কোড) দিলে বটের "
        "<b>সব মেসেজের</b> যেখানেই ওই লেখা থাকবে, সেখানেই টাচ করলে কপি হবে",
        cp_kb(db),
    )


@admin.callback_query(F.data == "adm:cp")
async def cp_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await cp_menu(c.message)
    await c.answer()


@admin.callback_query(F.data.startswith("cpt:"))
async def cp_toggle(c: CallbackQuery):
    key = c.data[4:]
    if key not in COPY_LABELS:
        await c.answer()
        return
    db = load()
    cp = db["settings"].setdefault("copy", dict(COPY_DEFAULT))
    cp[key] = not copy_map(db).get(key)
    save(db)
    try:
        await c.message.edit_reply_markup(reply_markup=cp_kb(db))
    except TelegramBadRequest:
        pass
    await c.answer("✅ কপি চালু" if cp[key] else "⛔ কপি বন্ধ")


@admin.callback_query(F.data == "cp:add")
async def cp_add_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(CP.word)
    await tell(
        c.message,
        "✍️ যে লেখাগুলো টাচ করলে কপি হবে তা পাঠান — প্রতি লাইনে ১টি।\n"
        "যেমন:\n<code>01712345678\n@mysupport\nPROMO2025</code>\n\n"
        "⚠️ লেখাটি বটের মেসেজে যেভাবে আছে হুবহু সেভাবে লিখতে হবে (বড়/ছোট হাতের অক্ষর মিলতে হবে)।\n"
        "(বাতিল: /cancel)",
    )
    await c.answer()


@admin.message(CP.word, F.text)
async def cp_add_got(m: Message, state: FSMContext):
    db = load()
    words = db["settings"].setdefault("copy_words", [])
    added = 0
    for line in m.text.split("\n"):
        v = line.strip()[:100]
        if len(v) < 2 or v in words:
            continue
        if len(words) >= COPY_WORDS_MAX:
            break
        words.append(v)
        added += 1
    save(db)
    await state.clear()
    await m.answer(f"✅ {added} টি লেখা যোগ হয়েছে। মোট: {len(words)}")
    await cp_menu(m)


def cp_list_kb(db):
    rows = []
    for w in db["settings"].get("copy_words", [])[:90]:
        h = hashlib.md5(w.encode("utf-8")).hexdigest()[:10]
        rows.append([B(("🗑 " + w)[:60], "cp:del:" + h, style="danger")])
    rows.append(back_row("adm:cp"))
    return KB(rows)


@admin.callback_query(F.data == "cp:list")
async def cp_list(c: CallbackQuery):
    db = load()
    if not db["settings"].get("copy_words"):
        await c.answer("📭 এখনো কোনো লেখা যোগ করা হয়নি", show_alert=True)
        return
    await tell(c.message, "🗑 মুছতে চাইলে লেখাটির উপর চাপুন:", cp_list_kb(db))
    await c.answer()


@admin.callback_query(F.data.startswith("cp:del:"))
async def cp_del(c: CallbackQuery):
    h = c.data.split(":")[2]
    db = load()
    words = db["settings"].get("copy_words", [])
    for w in list(words):
        if hashlib.md5(w.encode("utf-8")).hexdigest()[:10] == h:
            words.remove(w)
            break
    save(db)
    try:
        await c.message.edit_reply_markup(reply_markup=cp_list_kb(db))
    except TelegramBadRequest:
        pass
    await c.answer("🗑 মুছে ফেলা হয়েছে")


# ============================== 🎭 মাল্টি নেম (অ্যাডমিন) ==============================
class MN(StatesGroup):
    items = State()


def mn_kb():
    return KB(
        [
            [B("➕ নিজের লিস্ট যোগ করুন", "mn:lists", style="success")],
            [B("📋 কপি সেটিং (কোনটায় টাচ করলে কপি হবে)", "mn:copy")],
            [B("🎲 টেস্ট করুন", "mn:test")],
            [B("👁 আমার যোগ করা লিস্ট", "mn:view"), B("🗑 লিস্ট মুছুন", "mn:clrmenu", style="danger")],
            back_row(),
        ]
    )


def mn_copy_kb(db):
    copy = {**MN_COPY_DEFAULT, **db["multi"].get("copy", {})}
    rows = []
    for k, label in MN_LABELS.items():
        on = copy.get(k)
        rows.append([B(f"{'✅ কপি হবে' if on else '⛔ সাধারণ লেখা'} — {label}"[:60], "mn:cp:" + k, style="success" if on else None)])
    rows.append(back_row("adm:mn"))
    return KB(rows)


async def mn_menu(msg):
    db = load()
    mn = db["multi"]
    cnt = lambda k: len(mn.get(MN_KEYS[k]) or []) or "অটো"
    await tell(
        msg,
        f"🎭 <b>মাল্টি নেম সিস্টেম</b>\n{LINE}\n"
        "যেকোনো মেসেজে (স্টার্ট, বাটন রিপ্লাই, টাস্কের ধাপ, শপ ইত্যাদি) এগুলো লিখলে ইউজার যতবার বাটন চাপবে, প্রতিবার নতুন মান আসবে:\n"
        "• <code>%name%</code> → পুরো নাম\n"
        "• <code>%username%</code> → ইউজারনেম\n"
        "• <code>%firstname%</code> → ফার্স্ট নেম\n"
        "• <code>%lastname%</code> → লাস্ট নেম\n"
        "• <code>%number%</code> → ফোন নম্বর\n\n"
        "উদাহরণ:\n<code>নাম: %firstname% %lastname%\nনম্বর: %number%</code>\n"
        f"{LINE}\n"
        f"👤 নাম: <b>{cnt('name')}</b> | 🔖 ইউজারনেম: <b>{cnt('username')}</b> | 🅰️ ফার্স্ট: <b>{cnt('firstname')}</b> | "
        f"🅱️ লাস্ট: <b>{cnt('lastname')}</b> | 📞 নম্বর: <b>{cnt('number')}</b>\n"
        "💡 নিজের লিস্ট দিলে শুধু সেখান থেকেই র‍্যান্ডম আসবে; না দিলে বট নিজে বানাবে।\n"
        "👆 কপি সেটিং চালু থাকলে ইউজার ওই লেখার উপর টাচ করলেই কপি হয়ে যাবে।",
        mn_kb(),
    )


@admin.callback_query(F.data == "adm:mn")
async def mn_open(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await mn_menu(c.message)
    await c.answer()


@admin.callback_query(F.data == "mn:lists")
async def mn_lists(c: CallbackQuery):
    rows = [[B("➕ " + label, "mn:add:" + k)] for k, label in MN_LABELS.items()]
    rows.append(back_row("adm:mn"))
    await tell(c.message, "কোন লিস্টে যোগ করবেন?", KB(rows))
    await c.answer()


@admin.callback_query(F.data.startswith("mn:add:"))
async def mn_add_start(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[2]
    if key not in MN_KEYS:
        await c.answer()
        return
    await state.clear()
    await state.update_data(key=key)
    await state.set_state(MN.items)
    await tell(c.message, f"✍️ {MN_LABELS[key]}\nএর মানগুলো পাঠান — প্রতি লাইনে ১টি।\n(বাতিল: /cancel)")
    await c.answer()


@admin.message(MN.items, F.text)
async def mn_add_items(m: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("key")
    if key not in MN_KEYS:
        await state.clear()
        return
    db = load()
    cur = db["multi"].setdefault(MN_KEYS[key], [])
    added = 0
    for line in m.text.split("\n"):
        v = line.strip()
        if key == "username":
            v = re.sub(r"[^A-Za-z0-9_.]", "", v.lstrip("@"))[:32]
        elif key == "number":
            v = re.sub(r"[^0-9+]", "", v)[:20]
        else:
            v = v[:40]
        if v and v not in cur:
            cur.append(v)
            added += 1
    save(db)
    await state.clear()
    await m.answer(f"✅ {added} টি যোগ হয়েছে। মোট: {len(cur)}")
    await mn_menu(m)


@admin.callback_query(F.data == "mn:copy")
async def mn_copy_open(c: CallbackQuery):
    db = load()
    await tell(
        c.message,
        "📋 <b>কপি সেটিং</b>\nযেটা ✅ থাকবে, সেই লেখার উপর টাচ করলে ইউজারের কাছে কপি হয়ে যাবে। চাপ দিয়ে চালু/বন্ধ করুন:",
        mn_copy_kb(db),
    )
    await c.answer()


@admin.callback_query(F.data.startswith("mn:cp:"))
async def mn_copy_toggle(c: CallbackQuery):
    key = c.data.split(":")[2]
    if key not in MN_KEYS:
        await c.answer()
        return
    db = load()
    copy = db["multi"].setdefault("copy", dict(MN_COPY_DEFAULT))
    copy[key] = not {**MN_COPY_DEFAULT, **copy}.get(key)
    save(db)
    try:
        await c.message.edit_reply_markup(reply_markup=mn_copy_kb(db))
    except TelegramBadRequest:
        pass
    await c.answer("✅ কপি চালু" if copy[key] else "⛔ কপি বন্ধ")


@admin.callback_query(F.data == "mn:test")
async def mn_test(c: CallbackQuery):
    db = load()
    lines = ["🎲 <b>নমুনা (প্রতিবার বদলাবে)</b>"]
    for _ in range(4):
        lines.append(multi_names(db, "👤 %name% | 🔖 @%username%\n🅰️ %firstname% 🅱️ %lastname% 📞 %number%"))
    await tell(c.message, "\n\n".join(lines), KB([[B("🔄 আবার", "mn:test")], back_row("adm:mn")]))
    await c.answer()


@admin.callback_query(F.data == "mn:view")
async def mn_view(c: CallbackQuery):
    db = load()
    mn = db["multi"]
    blocks = []
    for k, label in MN_LABELS.items():
        vals = mn.get(MN_KEYS[k]) or []
        blocks.append(f"<b>{label}</b>\n" + ("\n".join(esc(x) for x in vals[:60]) or "— খালি (অটো ব্যবহার হচ্ছে)"))
    await send_blocks(c.message, blocks, KB([back_row("adm:mn")]))
    await c.answer()


@admin.callback_query(F.data == "mn:clrmenu")
async def mn_clear_menu(c: CallbackQuery):
    rows = [[B("🗑 " + label, "mn:clr:" + k, style="danger")] for k, label in MN_LABELS.items()]
    rows.append(back_row("adm:mn"))
    await tell(c.message, "কোন লিস্ট মুছবেন? (মুছলে বট নিজে অটো বানাবে)", KB(rows))
    await c.answer()


@admin.callback_query(F.data.startswith("mn:clr:"))
async def mn_clear(c: CallbackQuery):
    key = c.data.split(":")[2]
    if key not in MN_KEYS:
        await c.answer()
        return
    db = load()
    db["multi"][MN_KEYS[key]] = []
    save(db)
    await c.answer("🗑 মুছে ফেলা হয়েছে, এখন অটো ব্যবহার হবে")
    await mn_menu(c.message)


# ============================== ✅ অনুমোদিত ইউজার (শুধু মূল বট) ==============================
async def allow_menu(msg):
    db = load()
    lines = [
        "✅ <b>অনুমোদিত ইউজার</b>",
        f"👥 মোট: <b>{len(db['allowed'])}</b> জন",
        "",
        "ℹ️ এই লিস্টের বাইরের কেউ বট ব্যবহার করতে পারবে না — তাদের \"অ্যাডমিনের সাথে কথা বলুন\" মেসেজ যাবে।",
    ]
    rows = []
    for a in db["allowed"]:
        u = db["users"].get(str(a))
        name = u["name"] if u else "—"
        rows.append([B(f"🗑 {a} • {name}"[:60], f"alwd:{a}")])
    rows.append([B("➕ ইউজার যোগ করুন", "alwa")])
    rows.append(back_row())
    await tell(msg, "\n".join(lines), KB(rows))


@admin.callback_query(F.data == "adm:allow")
async def allow_open(c: CallbackQuery, state: FSMContext):
    if not cur().is_main:
        await c.answer("⛔ এটি শুধু মূল বটে চলে", show_alert=True)
        return
    await state.clear()
    await allow_menu(c.message)
    await c.answer()


@admin.callback_query(F.data == "alwa")
async def allow_add(c: CallbackQuery, state: FSMContext):
    if not cur().is_main:
        await c.answer()
        return
    await state.set_state(AllowAdd.uid)
    await tell(
        c.message,
        "🆔 যাকে অনুমতি দিবেন তার Telegram ইউজার আইডি দিন।\n"
        "একসাথে অনেকজনকে দিতে চাইলে স্পেস বা নতুন লাইন দিয়ে লিখুন।\n(বাতিল: /cancel)",
    )
    await c.answer()


@admin.message(AllowAdd.uid, F.text)
async def allow_add_val(m: Message, state: FSMContext):
    ids = re.findall(r"\d{5,}", m.text)
    if not ids:
        await m.answer("❌ সঠিক সংখ্যার আইডি দিন (বাতিল: /cancel):")
        return
    db = load()
    added = []
    for t in ids:
        uid = int(t)
        if uid in db["allowed"] or is_admin(db, uid) or uid in added:
            continue
        db["allowed"].append(uid)
        added.append(uid)
    save(db)
    await state.clear()
    for uid in added:
        await deliver(m.bot, uid, "✅ আপনাকে বট ব্যবহারের অনুমতি দেওয়া হয়েছে।\nশুরু করতে /start লিখুন।")
    await m.answer(f"✅ {len(added)} জন যোগ হয়েছে" if added else "ℹ️ নতুন কেউ যোগ হয়নি (আগে থেকেই অনুমোদিত)")
    await allow_menu(m)


@admin.callback_query(F.data.startswith("alwd:"))
async def allow_del(c: CallbackQuery):
    if not cur().is_main:
        await c.answer()
        return
    db = load()
    uid = int(c.data[5:])
    if uid in db["allowed"]:
        db["allowed"].remove(uid)
        save(db)
    await allow_menu(c.message)
    await c.answer("✅ বাদ দেওয়া হয়েছে")


# ============================== ইউজার অংশ ==============================
user = Router()


class GuardMiddleware(BaseMiddleware):
    """ব্যান চেক + Force Join চেক"""

    async def __call__(self, handler, event, data):
        tg = event.from_user
        db = load()
        if tg is None:
            return await handler(event, data)
        if cur().is_main and not is_admin(db, tg.id) and tg.id not in db.get("allowed", []):
            deny = "⛔ আপনি এই বট ব্যবহার করার অনুমতি পাননি।\n👮 অ্যাডমিনের সাথে কথা বলুন: " + str(db["settings"].get("support") or "@admin")
            if isinstance(event, CallbackQuery):
                await event.answer(deny, show_alert=True)
            else:
                await event.answer(deny, reply_markup=ReplyKeyboardRemove())
            return
        admin_user = is_admin(db, tg.id)
        if admin_user and not db["settings"].get("force_admins"):
            return await handler(event, data)
        u = db["users"].get(str(tg.id))
        if u and u.get("banned") and not admin_user:
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 আপনি ব্যান", show_alert=True)
            return
        is_start = isinstance(event, Message) and (event.text or "").startswith("/start")
        is_chk = isinstance(event, CallbackQuery) and event.data == "chk"
        if force_applies(db, tg.id) and not is_start and not is_chk:
            miss = await missing_channels(data["bot"], db, tg.id)
            if miss:
                text = "🔒 বট ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন করুন:"
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ আগে জয়েন করুন", show_alert=True)
                    await event.message.answer(text, reply_markup=join_kb(miss))
                else:
                    await event.answer(text, reply_markup=join_kb(miss))
                return
        return await handler(event, data)


user.message.middleware(GuardMiddleware())
user.callback_query.middleware(GuardMiddleware())


async def send_start(msg, db, tg_user):
    node = db["start"]
    text = render(node["reply"], db, tg_user.id)
    ikb = inline_kb(node)
    photo = node.get("photo")
    if ikb is not None:
        await tell(msg, text, ikb, photo)
        await tell(msg, "👇 মেনু থেকে বেছে নিন", main_kb(db))
    else:
        await tell(msg, text, main_kb(db), photo)


@user.message(CommandStart())
async def start_cmd(m: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    db = load()
    u, is_new = ensure_user(db, m.from_user)
    if is_new:
        arg = command.args or ""
        if arg.startswith("ref_"):
            rid = arg[4:]
            if rid != str(m.from_user.id) and rid in db["users"]:
                bonus = float(db["settings"]["ref_bonus"])
                u["referred_by"] = rid
                db["users"][rid]["balance"] += bonus
                db["users"][rid]["refs"] += 1
                add_tx(db, rid, "bonus", bonus, "রেফার বোনাস")
                save(db)
                await deliver(
                    m.bot,
                    int(rid),
                    f"🎉 <b>নতুন রেফার!</b>\n👤 {esc(m.from_user.full_name)} আপনার লিংকে জয়েন করেছেন\n"
                    f"🎁 বোনাস: <b>{money(bonus)} {db['settings']['currency']}</b>",
                )
        save(db)
    if force_applies(db, m.from_user.id):
        miss = await missing_channels(m.bot, db, m.from_user.id)
        if miss:
            await m.answer("🔒 বট ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন করুন:", reply_markup=join_kb(miss))
            return
    await send_start(m, db, m.from_user)


@user.callback_query(F.data == "chk")
async def check_join(c: CallbackQuery):
    db = load()
    miss = await missing_channels(c.bot, db, c.from_user.id)
    if miss:
        await c.answer("❌ এখনো সব চ্যানেলে জয়েন করেননি", show_alert=True)
        return
    ensure_user(db, c.from_user)
    save(db)
    try:
        await c.message.delete()
    except TelegramBadRequest:
        pass
    await send_start(c.message, db, c.from_user)
    await c.answer("✅ ধন্যবাদ!")


@user.message(Command("cancel"))
async def user_cancel(m: Message, state: FSMContext):
    await state.clear()
    await tell(m, "❎ বাতিল করা হয়েছে", main_kb(load()))


async def nav(m: Message, state: FSMContext, db):
    """মেনু/ব্যাক বাটন হলে true দেয় ও হ্যান্ডেল করে"""
    if not m.text:
        return False
    if cur().is_main and m.text in BOT_BTNS:
        await state.clear()
        await bot_buttons(m, state, db)
        return True
    if m.text == BACK_TEXT:
        await state.clear()
        await tell(m, "🏠 মেইন মেনু", main_kb(db))
        return True
    if m.text == CANCEL_TEXT:
        await state.clear()
        await tell(m, "❎ বাতিল করা হয়েছে", main_kb(db))
        return True
    item = find_menu(db, m.text)
    if item:
        await run_node(m, state, item, m.from_user)
        return True
    task = find_task_btn(db, m.text)  # কিবোর্ড বাটন হিসেবে সেট করা টাস্ক
    if task:
        await state.clear()
        ensure_user(db, m.from_user)
        if task.get("parent"):
            await begin_steps(m, state, db, task, m.from_user.id)
        else:
            await open_task(m, db, m.from_user.id, task)
        return True
    return False


async def run_node(msg, state: FSMContext, node, tg):
    """একটি বাটনের কাজ চালায়"""
    db = load()
    u, is_new = ensure_user(db, tg)
    if is_new:
        save(db)
    uid = tg.id
    kind = node.get("kind", "text")
    cur = db["settings"]["currency"]
    tpl = get_msg(db, kind) if kind in TPL_KINDS else DEFAULT_REPLY.get(kind, "")
    text = render(node.get("reply") or node.get("value") or tpl, db, uid)
    photo = node.get("photo")
    ikb = inline_kb(node)
    await state.clear()

    if kind == "input":
        await state.set_state(UserInput.waiting)
        await state.update_data(btn=node["id"])
        await tell_flow(msg, db, text, ikb, photo)
    elif kind == "withdraw":
        minimum = global_min(db)
        if u["balance"] < minimum:
            await tell(
                msg,
                f"⚠️ <b>উইথড্র করা যাচ্ছে না</b>\n{LINE}\n"
                f"📉 ন্যূনতম উইথড্র: <b>{money(minimum)} {cur}</b>\n"
                f"💰 আপনার ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>\n"
                f"{LINE}\n💡 আরও আয় করে আবার চেষ্টা করুন।",
                ikb,
            )
        else:
            await state.set_state(Withdraw.amount)
            await tell_flow(msg, db, text, ikb, photo)
    elif kind == "tasks":
        tasks = [
            t for t in db["tasks"].values()
            if t.get("active") and t.get("place") != "keyboard" and not t.get("parent")
        ]
        rows = [
            [B(f"{t['title']} • {money(t['reward'])} {cur}"[:60], "utk:" + t["id"], style=t.get("style"))]
            for t in tasks[:50]
        ]
        # এই বাটনের ভেতরে বসানো ইনলাইন বাটন/বাটন-টাস্কও লিস্টে যোগ হবে
        if ikb is not None:
            rows.extend(ikb.inline_keyboard)
        # এই বাটনের ভেতরে বসানো কিবোর্ড বাটন-টাস্ক
        has_kb = bool(node.get("children") or parent_tasks(db, node.get("id"), "parent_kb"))
        if rows:
            await tell(msg, text, KB(rows), photo)
            if has_kb:
                await tell(msg, "👇 অপশন বেছে নিন", sub_kb(node))
        elif has_kb:
            await tell(msg, text, None, photo)
            await tell(msg, "👇 অপশন বেছে নিন", sub_kb(node))
        else:
            await tell(msg, "😕 এই মুহূর্তে কোনো টাস্ক নেই। পরে আবার দেখুন।", None)
    elif kind == "shop":
        await show_shop(msg, db, text, photo, ikb)
    elif kind == "shopcat":
        ct = db["categories"].get(node.get("cat", ""))
        if not ct:
            await tell(msg, "😕 এই ক্যাটাগরিটি আর নেই। পরে আবার দেখুন।", ikb)
        else:
            head = node.get("reply") or f"📂 <b>{esc(ct['text'])}</b>\n{LINE}\n🟢 সবুজ = স্টক আছে | 🔴 লাল = স্টক নেই\n👇 পণ্য বেছে নিন:"
            await show_shop(msg, db, render(head, db, uid), photo, ikb, cat=ct["id"])
    elif kind == "addmoney":
        await show_addmoney(msg, db, text, photo, ikb)
    elif kind == "cart":
        await show_cart(msg, db, u)
    elif kind == "orders":
        await send_blocks(msg, orders_blocks(db, uid), ikb)
    elif kind == "wallet":
        await tell(msg, (text + "\n\n" if text else "") + wallet_text(db, uid), ikb, photo)
    elif kind == "profile":
        await tell(msg, (text + "\n\n" if text else "") + profile_text(db, uid), ikb, photo)
    elif kind == "refund":
        await show_refund(msg, db, uid, text, ikb)
    elif kind == "ticket":
        await state.set_state(TicketMsg.msg)
        await tell_flow(msg, db, text, ikb, photo)
    elif kind == "history":
        subs = sorted((s for s in db["subs"].values() if s["uid"] == str(uid)), key=lambda s: s["time"], reverse=True)[:10]
        lines = [text, LINE]
        if not subs:
            lines.append("📭 এখনো কিছু নেই")
        for s in subs:
            if s["type"] == "withdraw":
                lines.append(f"{STATUS_ICON[s['status']]} 💸 উইথড্র — {money(s['amount'])} {cur} ({esc(s.get('method') or '-')})")
            else:
                lines.append(f"{STATUS_ICON[s['status']]} {esc(s['btn'])} — {money(s.get('reward', 0))} {cur}")
        await tell(msg, "\n".join(lines), ikb)
    else:  # text / balance / refer / support
        children = node.get("children") or parent_tasks(db, node.get("id"), "parent_kb")
        if children:
            if ikb is None:
                await tell(msg, text, sub_kb(node), photo)
            else:
                await tell(msg, text, ikb, photo)
                await tell(msg, "👇 অপশন বেছে নিন", sub_kb(node))
        else:
            await tell(msg, text, ikb, photo)


# ---------- ইউজার ইনপুট (লেখা / ছবি জমা) ----------
@user.message(UserInput.waiting)
async def user_input_got(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    data = await state.get_data()
    ref = data.get("btn", "")
    u, _ = ensure_user(db, m.from_user)
    stype, tid = "input", None
    t = None
    if ref.startswith("task:"):
        t = db["tasks"].get(ref[5:])
        if not t or not t.get("active"):
            await state.clear()
            await tell(m, "❌ এই টাস্ক এখন চালু নেই", main_kb(db))
            return
        if task_taken(db, str(m.from_user.id), t["id"]):
            await state.clear()
            await tell(m, "⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন", main_kb(db))
            return
        label, reward, stype, tid = t["title"], float(t["reward"]), "task", t["id"]
        done = t.get("done_msg") or DEFAULT_TASK_DONE
    else:
        node = get_node(db, ref)
        if node is None:
            await state.clear()
            return
        label, reward = node["text"], float(node.get("reward", 0))
        done = node.get("done_msg", "✅ আপনার সাবমিশন জমা হয়েছে")
    sid = new_id()
    s = {
        "type": stype,
        "uid": str(m.from_user.id),
        "btn": label,
        "tid": tid,
        "content": m.text or m.caption or "[ফাইল/ছবি]",
        "reward": reward,
        "status": "pending",
        "time": int(time.time()),
    }
    db["subs"][sid] = s
    save(db)
    await state.clear()
    await notify_admins(m.bot, submission_text(db, s), approve_kb("ap", sid))
    if not m.text:
        for aid in admin_ids(db):
            try:
                await m.copy_to(aid)
            except Exception:
                pass
    await tell(m, done, main_kb(db))
    if t and t.get("repeat"):  # আবার মেসেজ পাঠানোর বাটন
        await tell(m, "🔁 চাইলে আবার জমা দিতে পারবেন:", KB([[B("➕ আবার মেসেজ পাঠান", "utd:" + t["id"], style="success")]]))


# ---------- উইথড্র ----------
@user.message(Withdraw.amount, F.text)
async def wd_amount(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    u, _ = ensure_user(db, m.from_user)
    v = parse_num(m.text)
    cur = db["settings"]["currency"]
    minimum = global_min(db)
    if v is None or v <= 0:
        await m.answer("❌ সঠিক সংখ্যা লিখুন (বাতিল: /cancel):")
        return
    if v < minimum:
        await m.answer(f"❌ ন্যূনতম {money(minimum)} {cur} উইথড্র করতে হবে। আবার লিখুন:")
        return
    if v > u["balance"]:
        await m.answer(f"❌ আপনার ব্যালেন্স {money(u['balance'])} {cur}। এর বেশি উইথড্র করা যাবে না। আবার লিখুন:")
        return
    await state.update_data(amount=v)
    methods = [x for x in db["wd_methods"] if method_min(db, x) <= v]
    if db["wd_methods"]:
        if not methods:
            await m.answer("❌ এই পরিমাণের জন্য কোনো মাধ্যম পাওয়া যায়নি। বেশি পরিমাণ লিখুন:")
            return
        await state.set_state(Withdraw.method)
        await m.answer(
            f"✅ পরিমাণ: <b>{money(v)} {cur}</b>\n{LINE}\n🏦 কোন মাধ্যমে নিতে চান? বেছে নিন:",
            reply_markup=method_kb(db, methods),
        )
    else:
        await state.set_state(Withdraw.account)
        await m.answer("📮 আপনার পেমেন্ট অ্যাকাউন্ট/নম্বর লিখুন (যেমন: bKash 01XXXXXXXXX):")


async def choose_method(msg, state: FSMContext, db, mt):
    await state.update_data(method=mt["name"])
    await state.set_state(Withdraw.account)
    hint = mt.get("hint") or f"আপনার {mt['name']} অ্যাকাউন্ট/নম্বর লিখুন"
    kb = cancel_kb() if db["settings"].get("cancel_on", True) else ReplyKeyboardRemove()
    await tell(msg, f"🏦 <b>{method_text(db, mt)}</b>\n{LINE}\n📮 {esc(hint)}:", kb)


@user.message(Withdraw.method, F.text)
async def wd_method_text(m: Message, state: FSMContext):
    db = load()
    amount = float((await state.get_data()).get("amount", 0))
    t = m.text.strip()
    for x in db["wd_methods"]:
        if method_min(db, x) <= amount and t in (method_label(db, x), x["name"]):
            await choose_method(m, state, db, x)
            return
    if await nav(m, state, db):
        return
    await m.answer("👆 নিচের বাটন থেকে পেমেন্ট মাধ্যম বেছে নিন (বাতিল: /cancel)")


@user.callback_query(Withdraw.method, F.data.startswith("uwm:"))
async def wd_method_pick(c: CallbackQuery, state: FSMContext):
    db = load()
    mt = get_method(db, c.data[4:])
    if not mt:
        await c.answer("❌ মাধ্যমটি পাওয়া যায়নি", show_alert=True)
        return
    await choose_method(c.message, state, db, mt)
    await c.answer()


@user.message(Withdraw.account, F.text)
async def wd_account(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    data = await state.get_data()
    amount = float(data["amount"])
    method = data.get("method", "")
    u, _ = ensure_user(db, m.from_user)
    if amount > u["balance"]:
        await state.clear()
        await m.answer("❌ ব্যালেন্স যথেষ্ট নয়")
        return
    u["balance"] -= amount
    add_tx(db, m.from_user.id, "withdraw", -amount, method or "উইথড্র")
    sid = new_id()
    s = {
        "type": "withdraw",
        "uid": str(m.from_user.id),
        "amount": amount,
        "method": method,
        "account": m.text,
        "status": "pending",
        "time": int(time.time()),
    }
    db["subs"][sid] = s
    save(db)
    await state.clear()
    await notify_admins(m.bot, withdraw_text(db, s), approve_kb("wd", sid))
    await tell(
        m,
        fmt_msg(db, "wd_sent", m.from_user.id, amount=amount, method=method or "-", account=m.text),
        main_kb(db),
    )


# ---------- মেনু বাটন ----------
@user.message(F.text, StateFilter(None))
async def menu_press(m: Message, state: FSMContext):
    await nav(m, state, load())


# ---------- ইনলাইন বাটন ----------
@user.callback_query(F.data.startswith("i:"))
async def inline_press(c: CallbackQuery, state: FSMContext):
    db = load()
    node = get_node(db, c.data[2:])
    await c.answer()
    if node is not None:
        await run_node(c.message, state, node, c.from_user)


# ---------- টাস্ক (ইউজার) ----------
async def open_task(msg, db, uid, t):
    """টাস্কের বিবরণ ও 'কাজ জমা দিন' বাটন দেখায়"""
    cur = db["settings"]["currency"]
    if not t.get("active"):
        await tell(msg, "❌ এই টাস্ক এখন চালু নেই")
        return
    if task_taken(db, str(uid), t["id"]):
        await tell(msg, "⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন")
        return
    rows = []
    if t.get("link"):
        rows.append([B("🔗 কাজের লিংক", url=t["link"])])
    for b in t.get("btns", []):
        rows.append([B(b["text"], url=b["url"])])
    rows.append([B("📝 কাজ জমা দিন", "utd:" + t["id"], style="success")])
    text = f"🎯 <b>{esc(t['title'])}</b>\n{LINE}\n"
    if t.get("desc"):
        text += f"📋 <b>কাজ:</b>\n{esc(t['desc'])}\n\n"
    text += f"🎁 পুরস্কার: <b>{money(t['reward'])} {cur}</b>\n"
    text += "🔁 বারবার জমা দেওয়া যাবে" if t.get("repeat") else "☝️ একবারই জমা দেওয়া যাবে"
    await tell(msg, multi_names(db, text), KB(rows))


@user.callback_query(F.data.startswith("utk:"))
async def task_view(c: CallbackQuery):
    db = load()
    t = db["tasks"].get(c.data[4:])
    ensure_user(db, c.from_user)
    if not t or not t.get("active"):
        await c.answer("❌ টাস্ক পাওয়া যায়নি", show_alert=True)
        return
    if task_taken(db, str(c.from_user.id), t["id"]):
        await c.answer("⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন", show_alert=True)
        return
    await open_task(c.message, db, c.from_user.id, t)
    await c.answer()


@user.callback_query(F.data.startswith("utd:"))
async def task_done(c: CallbackQuery, state: FSMContext):
    db = load()
    t = db["tasks"].get(c.data[4:])
    ensure_user(db, c.from_user)
    if not t or not t.get("active"):
        await c.answer("❌ টাস্ক পাওয়া যায়নি", show_alert=True)
        return
    if task_taken(db, str(c.from_user.id), t["id"]):
        await c.answer("⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন", show_alert=True)
        return
    await state.clear()
    await state.set_state(UserTask.answering)
    await state.update_data(tid=t["id"], idx=0, answers=[])
    if db["settings"].get("cancel_on", True):
        await tell(c.message, "✍️ একে একে উত্তর দিন। বাতিল করতে নিচের বাটন চাপুন 👇", cancel_kb())
    await send_step(c.message, db, t, 0)
    await c.answer()


def task_steps(t):
    if t.get("steps"):
        return t["steps"]
    return [{"q": t.get("prompt") or DEFAULT_TASK_PROMPT, "buttons": []}]


async def send_step(msg, db, t, idx):
    steps = task_steps(t)
    st = steps[idx]
    head = f"📝 <b>ধাপ {idx + 1}/{len(steps)}</b>\n{LINE}\n" if len(steps) > 1 else ""
    rows = [[B(b["text"], url=b["url"])] for b in st.get("buttons", [])]
    await tell(msg, multi_names(db, head + st["q"]), KB(rows) if rows else None)


@user.message(UserTask.answering)
async def task_answer(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    data = await state.get_data()
    t = db["tasks"].get(data.get("tid", ""))
    if not t or not t.get("active"):
        await state.clear()
        await tell(m, "❌ এই টাস্ক এখন চালু নেই", main_kb(db))
        return
    ensure_user(db, m.from_user)
    steps = task_steps(t)
    idx = int(data.get("idx", 0))
    answers = list(data.get("answers", []))
    photo = m.photo[-1].file_id if m.photo else None
    if not m.text and not m.photo:  # অন্য ধরনের ফাইল সরাসরি অ্যাডমিনদের কাছে যায়
        for aid in admin_ids(db):
            try:
                await m.copy_to(aid)
            except Exception:
                pass
    answers.append({"q": steps[idx]["q"], "a": m.text or m.caption or "[ফাইল/ছবি]", "photo": photo})
    idx += 1
    if idx < len(steps):
        await state.update_data(idx=idx, answers=answers)
        await send_step(m, db, t, idx)
        return
    if task_taken(db, str(m.from_user.id), t["id"]):
        await state.clear()
        await tell(m, "⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন", main_kb(db))
        return
    qa = [{"q": re.sub(r"<[^>]+>", "", a["q"]), "a": a["a"]} for a in answers]
    content = "\n\n".join(f"❓ {x['q']}\n💬 {x['a']}" for x in qa)
    sid = new_id()
    s = {
        "type": "task",
        "uid": str(m.from_user.id),
        "btn": t["title"],
        "tid": t["id"],
        "content": content,
        "qa": qa,
        "reward": float(t["reward"]),
        "status": "pending",
        "time": int(time.time()),
    }
    db["subs"][sid] = s
    save(db)
    await state.clear()
    await notify_admins(m.bot, submission_text(db, s), approve_kb("ap", sid))
    for a in answers:
        if a.get("photo"):
            for aid in admin_ids(db):
                try:
                    await m.bot.send_photo(aid, a["photo"])
                except Exception:
                    pass
    await tell(m, t.get("done_msg") or DEFAULT_TASK_DONE, main_kb(db))
    if t.get("repeat"):
        await tell(m, "🔁 চাইলে আবার জমা দিতে পারবেন:", KB([[B("➕ আবার মেসেজ পাঠান", "utd:" + t["id"], style="success")]]))


# ============================== 🛒 শপ / কার্ট / ওয়ালেট (ইউজার) ==============================
class AddMoney(StatesGroup):
    amount = State()
    trx = State()


class RefundReq(StatesGroup):
    reason = State()


class TicketMsg(StatesGroup):
    msg = State()


_BUYING = set()  # একই ইউজারের একসাথে দুইবার কেনা আটকাতে


async def edit_or_send(c: CallbackQuery, text, markup):
    try:
        await c.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await tell(c.message, text, markup)
    except Exception:
        await tell(c.message, text, markup)


def shop_cat_ok(db, cid):
    return bool(cid) and cid in db["categories"]


async def show_shop(msg, db, text, photo=None, ikb=None, cat=None):
    cur = db["settings"]["currency"]
    rows = []
    allp = [p for p in products(db).values() if p.get("active", True)]
    if cat is None:
        for ct in db["categories"].values():
            cnt = sum(1 for p in allp if p.get("cat") == ct["id"])
            if cnt:
                rows.append([B(f"{node_label(db, ct)} ({cnt})"[:60], "shc:" + ct["id"], style="primary", icon=node_cid(db, ct))])
        plist = [p for p in allp if not shop_cat_ok(db, p.get("cat"))]
    else:
        plist = [p for p in allp if p.get("cat") == cat]
    for p in plist:
        ok = avail(p)
        label = f"{'🟢' if ok else '🔴'} {p['name']} • {money(p['price'])} {cur} • {stock_short(p)}"
        rows.append([B(label[:60], "shp:" + p["id"], style="success" if ok else "danger")])
    rows = rows[:88]
    if not rows:
        await tell(msg, "😕 এই মুহূর্তে শপে কোনো পণ্য নেই। পরে আবার দেখুন।", ikb)
        return
    rows.append([B("🧺 কার্ট", "ctv"), B("🧾 আমার অর্ডার", "shpo")])
    if cat is not None:
        rows.append([B("🔙 সব ক্যাটাগরি", "shl")])
    if ikb is not None and cat is None:
        rows.extend(ikb.inline_keyboard)
    await tell(msg, text, KB(rows), photo)


@user.callback_query(F.data == "shl")
async def shop_back(c: CallbackQuery):
    db = load()
    ensure_user(db, c.from_user)
    await show_shop(c.message, db, DEFAULT_REPLY["shop"])
    await c.answer()


@user.callback_query(F.data.startswith("shc:"))
async def shop_cat(c: CallbackQuery):
    db = load()
    ensure_user(db, c.from_user)
    ct = db["categories"].get(c.data[4:])
    if not ct:
        await c.answer("❌ ক্যাটাগরি পাওয়া যায়নি", show_alert=True)
        return
    await show_shop(c.message, db, f"📂 <b>{esc(ct['text'])}</b>\n{LINE}\n🟢 সবুজ = স্টক আছে | 🔴 লাল = স্টক নেই\n👇 পণ্য বেছে নিন:", cat=ct["id"])
    await c.answer()


@user.callback_query(F.data == "shn")
async def shop_nostock(c: CallbackQuery):
    await c.answer("🔴 দুঃখিত, এই পণ্যের স্টক এখন নেই", show_alert=True)


@user.callback_query(F.data == "ctn")
async def cart_noop(c: CallbackQuery):
    await c.answer()


@user.callback_query(F.data.startswith("shp:"))
async def shop_view(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data[4:])
    u, is_new = ensure_user(db, c.from_user)
    if is_new:
        save(db)
    if not p or not p.get("active", True):
        await c.answer("❌ পণ্যটি পাওয়া যায়নি", show_alert=True)
        return
    cur = db["settings"]["currency"]
    ok = avail(p)
    n = stock_n(p)
    back = ("shc:" + p["cat"]) if shop_cat_ok(db, p.get("cat")) else "shl"
    text = f"🛍 <b>{esc(p['name'])}</b>\n{LINE}\n"
    if p.get("desc"):
        text += f"{p['desc']}\n\n"
    text += f"💰 দাম: <b>{money(p['price'])} {cur}</b>\n"
    if is_manual(p):
        text += "🚚 ডেলিভারি: <b>ম্যানুয়াল</b> (অ্যাডমিন পাঠাবে)\n"
        text += "📦 স্টক: <b>আছে</b> 🟢\n" if ok else "📦 স্টক: <b>নেই</b> 🔴\n"
    else:
        text += "⚡ ডেলিভারি: <b>অটো</b> (সাথে সাথে)\n"
        text += f"📦 স্টক: <b>{n} টি</b> 🟢\n" if ok else "📦 স্টক: <b>নেই</b> 🔴\n"
    text += f"👛 আপনার ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>"
    rows = []
    if ok:
        rows.append([B(f"⚡ এখনই কিনুন • {money(p['price'])} {cur}", "shb:" + p["id"], style="success")])
        rows.append([B("🧺 কার্টে যোগ করুন", "cta:" + p["id"])])
    else:
        rows.append([B("❌ স্টক নেই", "shn", style="danger")])
    rows.append([B("🧺 কার্ট দেখুন", "ctv"), B("🔙 পিছনে", back)])
    await tell(c.message, multi_names(db, text), KB(rows), p.get("photo"))
    await c.answer()


@user.callback_query(F.data.startswith("shb:"))
async def shop_confirm(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data[4:])
    u, is_new = ensure_user(db, c.from_user)
    if is_new:
        save(db)
    cur = db["settings"]["currency"]
    if not p or not p.get("active", True):
        await c.answer("❌ পণ্যটি পাওয়া যায়নি", show_alert=True)
        return
    if not avail(p):
        await c.answer("🔴 দুঃখিত, স্টক শেষ হয়ে গেছে", show_alert=True)
        return
    price = float(p["price"])
    if u["balance"] < price:
        await c.answer(
            f"❌ ব্যালেন্স কম!\nদরকার: {money(price)} {cur}\nআপনার ব্যালেন্স: {money(u['balance'])} {cur}",
            show_alert=True,
        )
        return
    how = "অ্যাডমিন যাচাই করে ম্যানুয়ালি ডেলিভারি দেবেন।" if is_manual(p) else "কিনলে পণ্য সাথে সাথে অটো ডেলিভারি হবে।"
    await tell(
        c.message,
        f"🛒 <b>কেনার নিশ্চিতকরণ</b>\n{LINE}\n"
        f"🛍 পণ্য: <b>{esc(p['name'])}</b>\n"
        f"💰 মূল্য: <b>{money(price)} {cur}</b>\n"
        f"👛 ব্যালেন্স: <b>{money(u['balance'])} {cur}</b> → <b>{money(u['balance'] - price)} {cur}</b>\n{LINE}\n"
        f"{how}",
        KB([[B("✅ হ্যাঁ, কিনুন", "shy:" + p["id"], style="success"), B("❌ না", "shp:" + p["id"], style="danger")]]),
    )
    await c.answer()


async def do_purchase(bot, tg, lines):
    """lines = [(pid, qty)]। সফল হলে None, ব্যর্থ হলে এরর লেখা রিটার্ন করে"""
    db = load()
    u, _ = ensure_user(db, tg)
    uid = tg.id
    cur = db["settings"]["currency"]
    plist, total = [], 0.0
    for pid, q in lines:
        p = products(db).get(pid)
        if not p or not p.get("active", True):
            return "❌ পণ্যটি পাওয়া যায়নি"
        if not avail(p):
            return f"🔴 {p['name']} — স্টক নেই"
        if not is_manual(p) and len(p["stock"]) < q:
            return f"🔴 {p['name']} — স্টকে মাত্র {len(p['stock'])} টি আছে"
        plist.append((p, q))
        total += float(p["price"]) * q
    total = round(total, 2)
    if not plist:
        return "❌ কিছু বাছা হয়নি"
    if u["balance"] < total:
        return f"❌ ব্যালেন্স কম! দরকার: {money(total)} {cur}, আপনার ব্যালেন্স: {money(u['balance'])} {cur}"

    # --- এই অংশে কোনো await নেই, তাই স্টক/ব্যালেন্স একসাথে নিরাপদে আপডেট হয় ---
    new_orders, taken = [], []
    for p, q in plist:
        for _ in range(q):
            o = {"id": new_id(), "uid": str(uid), "pid": p["id"], "name": p["name"], "price": float(p["price"]), "time": int(time.time())}
            if is_manual(p):
                o.update(item="", status="pending", manual=True)
            else:
                item = p["stock"].pop(0)
                taken.append((p, item))
                o.update(item=item, status="done", manual=False)
            p["sold"] = p.get("sold", 0) + 1
            db["orders"].append(o)
            new_orders.append(o)
    u["balance"] = round(u["balance"] - total, 2)
    tx = add_tx(db, uid, "purchase", -total, ", ".join(f"{p['name']}×{q}" for p, q in plist))
    save(db)

    def undo():
        for p, item in reversed(taken):
            p["stock"].insert(0, item)
        for o in new_orders:
            if o in db["orders"]:
                db["orders"].remove(o)
            pp = products(db).get(o["pid"])
            if pp:
                pp["sold"] = max(0, pp.get("sold", 1) - 1)
        u["balance"] = round(u["balance"] + total, 2)
        if tx in db["tx"]:
            db["tx"].remove(tx)
        save(db)

    blocks = [f"✅ <b>কেনা সফল হয়েছে!</b>\n{LINE}\n💰 মোট মূল্য: <b>{money(total)} {cur}</b>"]
    for o in new_orders:
        if o["manual"]:
            blocks.append(
                f"⏳ <b>{esc(o['name'])}</b> • 🆔 <code>{o['id']}</code>\n"
                "🧑‍💼 ম্যানুয়াল ডেলিভারি — অ্যাডমিন এপ্রুভ করলেই পণ্য পাঠানো হবে"
            )
        else:
            blocks.append(f"🛍 <b>{esc(o['name'])}</b> • 🆔 <code>{o['id']}</code>\n📦 <code>{esc(o['item'])}</code>")
    blocks.append(f"{LINE}\n👛 অবশিষ্ট ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>")
    chunks, buf = [], ""
    for b in blocks:
        if buf and len(buf) + len(b) + 2 > 3500:
            chunks.append(buf.strip())
            buf = ""
        buf += b + "\n\n"
    chunks.append(buf.strip())
    markup = KB([[B("🛒 আবার শপে যান", "shl"), B("🧾 আমার অর্ডার", "shpo")]])
    sent = await deliver(bot, uid, chunks[0], markup if len(chunks) == 1 else None)
    if not sent:  # ডেলিভারি না গেলে সব আগের অবস্থায় ফেরত
        undo()
        return "❌ ডেলিভারি করা যায়নি, টাকা কাটা হয়নি। আবার চেষ্টা করুন"
    for i, ch in enumerate(chunks[1:], 1):
        await deliver(bot, uid, ch, markup if i == len(chunks) - 1 else None)

    # অ্যাডমিন নোটিফিকেশন
    auto = [o for o in new_orders if not o["manual"]]
    if auto:
        names = ", ".join(sorted({o["name"] for o in auto}))
        await notify_admins(
            bot,
            f"🛒 <b>নতুন বিক্রি!</b>\n{LINE}\n"
            f"🛍 {esc(names)} • {money(sum(o['price'] for o in auto))} {cur}\n"
            f"👤 {esc(u['name'])} (@{esc(u.get('username') or '-')})\n"
            f"🆔 <code>{uid}</code>\n"
            + "\n".join(f"{'📦 বাকি স্টক: ' + str(len(p['stock'])) if p['stock'] else '🔴 স্টক শেষ: ' + esc(p['name'])}" for p, _ in plist if not is_manual(p)),
        )
    for o in new_orders:
        if o["manual"]:
            await notify_admins(bot, "🔔 <b>নতুন ম্যানুয়াল অর্ডার!</b>\n" + order_admin_text(db, o), order_btns(o))
    return None


@user.callback_query(F.data.startswith("shy:"))
async def shop_buy(c: CallbackQuery):
    uid = c.from_user.id
    if (cur().key, uid) in _BUYING:
        await c.answer("⏳ একটু অপেক্ষা করুন")
        return
    _BUYING.add((cur().key, uid))
    try:
        err = await do_purchase(c.bot, c.from_user, [(c.data[4:], 1)])
        if err:
            await c.answer(err[:190], show_alert=True)
            return
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await c.answer("✅ কেনা সফল!")
    finally:
        _BUYING.discard((cur().key, uid))


# ---------- অর্ডার হিস্টোরি ----------
def orders_blocks(db, uid, limit=10):
    cur = db["settings"]["currency"]
    mine = [o for o in db.get("orders", []) if o["uid"] == str(uid)][-limit:]
    blocks = ["🧾 <b>আপনার সাম্প্রতিক অর্ডার</b>"]
    if not mine:
        blocks.append("📭 এখনো কোনো অর্ডার নেই")
    for o in reversed(mine):
        st = order_status(o)
        when = datetime.fromtimestamp(o["time"], TZ).strftime("%d/%m/%Y %H:%M")
        if st == "pending":
            body = "⏳ ম্যানুয়াল ডেলিভারি পেন্ডিং"
        elif st == "refunded":
            body = "♻️ রিফান্ড হয়েছে"
        else:
            body = f"📦 <code>{esc(str(o.get('item', ''))[:300])}</code>"
        blocks.append(f"#{o['id']} • <b>{esc(o['name'])}</b> • {money(o['price'])} {cur}\n🕐 {when}\n{body}")
    return blocks


@user.callback_query(F.data == "shpo")
async def shop_orders(c: CallbackQuery):
    db = load()
    if not any(o["uid"] == str(c.from_user.id) for o in db.get("orders", [])):
        await c.answer("📭 এখনো কোনো অর্ডার নেই", show_alert=True)
        return
    await send_blocks(c.message, orders_blocks(db, c.from_user.id))
    await c.answer()


# ---------- কার্ট ----------
def cart_build(db, u):
    cur = db["settings"]["currency"]
    cart = u.setdefault("cart", {})
    lines, total = [], 0.0
    for pid in list(cart):
        p = products(db).get(pid)
        if not p or not p.get("active", True) or cart[pid] < 1:
            cart.pop(pid, None)
            continue
        lines.append((p, cart[pid]))
        total += float(p["price"]) * cart[pid]
    total = round(total, 2)
    if not lines:
        return "🧺 <b>আপনার কার্ট খালি</b>\n👇 শপ থেকে পণ্য কার্টে যোগ করুন।", KB([[B("🛍 শপে যান", "shl", style="success")]]), lines, 0.0
    text = [f"🧺 <b>আপনার কার্ট</b>\n{LINE}"]
    rows = []
    for i, (p, q) in enumerate(lines, 1):
        ok = avail(p)
        text.append(f"{i}. {'🟢' if ok else '🔴'} {esc(p['name'])} × {q} = <b>{money(float(p['price']) * q)} {cur}</b>")
        rows.append(
            [
                B("➖", "ctm:" + p["id"]),
                B(f"{p['name'][:16]} ×{q}", "ctn"),
                B("➕", "ctp:" + p["id"]),
                B("🗑", "ctx:" + p["id"], style="danger"),
            ]
        )
    text.append(f"{LINE}\n💰 মোট: <b>{money(total)} {cur}</b>\n👛 ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>")
    rows.append([B("✅ চেকআউট (কিনুন)", "ctc", style="success")])
    rows.append([B("🗑 কার্ট খালি করুন", "ctz"), B("🛍 শপে ফিরুন", "shl")])
    return "\n".join(text), KB(rows), lines, total


async def show_cart(msg, db, u):
    text, kb, _, _ = cart_build(db, u)
    await tell(msg, text, kb)


@user.callback_query(F.data == "ctv")
async def cart_open(c: CallbackQuery):
    db = load()
    u, _ = ensure_user(db, c.from_user)
    await show_cart(c.message, db, u)
    await c.answer()


def cart_cap(p):
    return 20 if is_manual(p) else len(p.get("stock", []))


@user.callback_query(F.data.startswith("cta:"))
async def cart_add(c: CallbackQuery):
    db = load()
    p = products(db).get(c.data[4:])
    u, _ = ensure_user(db, c.from_user)
    if not p or not p.get("active", True):
        await c.answer("❌ পণ্যটি পাওয়া যায়নি", show_alert=True)
        return
    if not avail(p):
        await c.answer("🔴 দুঃখিত, স্টক নেই", show_alert=True)
        return
    cart = u.setdefault("cart", {})
    if cart.get(p["id"], 0) + 1 > cart_cap(p):
        await c.answer(f"⚠️ এর বেশি যোগ করা যাবে না (সর্বোচ্চ {cart_cap(p)} টি)", show_alert=True)
        return
    cart[p["id"]] = cart.get(p["id"], 0) + 1
    save(db)
    await c.answer(f"✅ কার্টে যোগ হয়েছে ({cart[p['id']]} টি)")


async def cart_refresh(c: CallbackQuery, db, u):
    text, kb, _, _ = cart_build(db, u)
    await edit_or_send(c, text, kb)


@user.callback_query(F.data.startswith("ctp:"))
async def cart_plus(c: CallbackQuery):
    db = load()
    u, _ = ensure_user(db, c.from_user)
    p = products(db).get(c.data[4:])
    cart = u.setdefault("cart", {})
    if p and p["id"] in cart:
        if cart[p["id"]] + 1 > cart_cap(p):
            await c.answer(f"⚠️ সর্বোচ্চ {cart_cap(p)} টি", show_alert=True)
            return
        cart[p["id"]] += 1
        save(db)
    await cart_refresh(c, db, u)
    await c.answer()


@user.callback_query(F.data.startswith("ctm:"))
async def cart_minus(c: CallbackQuery):
    db = load()
    u, _ = ensure_user(db, c.from_user)
    cart = u.setdefault("cart", {})
    pid = c.data[4:]
    if pid in cart:
        cart[pid] -= 1
        if cart[pid] < 1:
            cart.pop(pid, None)
        save(db)
    await cart_refresh(c, db, u)
    await c.answer()


@user.callback_query(F.data.startswith("ctx:"))
async def cart_remove(c: CallbackQuery):
    db = load()
    u, _ = ensure_user(db, c.from_user)
    u.setdefault("cart", {}).pop(c.data[4:], None)
    save(db)
    await cart_refresh(c, db, u)
    await c.answer("🗑 সরানো হয়েছে")


@user.callback_query(F.data == "ctz")
async def cart_clear(c: CallbackQuery):
    db = load()
    u, _ = ensure_user(db, c.from_user)
    u["cart"] = {}
    save(db)
    await cart_refresh(c, db, u)
    await c.answer("🗑 কার্ট খালি হয়েছে")


@user.callback_query(F.data == "ctc")
async def cart_checkout(c: CallbackQuery):
    db = load()
    u, _ = ensure_user(db, c.from_user)
    cur = db["settings"]["currency"]
    _, _, lines, total = cart_build(db, u)
    if not lines:
        await c.answer("🧺 কার্ট খালি", show_alert=True)
        return
    for p, q in lines:
        if not avail(p) or (not is_manual(p) and len(p["stock"]) < q):
            await c.answer(f"🔴 {p['name']} এর স্টক যথেষ্ট নেই, কার্ট ঠিক করুন", show_alert=True)
            return
    if u["balance"] < total:
        await c.answer(
            f"❌ ব্যালেন্স কম!\nদরকার: {money(total)} {cur}\nআপনার ব্যালেন্স: {money(u['balance'])} {cur}",
            show_alert=True,
        )
        return
    await tell(
        c.message,
        f"🛒 <b>চেকআউট নিশ্চিতকরণ</b>\n{LINE}\n"
        f"📦 মোট পণ্য: <b>{sum(q for _, q in lines)} টি</b>\n"
        f"💰 মোট মূল্য: <b>{money(total)} {cur}</b>\n"
        f"👛 ব্যালেন্স: <b>{money(u['balance'])} {cur}</b> → <b>{money(u['balance'] - total)} {cur}</b>",
        KB([[B("✅ হ্যাঁ, কিনুন", "ctk", style="success"), B("❌ না", "ctv", style="danger")]]),
    )
    await c.answer()


@user.callback_query(F.data == "ctk")
async def cart_buy(c: CallbackQuery):
    uid = c.from_user.id
    if (cur().key, uid) in _BUYING:
        await c.answer("⏳ একটু অপেক্ষা করুন")
        return
    _BUYING.add((cur().key, uid))
    try:
        db = load()
        u, _ = ensure_user(db, c.from_user)
        _, _, lines, _ = cart_build(db, u)
        if not lines:
            await c.answer("🧺 কার্ট খালি", show_alert=True)
            return
        err = await do_purchase(c.bot, c.from_user, [(p["id"], q) for p, q in lines])
        if err:
            await c.answer(err[:190], show_alert=True)
            return
        u["cart"] = {}
        save(db)
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await c.answer("✅ কেনা সফল!")
    finally:
        _BUYING.discard((cur().key, uid))


# ---------- ওয়ালেট ও প্রোফাইল ----------
def wallet_text(db, uid):
    u = db["users"].get(str(uid)) or {"balance": 0}
    cur = db["settings"]["currency"]
    today = datetime.now(TZ).date()
    orders = [o for o in db.get("orders", []) if o["uid"] == str(uid) and order_status(o) != "refunded"]
    total_spent = sum(o["price"] for o in orders)
    today_spent = sum(o["price"] for o in orders if datetime.fromtimestamp(o["time"], TZ).date() == today)
    txs = [t for t in db.get("tx", []) if t["uid"] == str(uid)][-10:]
    lines = [
        f"👛 <b>আপনার ওয়ালেট</b>\n{LINE}",
        f"💰 মেইন ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>",
        f"📅 আজকের খরচ: <b>{money(today_spent)} {cur}</b>",
        f"📊 টোটাল খরচ: <b>{money(total_spent)} {cur}</b>",
        f"{LINE}\n📜 <b>সাম্প্রতিক লেনদেন</b>",
    ]
    if not txs:
        lines.append("📭 এখনো কোনো লেনদেন নেই")
    for t in reversed(txs):
        sign = "+" if t["amount"] >= 0 else "−"
        when = datetime.fromtimestamp(t["time"], TZ).strftime("%d/%m %H:%M")
        lines.append(f"{TX_ICON.get(t['type'], '•')} {sign}{money(abs(t['amount']))} {cur} — {esc(t['note'])} • {when}")
    return "\n".join(lines)


def profile_text(db, uid):
    u = db["users"].get(str(uid)) or {"name": "-", "username": "", "balance": 0, "refs": 0, "joined": int(time.time())}
    cur = db["settings"]["currency"]
    orders = [o for o in db.get("orders", []) if o["uid"] == str(uid)]
    spent = sum(o["price"] for o in orders if order_status(o) != "refunded")
    return (
        f"👤 <b>আপনার প্রোফাইল</b>\n{LINE}\n"
        f"📛 নাম: <b>{esc(u['name'])}</b>\n"
        f"🔖 ইউজারনেম: @{esc(u.get('username') or '-')}\n"
        f"🆔 আইডি: <code>{uid}</code>\n"
        f"📅 জয়েন: {datetime.fromtimestamp(u['joined'], TZ).strftime('%d/%m/%Y')}\n{LINE}\n"
        f"💰 ব্যালেন্স: <b>{money(u['balance'])} {cur}</b>\n"
        f"🧾 টোটাল অর্ডার: <b>{len(orders)}</b>\n"
        f"📊 টোটাল খরচ: <b>{money(spent)} {cur}</b>\n"
        f"👥 মোট রেফার: <b>{u['refs']}</b> জন"
    )


# ---------- এড মানি ----------
async def show_addmoney(msg, db, text, photo=None, ikb=None):
    cur = db["settings"]["currency"]
    ms = [x for x in db["pay_methods"] if x.get("number")]
    if not ms:
        await tell(msg, "😕 এই মুহূর্তে এড মানি চালু নেই। পরে আবার চেষ্টা করুন।", ikb)
        return
    rows = [[B(node_label(db, x)[:60], "amm:" + x["id"], style=x.get("style"), icon=node_cid(db, x))] for x in ms]
    if ikb is not None:
        rows.extend(ikb.inline_keyboard)
    await tell(msg, text + f"\n\n💳 ন্যূনতম এড মানি: <b>{money(db['settings']['min_add'])} {cur}</b>", KB(rows), photo)


@user.callback_query(F.data.startswith("amm:"))
async def am_pick(c: CallbackQuery, state: FSMContext):
    db = load()
    mt = next((x for x in db["pay_methods"] if x["id"] == c.data[4:]), None)
    if not mt or not mt.get("number"):
        await c.answer("❌ মাধ্যমটি পাওয়া যায়নি", show_alert=True)
        return
    ensure_user(db, c.from_user)
    cur = db["settings"]["currency"]
    await state.clear()
    await state.update_data(mid=mt["id"])
    await state.set_state(AddMoney.amount)
    await c.answer()
    await tell_flow(
        c.message,
        db,
        f"🏦 <b>{pm_text(db, mt)}</b>\n{LINE}\n💰 কত {cur} এড করতে চান? পরিমাণ লিখুন "
        f"(ন্যূনতম {money(db['settings']['min_add'])} {cur}):",
    )


@user.message(AddMoney.amount, F.text)
async def am_amount(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    cur = db["settings"]["currency"]
    minimum = float(db["settings"]["min_add"])
    v = parse_num(m.text)
    if v is None or v <= 0:
        await m.answer("❌ সঠিক সংখ্যা লিখুন (বাতিল: /cancel):")
        return
    if v < minimum:
        await m.answer(f"❌ ন্যূনতম {money(minimum)} {cur} এড করতে হবে। আবার লিখুন:")
        return
    mid = (await state.get_data()).get("mid")
    mt = next((x for x in db["pay_methods"] if x["id"] == mid), None)
    if not mt or not mt.get("number"):
        await state.clear()
        await tell(m, "❌ মাধ্যমটি এখন চালু নেই", main_kb(db))
        return
    await state.update_data(amount=v)
    await state.set_state(AddMoney.trx)
    await tell_flow(
        m,
        db,
        f"🏦 <b>{pm_text(db, mt)}</b>\n{LINE}\n"
        f"📮 নাম্বার: <code>{esc(mt['number'])}</code>\n"
        f"💸 পরিমাণ: <b>{money(v)} {cur}</b>\n"
        f"📝 {esc(mt.get('note') or '')}\n{LINE}\n"
        f"✅ উপরের নাম্বারে ঠিক <b>{money(v)} {cur}</b> পাঠান, তারপর <b>Transaction ID (TrxID)</b> লিখে পাঠান:",
    )


@user.message(AddMoney.trx, F.text)
async def am_trx(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    trx = m.text.strip()
    if len(trx) < 4 or len(trx) > 40:
        await m.answer("❌ সঠিক Transaction ID লিখুন (বাতিল: /cancel):")
        return
    if any(r["trx"].lower() == trx.lower() and r["status"] in ("pending", "approved") for r in db["addreqs"].values()):
        await m.answer("⚠️ এই Transaction ID আগেই জমা দেওয়া হয়েছে। সঠিক ID দিন:")
        return
    uid = str(m.from_user.id)
    if sum(1 for r in db["addreqs"].values() if r["uid"] == uid and r["status"] == "pending") >= 5:
        await state.clear()
        await tell(m, "⚠️ আপনার ৫টি রিকোয়েস্ট পেন্ডিং আছে। অ্যাডমিন যাচাই করা পর্যন্ত অপেক্ষা করুন।", main_kb(db))
        return
    d = await state.get_data()
    mt = next((x for x in db["pay_methods"] if x["id"] == d.get("mid")), None)
    ensure_user(db, m.from_user)
    cur = db["settings"]["currency"]
    rid = new_id()
    r = {
        "id": rid,
        "uid": uid,
        "method": mt["text"] if mt else "?",
        "amount": float(d["amount"]),
        "trx": trx,
        "status": "pending",
        "time": int(time.time()),
    }
    db["addreqs"][rid] = r
    save(db)
    await state.clear()
    await notify_admins(m.bot, addreq_text(db, r), approve_kb("amr", rid))
    await tell(
        m,
        f"⏳ <b>আপনার এড মানি রিকোয়েস্ট জমা হয়েছে</b>\n{LINE}\n"
        f"💸 পরিমাণ: <b>{money(r['amount'])} {cur}</b>\n🧾 TrxID: <code>{esc(trx)}</code>\n"
        "🕐 অ্যাডমিন যাচাই করে এপ্রুভ করলেই ব্যালেন্সে টাকা যোগ হবে।",
        main_kb(db),
    )


@user.message(AddMoney.trx)
@user.message(AddMoney.amount)
async def am_other(m: Message):
    await m.answer("✍️ লেখা পাঠান (বাতিল: /cancel)")


# ---------- রিফান্ড ----------
async def show_refund(msg, db, uid, text, ikb=None):
    cur = db["settings"]["currency"]
    pend = {r["oid"] for r in db["refunds"].values() if r["status"] == "pending"}
    mine = [o for o in db.get("orders", []) if o["uid"] == str(uid) and order_status(o) != "refunded" and o["id"] not in pend][-10:]
    if not mine:
        await tell(msg, text + "\n\n📭 রিফান্ড চাওয়ার মতো কোনো অর্ডার নেই", ikb)
        return
    rows = [[B(f"#{o['id']} • {o['name']} • {money(o['price'])}{cur}"[:60], "rfo:" + o["id"])] for o in reversed(mine)]
    if ikb is not None:
        rows.extend(ikb.inline_keyboard)
    await tell(msg, text + "\n\n👇 যে অর্ডারের রিফান্ড চান সেটি বেছে নিন:", KB(rows))


@user.callback_query(F.data.startswith("rfo:"))
async def refund_pick(c: CallbackQuery, state: FSMContext):
    db = load()
    o = find_order(db, c.data[4:])
    if not o or o["uid"] != str(c.from_user.id) or order_status(o) == "refunded":
        await c.answer("❌ অর্ডার পাওয়া যায়নি", show_alert=True)
        return
    if any(r["oid"] == o["id"] and r["status"] == "pending" for r in db["refunds"].values()):
        await c.answer("⏳ এই অর্ডারের রিফান্ড রিকোয়েস্ট আগেই জমা আছে", show_alert=True)
        return
    await state.clear()
    await state.update_data(oid=o["id"])
    await state.set_state(RefundReq.reason)
    await c.answer()
    await tell_flow(c.message, db, f"♻️ <b>{esc(o['name'])}</b> (#{o['id']})\n✍️ রিফান্ড চাওয়ার কারণ লিখুন:")


@user.message(RefundReq.reason, F.text)
async def refund_reason(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    oid = (await state.get_data()).get("oid", "")
    o = find_order(db, oid)
    await state.clear()
    if not o or o["uid"] != str(m.from_user.id) or order_status(o) == "refunded":
        await tell(m, "❌ অর্ডার পাওয়া যায়নি", main_kb(db))
        return
    rid = new_id()
    r = {"id": rid, "uid": str(m.from_user.id), "oid": oid, "reason": m.text.strip()[:500], "status": "pending", "time": int(time.time())}
    db["refunds"][rid] = r
    save(db)
    await notify_admins(m.bot, refund_text(db, r), approve_kb("rfa", rid))
    await tell(m, "⏳ <b>রিফান্ড রিকোয়েস্ট জমা হয়েছে।</b>\nঅ্যাডমিন যাচাই করে জানিয়ে দেবেন।", main_kb(db))


# ---------- সাপোর্টে মেসেজ ----------
@user.message(TicketMsg.msg)
async def ticket_got(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    u, _ = ensure_user(db, m.from_user)
    await state.clear()
    body = esc((m.text or m.caption or "[ফাইল/ছবি]")[:3000])
    await notify_admins(
        m.bot,
        f"🆘 <b>নতুন সাপোর্ট মেসেজ</b>\n"
        f"👤 {esc(u['name'])} (@{esc(u.get('username') or '-')})\n"
        f"🆔 <code>{m.from_user.id}</code>\n\n💬 {body}",
        KB([[B("↩️ রিপ্লাই দিন", f"tkr:{m.from_user.id}", style="success")]]),
    )
    if not m.text:
        for aid in admin_ids(db):
            try:
                await m.copy_to(aid)
            except Exception:
                pass
    await tell(m, "✅ আপনার মেসেজ সাপোর্টে পাঠানো হয়েছে। শীঘ্রই উত্তর পাবেন।", main_kb(db))


# ============================== 🔘 বাটন টাস্ক (ইউজার) ==============================
async def begin_steps(msg, state: FSMContext, db, t, uid):
    """বাটন চাপলেই সরাসরি ধাপে ধাপে মেসেজ নেওয়া শুরু করে"""
    if not t or not t.get("active"):
        await tell(msg, "❌ এই টাস্ক এখন চালু নেই")
        return
    if task_taken(db, str(uid), t["id"]):
        await tell(msg, "⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন")
        return
    await state.clear()
    await state.set_state(UserTask.answering)
    await state.update_data(tid=t["id"], idx=0, answers=[])
    if db["settings"].get("cancel_on", True):
        await tell(msg, "✍️ একে একে উত্তর দিন। বাতিল করতে নিচের বাটন চাপুন 👇", cancel_kb())
    await send_step(msg, db, t, 0)


@user.callback_query(F.data.startswith("ubt:"))
async def btn_task_press(c: CallbackQuery, state: FSMContext):
    db = load()
    t = db["tasks"].get(c.data[4:])
    u, is_new = ensure_user(db, c.from_user)
    if is_new:
        save(db)
    if not t or not t.get("active"):
        await c.answer("❌ টাস্ক পাওয়া যায়নি", show_alert=True)
        return
    if task_taken(db, str(c.from_user.id), t["id"]):
        await c.answer("⚠️ আপনি এই টাস্ক আগেই জমা দিয়েছেন", show_alert=True)
        return
    await c.answer()
    await begin_steps(c.message, state, db, t, c.from_user.id)


# ============================== 🤖 মাল্টি-বট (এড / আমার / ডিলিট) ==============================
def my_bots(db, uid):
    return [b for b in db["bots"].values() if int(b["owner"]) == int(uid)]


def bot_running(key):
    r = RUNNING.get(key)
    return bool(r and not r["task"].done())


def new_bot_obj(token):
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def make_ctx(rec):
    return BotCtx(rec["id"], os.path.join(BOTS_DIR, rec["id"] + ".json"), int(rec["owner"]), rec["token"], False, rec.get("username", ""))


async def handle_update(bot, ctx, upd):
    CUR_BOT.set(ctx)  # এই আপডেটের সব load()/save() এই বটের ডাটায় যাবে
    try:
        await DP.feed_update(bot, upd)
    except Exception:
        logging.exception("আপডেট হ্যান্ডেল করা যায়নি (%s)", ctx.key)


async def poll_loop(bot, ctx):
    CUR_BOT.set(ctx)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        logging.exception("webhook মুছা যায়নি (%s)", ctx.key)
    used = DP.resolve_used_update_types()
    offset = None
    live = set()
    try:
        while True:
            try:
                updates = await bot.get_updates(offset=offset, timeout=30, allowed_updates=used)
            except asyncio.CancelledError:
                raise
            except TelegramUnauthorizedError:
                logging.error("বট '%s' এর টোকেন বাতিল/ভুল, পোলিং বন্ধ", ctx.key)
                return
            except Exception as e:
                logging.warning("get_updates ব্যর্থ (%s): %s", ctx.key, e)
                await asyncio.sleep(3)
                continue
            for upd in updates:
                offset = upd.update_id + 1
                t = asyncio.create_task(handle_update(bot, ctx, upd))
                live.add(t)
                t.add_done_callback(live.discard)
    finally:
        for t in list(live):
            t.cancel()


def start_clone(bot, rec):
    ctx = make_ctx(rec)
    RUNNING[rec["id"]] = {"task": asyncio.create_task(poll_loop(bot, ctx)), "bot": bot}


async def stop_clone(key):
    r = RUNNING.pop(key, None)
    if r:
        r["task"].cancel()
        try:
            await r["task"]
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await r["bot"].session.close()
        except Exception:
            pass
    _DBS.pop(key, None)


async def bot_buttons(m: Message, state: FSMContext, db):
    t, uid = m.text, m.from_user.id
    if t == BTN_ADD_BOT:
        await state.set_state(BotAdd.name)
        await tell_flow(m, db, f"🤖 <b>নতুন বট যোগ করুন</b>\n{LINE}\n✍️ আপনার বটের নাম লিখুন:")
        return
    mine = my_bots(db, uid)
    if t == BTN_MY_BOTS:
        if not mine:
            await tell(m, f"📭 আপনার কোনো বট নেই।\n{BTN_ADD_BOT} চেপে নতুন বট যোগ করুন।", main_kb(db))
            return
        lines = ["🤖 <b>আপনার বটসমূহ</b>", LINE]
        rows = []
        for i, b in enumerate(mine, 1):
            st = "🟢 চালু" if bot_running(b["id"]) else "🔴 বন্ধ"
            lines.append(f"{i}. <b>{esc(b['name'])}</b> — @{esc(b['username'])}\n    {st}")
            rows.append([B(f"🤖 @{b['username']}"[:60], url=f"https://t.me/{b['username']}")])
        await tell(m, "\n".join(lines), KB(rows))
        return
    if t == BTN_DEL_BOT:
        if not mine:
            await tell(m, "📭 ডিলিট করার মতো কোনো বট নেই।", main_kb(db))
            return
        rows = [[B(f"🗑 {b['name']} (@{b['username']})"[:60], "bdel:" + b["id"], style="danger")] for b in mine]
        await tell(m, "🗑 <b>কোন বটটি ডিলিট করবেন?</b>\n👇 বেছে নিন:", KB(rows))


@user.message(BotAdd.name, F.text)
async def bot_add_name(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    name = m.text.strip()
    if len(name) < 2 or len(name) > 40:
        await m.answer("❌ নাম ২ থেকে ৪০ অক্ষরের মধ্যে হতে হবে। আবার লিখুন (বাতিল: /cancel):")
        return
    await state.update_data(bname=name)
    await state.set_state(BotAdd.token)
    await tell_flow(
        m,
        db,
        f"🤖 বটের নাম: <b>{esc(name)}</b>\n{LINE}\n🔑 এবার বটের <b>টোকেন</b> দিন (@BotFather থেকে পাওয়া):",
    )


@user.message(BotAdd.token, F.text)
async def bot_add_token(m: Message, state: FSMContext):
    db = load()
    if await nav(m, state, db):
        return
    token = m.text.strip()
    try:
        await m.delete()  # টোকেন গোপন রাখতে ইউজারের মেসেজ মুছে দেওয়া হয়
    except Exception:
        pass
    if not TOKEN_RE.match(token):
        await m.answer("❌ টোকেনটি সঠিক ফরম্যাটে নেই। @BotFather থেকে পাওয়া পুরো টোকেন দিন (বাতিল: /cancel):")
        return
    if token == MAIN_CTX.token or any(b["token"] == token for b in db["bots"].values()):
        await m.answer("⚠️ এই টোকেনের বট আগেই যোগ করা আছে। অন্য টোকেন দিন (বাতিল: /cancel):")
        return
    name = (await state.get_data()).get("bname", "Bot")
    nb = new_bot_obj(token)
    try:
        me = await nb.get_me()
    except Exception:
        try:
            await nb.session.close()
        except Exception:
            pass
        await m.answer("❌ টোকেনটি কাজ করছে না। সঠিক টোকেন দিন (বাতিল: /cancel):")
        return
    key = "b" + new_id()
    rec = {
        "id": key,
        "name": name,
        "token": token,
        "username": me.username or "",
        "owner": m.from_user.id,
        "created": int(time.time()),
    }
    # নতুন বটের নিজস্ব ডাটা ফাইল (ডিফল্ট ফিচারসহ), Owner = যে যোগ করেছে
    d = default_db()
    d["settings"]["bot_name"] = name
    os.makedirs(BOTS_DIR, exist_ok=True)
    with open(os.path.join(BOTS_DIR, key + ".json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    db["bots"][key] = rec
    save(db)
    start_clone(nb, rec)
    await state.clear()
    await tell(
        m,
        f"✅ <b>বট যোগ হয়েছে!</b>\n{LINE}\n🤖 নাম: <b>{esc(name)}</b>\n🔗 @{esc(rec['username'])}\n{LINE}\n"
        "⚙️ আপনি এই বটের অ্যাডমিন। বটে গিয়ে /start দিন, তারপর /admin লিখে প্যানেল খুলুন।",
        KB([[B("🤖 বট খুলুন", url=f"https://t.me/{rec['username']}", style="success")]]),
    )
    await tell(m, "🏠 মেইন মেনু", main_kb(db))


@user.message(BotAdd.name)
@user.message(BotAdd.token)
async def bot_add_other(m: Message):
    await m.answer("✍️ লেখা পাঠান (বাতিল: /cancel)")


@user.callback_query(F.data.startswith("bdel:"))
async def bot_del_ask(c: CallbackQuery):
    db = load()
    b = db["bots"].get(c.data[5:])
    if not b or int(b["owner"]) != c.from_user.id:
        await c.answer("❌ বট পাওয়া যায়নি", show_alert=True)
        return
    await c.answer()
    await tell(
        c.message,
        f"⚠️ <b>{esc(b['name'])}</b> (@{esc(b['username'])}) ডিলিট করলে বটটি বন্ধ হয়ে যাবে এবং তার ইউজার/ব্যালেন্স সহ সব ডাটা সরে যাবে।\n\nনিশ্চিত?",
        KB([[B("✅ হ্যাঁ, ডিলিট করুন", "bdy:" + b["id"], style="danger"), B("↩️ না", "bdn")]]),
    )


@user.callback_query(F.data == "bdn")
async def bot_del_no(c: CallbackQuery):
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.answer("বাতিল")


@user.callback_query(F.data.startswith("bdy:"))
async def bot_del_yes(c: CallbackQuery):
    db = load()
    key = c.data[4:]
    b = db["bots"].get(key)
    if not b or int(b["owner"]) != c.from_user.id:
        await c.answer("❌ বট পাওয়া যায়নি", show_alert=True)
        return
    await stop_clone(key)
    del db["bots"][key]
    save(db)
    path = os.path.join(BOTS_DIR, key + ".json")
    if os.path.exists(path):
        try:
            os.replace(path, path + ".deleted")  # নিরাপত্তার জন্য ব্যাকআপ রাখা হয়
        except Exception:
            pass
    await c.answer("✅ ডিলিট হয়েছে")
    await tell(c.message, f"🗑 <b>{esc(b['name'])}</b> ডিলিট হয়েছে।", main_kb(db))


# ============================== চালু ==============================
async def main():
    global BOT_USERNAME, DP
    load()
    bot = new_bot_obj(BOT_TOKEN)
    BOT_USERNAME = (await bot.get_me()).username
    MAIN_CTX.username = BOT_USERNAME
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin)
    dp.include_router(user)
    DP = dp
    os.makedirs(BOTS_DIR, exist_ok=True)
    for rec in list(load()["bots"].values()):  # আগে যোগ করা সব বট আবার চালু
        try:
            start_clone(new_bot_obj(rec["token"]), rec)
        except Exception:
            logging.exception("বট চালু করা যায়নি: %s", rec.get("id"))
    try:
        await poll_loop(bot, MAIN_CTX)
    finally:
        for key in list(RUNNING):
            await stop_clone(key)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
