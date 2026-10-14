#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║        TELEGRAM BOT HOSTING PLATFORM  —  bot.py              ║
║        python-telegram-bot v20+ (async)                      ║
╚══════════════════════════════════════════════════════════════╝

Run:
    pip install -U "python-telegram-bot>=21.7"
    export BOT_TOKEN="123456:ABC..."      # অথবা নিচে BOT_TOKEN এ বসাও
    python bot.py

Folders (auto-created):
    bots/       -> ইউজারদের বট কোড   (bots/{user_id}_{bot_name}.py)
    templates/  -> বট মার্কেটের কোড
    logs/       -> প্রতিটি বটের লগ
    data.json   -> সব ডাটা
"""

import ast
import asyncio
import copy
import html
import importlib.util
import json
import logging
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Bot,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:  # tap-to-copy button (PTB >= 21.7)
    from telegram import CopyTextButton
except ImportError:  # pragma: no cover
    CopyTextButton = None

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN") or "PUT_YOUR_PLATFORM_BOT_TOKEN_HERE"
ADMIN_ID = 8933985337

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
BOTS_DIR = BASE_DIR / "bots"
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"
TMP_DIR = BASE_DIR / "tmp"

PYTHON_BIN = "python3" if shutil.which("python3") else sys.executable
MAX_CODE_BYTES = 2 * 1024 * 1024  # 2 MB
MONITOR_INTERVAL = 10  # seconds

# ইউজারের কোড এই env variable গুলো থেকে টোকেন পড়তে পারবে
TOKEN_ENV_NAMES = ("BOT_TOKEN", "TOKEN", "API_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN")

# কোডে import দেখে অটো-ইনস্টল করার জন্য (শুধু এই লিস্টের প্যাকেজ)
PIP_MAP = {
    "telegram": "python-telegram-bot",
    "aiogram": "aiogram",
    "pyrogram": "pyrogram tgcrypto",
    "telebot": "pyTelegramBotAPI",
    "telethon": "telethon",
    "requests": "requests",
    "aiohttp": "aiohttp",
    "httpx": "httpx",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "PIL": "pillow",
    "yt_dlp": "yt-dlp",
    "aiofiles": "aiofiles",
    "aiosqlite": "aiosqlite",
    "apscheduler": "apscheduler",
    "pytz": "pytz",
    "flask": "flask",
    "pymongo": "pymongo",
    "motor": "motor",
    "psutil": "psutil",
    "openai": "openai",
    "qrcode": "qrcode[pil]",
}

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
TOKEN_FIND_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")

LINE = "━━━━━━━━━━━━━━━━━━"

# যে স্টেটগুলোতে কোড (ফাইল অথবা লেখা মেসেজ) গ্রহণ করা হয়
CODE_STATES = ("upload_code", "edit_code", "adm_tpl_file", "adm_tpl_edit")
ADMIN_CODE_STATES = ("adm_tpl_file", "adm_tpl_edit")

# Reply keyboard labels
BTN_ADD = "➕ এড বট"
BTN_MARKET = "🛒 বট মার্কেট"
BTN_WALLET = "💰 ওয়ালেট"
BTN_ADDMONEY = "💳 এড মানি"
BTN_SUPPORT = "📞 সাপোর্ট"
BTN_ADMIN = "👑 এডমিন প্যানেল"
MENU_LABELS = {BTN_ADD, BTN_MARKET, BTN_WALLET, BTN_ADDMONEY, BTN_SUPPORT, BTN_ADMIN}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("hosting")

# ═══════════════════════════════════════════════════════════════
#  DATABASE (data.json)
# ═══════════════════════════════════════════════════════════════
DEFAULT_DATA = {
    "users": {},            # uid -> {id,name,username,balance,joined}
    "bots": {},             # bid -> {owner,name,file,token,status,source,template,pid,created}
    "templates": {},        # tid -> {name,price,desc,file,created}
    "payment_codes": {},    # code -> {uid,status,amount,trx,created,...}
    "payment_numbers": [],  # [{id,method,number}]
    "channel_lock": [],     # ["@channel"]
    "settings": {"global_price": 50, "support": "@support"},
    "counters": {"bot": 0, "tpl": 0, "pay": 0},
}


def load_data() -> dict:
    data = None
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            shutil.copy(DATA_FILE, DATA_FILE.with_suffix(f".broken.{int(time.time())}"))
            log.error("data.json corrupted — backup created, starting fresh")
    if not isinstance(data, dict):
        data = {}
    for k, v in DEFAULT_DATA.items():
        data.setdefault(k, copy.deepcopy(v))
    for k, v in DEFAULT_DATA["settings"].items():
        data["settings"].setdefault(k, v)
    for k, v in DEFAULT_DATA["counters"].items():
        data["counters"].setdefault(k, v)

    # ── পুরনো/ভিন্ন ফরম্যাটের data.json ঠিক করা (KeyError: 'balance' ফিক্স) ──
    for key, default in (("users", {}), ("bots", {}), ("templates", {}), ("payment_codes", {})):
        if not isinstance(data.get(key), dict):
            data[key] = copy.deepcopy(default)
    for key in ("payment_numbers", "channel_lock"):
        if not isinstance(data.get(key), list):
            data[key] = []

    for uid, u in list(data["users"].items()):
        if not isinstance(u, dict):
            u = {}
            data["users"][uid] = u
        u.setdefault("id", int(uid) if str(uid).isdigit() else 0)
        u.setdefault("name", "User")
        u.setdefault("username", None)
        try:
            u["balance"] = float(u.get("balance") or 0)
        except (TypeError, ValueError):
            u["balance"] = 0.0
        u.setdefault("joined", int(time.time()))

    for bid, b in list(data["bots"].items()):
        if not isinstance(b, dict):
            data["bots"].pop(bid, None)
            continue
        b.setdefault("owner", 0)
        b.setdefault("name", bid)
        b.setdefault("file", "")
        b.setdefault("token", "")
        b.setdefault("status", "stopped")
        b.setdefault("source", "custom")
        b.setdefault("template", None)
        b.setdefault("username", None)
        b.setdefault("pid", None)
        b.setdefault("created", int(time.time()))
    return data


DB = load_data()


def save_data() -> None:
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(DB, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def now() -> int:
    return int(time.time())


def esc(s) -> str:
    return html.escape(str(s))


def money(x) -> str:
    s = f"{float(x):,.2f}".rstrip("0").rstrip(".")
    return f"৳{s}"


def parse_num(text: str):
    try:
        v = float(text.translate(BN_DIGITS).replace(",", "").replace("৳", "").strip())
        return v if v >= 0 else None
    except Exception:
        return None


def next_id(kind: str, prefix: str) -> str:
    DB["counters"][kind] += 1
    save_data()
    return f"{prefix}{DB['counters'][kind]}"


def get_user(tg_user) -> dict:
    uid = str(tg_user.id)
    u = DB["users"].get(uid)
    if not u:
        u = {
            "id": tg_user.id,
            "name": tg_user.full_name,
            "username": tg_user.username,
            "balance": 0.0,
            "joined": now(),
        }
        DB["users"][uid] = u
        save_data()
    else:
        changed = False
        for k, v in (("id", tg_user.id), ("balance", 0.0), ("joined", now())):
            if k not in u:
                u[k] = v
                changed = True
        if u.get("name") != tg_user.full_name or u.get("username") != tg_user.username:
            u["name"], u["username"] = tg_user.full_name, tg_user.username
            changed = True
        if changed:
            save_data()
    return u


def user_bots(uid: int):
    return [(bid, b) for bid, b in DB["bots"].items() if b["owner"] == uid]


def ib(text, cb=None, url=None, style=None, copy_text=None):
    """InlineKeyboardButton helper — style: primary(নীল) / success(সবুজ) / danger(লাল)."""
    extra = {"api_kwargs": {"style": style}} if style else {}
    if copy_text is not None:
        if CopyTextButton is None:
            return None
        return InlineKeyboardButton(text, copy_text=CopyTextButton(text=str(copy_text)[:256]), **extra)
    if url:
        return InlineKeyboardButton(text, url=url, **extra)
    return InlineKeyboardButton(text, callback_data=cb, **extra)


def kb(*rows) -> InlineKeyboardMarkup:
    out = []
    for r in rows:
        r = [b for b in r if b is not None]
        if r:
            out.append(r)
    return InlineKeyboardMarkup(out)


CANCEL_KB = kb([ib("❌ বাতিল করুন", cb="cancel", style="danger")])


def main_menu(uid: int) -> ReplyKeyboardMarkup:
    def k(text, style):
        return KeyboardButton(text, api_kwargs={"style": style})

    rows = [
        [k(BTN_ADD, "primary"), k(BTN_MARKET, "success")],
        [k(BTN_WALLET, "success"), k(BTN_ADDMONEY, "primary")],
        [k(BTN_SUPPORT, "danger")],
    ]
    if uid == ADMIN_ID:
        rows.append([KeyboardButton(BTN_ADMIN)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


async def send(update: Update, text: str, markup=None):
    return await update.effective_chat.send_message(
        text, parse_mode=ParseMode.HTML, reply_markup=markup
    )


async def edit(q, text: str, markup=None):
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        await q.message.chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ═══════════════════════════════════════════════════════════════
#  CHANNEL LOCK
# ═══════════════════════════════════════════════════════════════
async def missing_channels(bot, uid: int):
    missing = []
    for ch in DB["channel_lock"]:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ("left", "kicked") or (
                m.status == "restricted" and not getattr(m, "is_member", True)
            ):
                missing.append(ch)
        except TelegramError as e:
            log.warning("Channel check failed for %s: %s", ch, e)
    return missing


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if uid == ADMIN_ID or not DB["channel_lock"]:
        return True
    missing = await missing_channels(context.bot, uid)
    if not missing:
        return True
    rows = [
        [ib(f"🔵 Join Channel {ch}", url=f"https://t.me/{ch.lstrip('@')}", style="primary")]
        for ch in missing
    ]
    rows.append([ib("🟢 Verify", cb="verify", style="success")])
    await send(
        update,
        f"🔒 <b>চ্যানেল জয়েন বাধ্যতামূলক!</b>\n{LINE}\n\n"
        "বটটি ব্যবহার করতে নিচের চ্যানেলে জয়েন করুন, তারপর "
        "<b>🟢 Verify</b> বাটনে ক্লিক করুন।",
        kb(*rows),
    )
    return False


# ═══════════════════════════════════════════════════════════════
#  PROCESS MANAGER (bot hosting)
# ═══════════════════════════════════════════════════════════════
PROCS: dict = {}  # bid -> Popen


def build_env(token: str) -> dict:
    keep = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "VIRTUAL_ENV", "SYSTEMROOT", "TEMP", "TMP")
    }
    for name in TOKEN_ENV_NAMES:
        keep[name] = token
    keep["PYTHONUNBUFFERED"] = "1"
    return keep


def start_bot_process(bid: str) -> bool:
    b = DB["bots"][bid]
    proc = PROCS.get(bid)
    if proc and proc.poll() is None:
        return True
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / f"{bid}.log"
    if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
        log_path.unlink()
    try:
        logf = open(log_path, "ab")
        logf.write(f"\n===== START {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n".encode())
        logf.flush()
        proc = subprocess.Popen(
            [PYTHON_BIN, str(Path(b["file"]).resolve())],
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=str(BOTS_DIR),
            env=build_env(b["token"]),
            start_new_session=(os.name == "posix"),
        )
    except Exception as e:
        log.error("Failed to start %s: %s", bid, e)
        b["status"], b["pid"] = "stopped", None
        save_data()
        return False
    PROCS[bid] = proc
    b["status"], b["pid"] = "running", proc.pid
    save_data()
    return True


def _kill_proc(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass
    except Exception:
        pass


async def stop_bot_process(bid: str) -> None:
    proc = PROCS.pop(bid, None)
    if proc and proc.poll() is None:
        await asyncio.to_thread(_kill_proc, proc)
    b = DB["bots"].get(bid)
    if b:
        b["status"], b["pid"] = "stopped", None
        save_data()


def tail_log(bid: str, limit: int = 3000) -> str:
    p = LOGS_DIR / f"{bid}.log"
    if not p.exists():
        return ""
    data = p.read_bytes()[-limit:]
    return data.decode("utf-8", errors="replace")


# import নাম ≠ pip প্যাকেজ নাম — এমন কমন কেসগুলো (লিস্টে না থাকলে import নামই pip নাম ধরা হয়)
PIP_ALIASES = {
    "cv2": "opencv-python-headless",
    "yaml": "pyyaml",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodomex",
    "jwt": "pyjwt",
    "dateutil": "python-dateutil",
    "serial": "pyserial",
    "OpenSSL": "pyopenssl",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "fitz": "pymupdf",
    "PyPDF2": "pypdf2",
    "git": "gitpython",
    "bson": "pymongo",
    "gridfs": "pymongo",
    "telegram": "python-telegram-bot",
    "telebot": "pyTelegramBotAPI",
    "discord": "discord.py",
    "socks": "pysocks",
    "nacl": "pynacl",
    "google": "google-api-python-client",
    "attr": "attrs",
    "multipart": "python-multipart",
    "ddtrace": "ddtrace",
    "win32api": "pywin32",
    "usb": "pyusb",
    "zmq": "pyzmq",
    "lxml": "lxml",
    "Image": "pillow",
}

try:
    _STDLIB = set(sys.stdlib_module_names) | set(sys.builtin_module_names)  # Python 3.10+
except AttributeError:  # pragma: no cover
    import sysconfig

    _std = Path(sysconfig.get_paths()["stdlib"])
    _STDLIB = set(sys.builtin_module_names) | {
        p.stem for p in _std.iterdir() if p.suffix == ".py" or p.is_dir()
    }
_STDLIB |= {"__future__", "typing_extensions_builtin"}


def _missing_packages(path: Path):
    """কোডের সব থার্ড-পার্টি import খুঁজে যেগুলো ইনস্টল নেই সেগুলোর pip নাম রিটার্ন করে।"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods.add(n.module.split(".")[0])
    pkgs = []
    for m in sorted(mods):
        if not m or m in _STDLIB or m.startswith("_"):
            continue
        # ইউজারের নিজের লোকাল ফাইল/ফোল্ডার (bots/ এর ভেতরে) হলে স্কিপ
        if (BOTS_DIR / f"{m}.py").exists() or (BOTS_DIR / m).is_dir():
            continue
        try:
            found = importlib.util.find_spec(m) is not None
        except Exception:
            found = False
        if found:
            continue
        spec = PIP_MAP.get(m) or PIP_ALIASES.get(m) or m
        for p in spec.split():
            if p not in pkgs:
                pkgs.append(p)
    return pkgs


def _pip_run(pkgs) -> bool:
    try:
        r = subprocess.run(
            [PYTHON_BIN, "-m", "pip", "install", "-q", "--disable-pip-version-check", *pkgs],
            timeout=900,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return r.returncode == 0
    except Exception as e:
        log.warning("pip install failed: %s", e)
        return False


def _pip_install(pkgs):
    # আগে সব একসাথে; ফেইল করলে একটা একটা করে, যাতে একটার জন্য বাকিগুলো আটকে না যায়
    if _pip_run(pkgs):
        return
    for p in pkgs:
        if not _pip_run([p]):
            log.warning("Could not install package: %s", p)


async def ensure_deps(path: Path) -> None:
    pkgs = await asyncio.to_thread(_missing_packages, path)
    if pkgs:
        log.info("Installing packages: %s", pkgs)
        await asyncio.to_thread(_pip_install, pkgs)


def patch_token(path: Path, token: str) -> None:
    """কোডে হার্ডকোড করা পুরনো/ডামি টোকেন থাকলে ইউজারের দেওয়া টোকেন দিয়ে বদলে দেয়।"""
    try:
        src = path.read_text(encoding="utf-8")
        new = TOKEN_FIND_RE.sub(lambda m: token, src)
        if new != src:
            path.write_text(new, encoding="utf-8")
    except Exception as e:
        log.warning("patch_token: %s", e)


def _pid_is_ours(pid, file) -> bool:
    try:
        return str(file) in Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="ignore")
    except Exception:
        return False


async def monitor_loop(app: Application):
    while True:
        await asyncio.sleep(MONITOR_INTERVAL)
        for bid, proc in list(PROCS.items()):
            code = proc.poll()
            if code is None:
                continue
            PROCS.pop(bid, None)
            b = DB["bots"].get(bid)
            if not b:
                continue
            b["status"], b["pid"] = ("crashed" if code != 0 else "stopped"), None
            save_data()
            tail = tail_log(bid, 700)
            try:
                await app.bot.send_message(
                    b["owner"],
                    f"⚠️ <b>আপনার বট বন্ধ হয়ে গেছে!</b>\n{LINE}\n\n"
                    f"🤖 <b>Bot:</b> @{esc(b['name'])}\n"
                    f"🔢 <b>Exit Code:</b> <code>{code}</code>\n\n"
                    f"📜 <b>শেষ লগ:</b>\n<pre>{esc(tail[-700:]) or 'No logs'}</pre>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb([ib("⚙️ ম্যানেজ", cb=f"bm:{bid}", style="primary")]),
                )
            except TelegramError:
                pass


# ═══════════════════════════════════════════════════════════════
#  TOKEN / FILE VALIDATION
# ═══════════════════════════════════════════════════════════════
async def validate_token(token: str):
    try:
        async with Bot(token) as b:
            return await b.get_me()
    except Exception:
        return None


async def fetch_code_file(context, uid: int, doc):
    fname = doc.file_name or ""
    if not fname.lower().endswith(".py"):
        return False, "❌ শুধু <b>.py</b> ফাইল গ্রহণযোগ্য।"
    if doc.file_size and doc.file_size > MAX_CODE_BYTES:
        return False, "❌ ফাইল অনেক বড়! সর্বোচ্চ <b>2 MB</b>।"
    TMP_DIR.mkdir(exist_ok=True)
    tmp = TMP_DIR / f"{uid}_{now()}_{random.randint(100, 999)}.py"
    tg_file = await doc.get_file()
    await tg_file.download_to_drive(custom_path=tmp)
    try:
        src = tmp.read_bytes().decode("utf-8-sig")
        compile(src, fname, "exec")
        tmp.write_text(src, encoding="utf-8")
    except UnicodeDecodeError:
        tmp.unlink(missing_ok=True)
        return False, "❌ ফাইল অবশ্যই <b>UTF-8</b> এনকোডিং-এ হতে হবে।"
    except SyntaxError as e:
        tmp.unlink(missing_ok=True)
        return False, f"❌ <b>Syntax Error</b> (line {e.lineno}):\n<code>{esc(e.msg)}</code>"
    return True, tmp


def bot_url(b: dict) -> str:
    """হোস্ট করা বটে সরাসরি যাওয়ার লিংক।"""
    return f"https://t.me/{b.get('username') or b['name']}"


def clean_code_text(text: str) -> str:
    """মেসেজে পেস্ট করা কোড থেকে ```python ... ``` মার্কডাউন ফেন্স সরায়।"""
    t = text.strip()
    m = re.match(r"^```[A-Za-z0-9_+-]*[ \t]*\n(.*?)\n?[ \t]*```$", t, re.S)
    if m:
        t = m.group(1)
    return t.strip("\n") + "\n"


async def code_from_text(uid: int, text: str):
    """লেখা কোড যাচাই করে tmp ফাইলে সেভ করে।"""
    src = clean_code_text(text)
    if len(src.encode("utf-8")) > MAX_CODE_BYTES:
        return False, "❌ কোড অনেক বড়! সর্বোচ্চ <b>2 MB</b>।"
    try:
        compile(src, "code.py", "exec")
    except SyntaxError as e:
        return False, f"❌ <b>Syntax Error</b> (line {e.lineno}):\n<code>{esc(e.msg)}</code>"
    except ValueError as e:
        return False, f"❌ কোড সঠিক নয়: <code>{esc(e)}</code>"
    TMP_DIR.mkdir(exist_ok=True)
    tmp = TMP_DIR / f"{uid}_{now()}_{random.randint(100, 999)}.py"
    tmp.write_text(src, encoding="utf-8")
    return True, tmp


async def deploy_bot(context, update, uid, token, me, src: Path, source, tid=None, price=0.0):
    user = DB["users"][str(uid)]
    if user["balance"] < price:
        return False, "insufficient"
    bot_name = re.sub(r"[^A-Za-z0-9_]", "", me.username or f"bot{me.id}")
    BOTS_DIR.mkdir(exist_ok=True)
    dest = BOTS_DIR / f"{uid}_{bot_name}.py"
    shutil.copyfile(src, dest)
    patch_token(dest, token)
    bid = next_id("bot", "b")
    user["balance"] = round(user["balance"] - price, 2)
    DB["bots"][bid] = {
        "owner": uid,
        "name": bot_name,
        "username": me.username,
        "file": str(dest),
        "token": token,
        "status": "stopped",
        "source": source,
        "template": tid,
        "pid": None,
        "created": now(),
    }
    save_data()
    await ensure_deps(dest)
    ok = start_bot_process(bid)
    if not ok:  # শুরুই করতে না পারলে রিফান্ড
        user["balance"] = round(user["balance"] + price, 2)
        DB["bots"].pop(bid, None)
        save_data()
        return False, "start_failed"
    return True, bid


# ═══════════════════════════════════════════════════════════════
#  USER SCREENS
# ═══════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user)
    context.user_data.pop("state", None)
    if not await gate(update, context):
        return
    await send_welcome(update)


async def send_welcome(update: Update):
    user = update.effective_user
    u = get_user(user)
    await send(
        update,
        f"👋 <b>স্বাগতম, {esc(user.first_name)}!</b>\n\n"
        f"🚀 <b>Premium Telegram Bot Hosting</b>\n{LINE}\n\n"
        f"💰 <b>আপনার ব্যালেন্স:</b> <code>{money(u['balance'])}</code>\n\n"
        "✨ নিজের Python বট ২৪/৭ চালান — aiogram, pyrogram, telebot যেকোনো লাইব্রেরি সাপোর্টেড!\n\n"
        "👇 <b>নিচের মেনু থেকে বেছে নিন</b>",
        main_menu(user.id),
    )


async def show_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(update.effective_user)
    price = DB["settings"]["global_price"]
    if u["balance"] < price:
        await send(
            update,
            f"➕ <b>এড বট</b>\n{LINE}\n\n"
            f"💸 <b>বট হোস্টিং চার্জ:</b> <code>{money(price)}</code>\n"
            f"💰 <b>আপনার ব্যালেন্স:</b> <code>{money(u['balance'])}</code>\n\n"
            "⚠️ <b>ব্যালেন্স যথেষ্ট নয়!</b> আগে <b>💳 এড মানি</b> করুন।",
            kb([ib("💳 এড মানি", cb="am:new", style="primary")]),
        )
        return
    context.user_data["state"] = {"name": "upload_code"}
    await send(
        update,
        f"➕ <b>নতুন বট এড করুন</b>\n{LINE}\n\n"
        f"💸 <b>চার্জ:</b> <code>{money(price)}</code>  |  💰 <b>ব্যালেন্স:</b> <code>{money(u['balance'])}</code>\n\n"
        "📂 <b>ধাপ ১:</b> আপনার বটের কোড দুইভাবে দিতে পারেন:\n\n"
        "1️⃣ <b>.py ফাইল</b> পাঠান (Document হিসেবে)\n"
        "2️⃣ <b>কোড লিখে/পেস্ট করে</b> মেসেজ পাঠান — কোড একাধিক মেসেজে হলে সবগুলো পাঠিয়ে "
        "শেষে <b>✅ কোড সম্পূর্ণ</b> বাটন চাপুন।\n\n"
        "💡 <i>টোকেন কোডে হার্ডকোড থাকলেও সমস্যা নেই, আপনার টোকেন দিয়ে অটো বদলে যাবে। "
        "চাইলে <code>os.getenv('BOT_TOKEN')</code> ও ব্যবহার করতে পারেন।\n"
        "কোড বড় হলে ফাইল পাঠানোই ভালো।</i>",
        CANCEL_KB,
    )


def wallet_text(uid: int) -> str:
    u = DB["users"][str(uid)]
    bots = user_bots(uid)
    active = [b for _, b in bots if b["status"] == "running"]
    stopped = [b for _, b in bots if b["status"] != "running"]
    t = (
        f"💰 <b>আমার ওয়ালেট</b>\n{LINE}\n\n"
        f"💵 <b>বর্তমান ব্যালেন্স:</b> <code>{money(u['balance'])}</code>\n"
        f"🤖 <b>মোট বট:</b> <code>{len(bots)}</code>\n"
        f"🟢 <b>Active:</b> <code>{len(active)}</code>   🔴 <b>Stopped:</b> <code>{len(stopped)}</code>\n"
    )
    if active:
        t += "\n🟢 <b>চালু বট:</b>\n" + "\n".join(f"   ▫️ @{esc(b['name'])}" for b in active) + "\n"
    if stopped:
        t += "\n🔴 <b>বন্ধ বট:</b>\n" + "\n".join(f"   ▫️ @{esc(b['name'])}" for b in stopped) + "\n"
    if not bots:
        t += "\n📭 <i>আপনার কোনো বট নেই।</i>\n"
    else:
        t += "\n👇 <i>ম্যানেজ করতে বটে ক্লিক করুন</i>"
    return t


def wallet_markup(uid: int):
    btns = [
        ib(("🟢 " if b["status"] == "running" else "🔴 ") + f"@{b['name']}", cb=f"bm:{bid}")
        for bid, b in user_bots(uid)
    ]
    rows = [btns[i : i + 2] for i in range(0, len(btns), 2)]
    rows.append([ib("➕ এড বট", cb="addbot", style="primary"), ib("💳 এড মানি", cb="am:new", style="success")])
    return kb(*rows)


async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user)
    uid = update.effective_user.id
    await send(update, wallet_text(uid), wallet_markup(uid))


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (DB["settings"].get("support") or "").strip()
    url = None
    if s.startswith("@"):
        url = f"https://t.me/{s[1:]}"
    elif s.startswith("http"):
        url = s
    elif s.startswith("t.me"):
        url = "https://" + s
    text = f"📞 <b>সাপোর্ট</b>\n{LINE}\n\n"
    text += f"💬 যেকোনো সমস্যায় যোগাযোগ করুন:\n👉 <b>{esc(s)}</b>" if s else "⚠️ সাপোর্ট এখনো সেট করা হয়নি।"
    await send(update, text, kb([ib("💬 সাপোর্টে যোগাযোগ", url=url, style="danger")]) if url else None)


# ───────────────────────── Bot management ─────────────────────────
STATUS_TXT = {"running": "🟢 Active", "stopped": "🔴 Stopped", "crashed": "🟠 Crashed"}


def bot_view(bid: str):
    b = DB["bots"][bid]
    running = b["status"] == "running"
    src = "🛒 Market" if b["source"] == "market" else "📂 Custom Code"
    text = (
        f"🤖 <b>@{esc(b['name'])}</b>\n{LINE}\n\n"
        f"📊 <b>Status:</b> {STATUS_TXT.get(b['status'], b['status'])}\n"
        f"📦 <b>Source:</b> {src}\n"
        f"🕒 <b>Created:</b> <code>{time.strftime('%Y-%m-%d %H:%M', time.localtime(b['created']))}</code>\n"
        f"🆔 <b>PID:</b> <code>{b.get('pid') or '-'}</code>"
    )
    markup = kb(
        [ib("🔗 বট ওপেন করুন", url=bot_url(b), style="success")] if running else [],
        [
            ib("⏹ Stop", cb=f"ba:stop:{bid}", style="danger")
            if running
            else ib("▶️ Start", cb=f"ba:start:{bid}", style="success"),
            ib("🔄 Restart", cb=f"ba:restart:{bid}", style="primary"),
        ],
        [ib("📜 Logs", cb=f"ba:logs:{bid}"), ib("✏️ Edit Code", cb=f"ba:edit:{bid}")],
        [ib("🗑 Delete", cb=f"ba:delask:{bid}", style="danger")],
        [ib("⬅️ Back", cb="wallet")],
    )
    return text, markup


async def bot_action(update, context, q, uid, action, bid):
    b = DB["bots"].get(bid)
    if not b or (b["owner"] != uid and uid != ADMIN_ID):
        await q.answer("❌ বট পাওয়া যায়নি", show_alert=True)
        return
    if action == "start":
        await q.answer("⏳ চালু করা হচ্ছে...")
        await ensure_deps(Path(b["file"]))
        if not start_bot_process(bid):
            await q.answer("❌ চালু করা যায়নি", show_alert=True)
    elif action == "stop":
        await stop_bot_process(bid)
        await q.answer("⏹ বন্ধ করা হয়েছে")
    elif action == "restart":
        await q.answer("🔄 রিস্টার্ট হচ্ছে...")
        await stop_bot_process(bid)
        await ensure_deps(Path(b["file"]))
        start_bot_process(bid)
    elif action == "logs":
        await q.answer()
        t = tail_log(bid, 3000)
        await q.message.chat.send_message(
            f"📜 <b>Logs — @{esc(b['name'])}</b>\n<pre>{esc(t[-3300:]) or 'কোনো লগ নেই'}</pre>",
            parse_mode=ParseMode.HTML,
        )
        return
    elif action == "edit":
        await q.answer()
        context.user_data["state"] = {"name": "edit_code", "bid": bid}
        await q.message.chat.send_message(
            f"✏️ <b>কোড এডিট — @{esc(b['name'])}</b>\n{LINE}\n\n"
            "📂 নতুন কোড <b>.py ফাইল</b> হিসেবে পাঠান, অথবা <b>কোড লিখে/পেস্ট করে</b> মেসেজ পাঠান "
            "(শেষে <b>✅ কোড সম্পূর্ণ</b> চাপুন)। পুরনো কোড রিপ্লেস হয়ে বট অটো রিস্টার্ট হবে।\n"
            "💸 <i>এডিট সম্পূর্ণ ফ্রি।</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=CANCEL_KB,
        )
        return
    elif action == "delask":
        await q.answer()
        await edit(
            q,
            f"🗑 <b>@{esc(b['name'])}</b> মুছে ফেলবেন?\n\n⚠️ <i>এটি আর ফেরত আনা যাবে না এবং টাকা রিফান্ড হবে না।</i>",
            kb([ib("✅ হ্যাঁ, মুছুন", cb=f"ba:del:{bid}", style="danger"), ib("❌ না", cb=f"bm:{bid}", style="success")]),
        )
        return
    elif action == "del":
        await stop_bot_process(bid)
        Path(b["file"]).unlink(missing_ok=True)
        (LOGS_DIR / f"{bid}.log").unlink(missing_ok=True)
        DB["bots"].pop(bid, None)
        save_data()
        await q.answer("🗑 মুছে ফেলা হয়েছে")
        await edit(q, wallet_text(uid), wallet_markup(uid))
        return
    text, markup = bot_view(bid)
    await edit(q, text, markup)


# ───────────────────────── Market ─────────────────────────
async def show_market(update: Update, context: ContextTypes.DEFAULT_TYPE, q=None):
    tpls = DB["templates"]
    if not tpls:
        text, markup = f"🛒 <b>বট মার্কেট</b>\n{LINE}\n\n📭 এখনো কোনো বট যোগ করা হয়নি। পরে আবার দেখুন!", None
    else:
        text = (
            f"🛒 <b>বট মার্কেট</b>\n{LINE}\n\n"
            "🔥 রেডিমেড বট — শুধু আপনার <b>Bot Token</b> দিলেই চালু!\n\n👇 একটি বট সিলেক্ট করুন:"
        )
        markup = kb(*[[ib(f"🤖 {t['name']}  •  {money(t['price'])}", cb=f"mk:{tid}", style="success")] for tid, t in tpls.items()])
    if q:
        await edit(q, text, markup)
    else:
        await send(update, text, markup)


async def market_item(q, tid: str, uid: int):
    t = DB["templates"].get(tid)
    if not t:
        await q.answer("❌ বট পাওয়া যায়নি", show_alert=True)
        return
    u = DB["users"][str(uid)]
    await edit(
        q,
        f"🤖 <b>{esc(t['name'])}</b>\n{LINE}\n\n"
        f"📝 {esc(t.get('desc') or 'কোনো বিবরণ নেই')}\n\n"
        f"💸 <b>দাম:</b> <code>{money(t['price'])}</code>\n"
        f"💰 <b>আপনার ব্যালেন্স:</b> <code>{money(u['balance'])}</code>",
        kb([ib("🛒 কিনুন ও চালু করুন", cb=f"mkbuy:{tid}", style="success")], [ib("⬅️ Back", cb="market")]),
    )


# ───────────────────────── Add Money ─────────────────────────
METHOD_EMOJI = {"bKash": "🟣", "Nagad": "🟠", "Rocket": "🟪", "Crypto": "🪙"}


def gen_pay_code() -> str:
    for _ in range(2000):
        code = f"PAY-{random.randint(1000, 9999)}"
        if code not in DB["payment_codes"]:
            return code
    while True:
        code = f"PAY-{random.randint(10000, 99999)}"
        if code not in DB["payment_codes"]:
            return code


async def show_add_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user(update.effective_user)
    nums = DB["payment_numbers"]
    if not nums:
        await send(update, f"💳 <b>এড মানি</b>\n{LINE}\n\n⚠️ এখনো পেমেন্ট নাম্বার সেট করা হয়নি। এডমিনের সাথে যোগাযোগ করুন।")
        return
    for c in DB["payment_codes"].values():  # পুরনো অব্যবহৃত কোড এক্সপায়ার
        if c["uid"] == uid and c["status"] == "created":
            c["status"] = "expired"
    code = gen_pay_code()
    DB["payment_codes"][code] = {"uid": uid, "status": "created", "amount": None, "trx": None, "created": now()}
    save_data()
    lines = "\n".join(
        f"{METHOD_EMOJI.get(n['method'], '💠')} <b>{esc(n['method'])}:</b> <code>{esc(n['number'])}</code>" for n in nums
    )
    rows = [[ib(f"📋 কপি: {n['method']}", copy_text=n["number"], style="primary")] for n in nums[:6]]
    rows.append([ib("📋 কপি: Reference কোড", copy_text=code, style="primary")])
    rows.append([ib("✅ I Paid", cb=f"am:paid:{code}", style="success"), ib("❌ Cancel", cb=f"am:cancel:{code}", style="danger")])
    await send(
        update,
        f"💳 <b>এড মানি</b>\n{LINE}\n\n"
        f"🔖 <b>আপনার Reference কোড:</b>\n<code>{code}</code>\n\n"
        f"📲 <b>এই নাম্বারে টাকা পাঠান:</b>\n{lines}\n\n"
        f"📝 Reference এ লিখুন: <code>{code}</code>\n\n"
        "👆 <i>নাম্বার/কোডের উপর ট্যাপ করলে কপি হবে।</i>\n"
        "✅ টাকা পাঠানো শেষে <b>I Paid</b> বাটনে ক্লিক করুন।\n"
        "⚠️ <i>এই কোড শুধু একবারই ব্যবহার করা যাবে।</i>",
        kb(*rows),
    )


async def pay_callback(update, context, q, uid, parts):
    act, code = parts[1], parts[2]
    pc = DB["payment_codes"].get(code)
    if not pc or pc["uid"] != uid:
        await q.answer("❌ কোড পাওয়া যায়নি", show_alert=True)
        return
    if pc["status"] != "created":
        await q.answer("⚠️ এই কোড আগেই ব্যবহার/এক্সপায়ার হয়েছে!", show_alert=True)
        return
    if act == "cancel":
        pc["status"] = "cancelled"
        save_data()
        await q.answer()
        await edit(q, "❌ <b>পেমেন্ট রিকোয়েস্ট বাতিল করা হয়েছে।</b>")
    elif act == "paid":
        await q.answer()
        context.user_data["state"] = {"name": "pay_amount", "code": code}
        await q.message.chat.send_message(
            f"💵 <b>কত টাকা পাঠিয়েছেন?</b>\n\nশুধু সংখ্যা লিখুন (যেমন: <code>100</code>)",
            parse_mode=ParseMode.HTML,
            reply_markup=CANCEL_KB,
        )


async def approval(q, context, code: str, ok: bool):
    pc = DB["payment_codes"].get(code)
    if not pc or pc["status"] != "submitted":
        await q.answer("⚠️ আগেই প্রসেস করা হয়েছে!", show_alert=True)
        return
    u = DB["users"].get(str(pc["uid"]))
    if ok:
        pc["status"] = "approved"
        u["balance"] = round(u["balance"] + pc["amount"], 2)
    else:
        pc["status"] = "rejected"
    pc["resolved"] = now()
    save_data()
    await q.answer("✅ Approved" if ok else "❌ Rejected")
    await edit(q, q.message.text_html + f"\n\n{'✅ <b>APPROVED</b>' if ok else '❌ <b>REJECTED</b>'}")
    try:
        if ok:
            await context.bot.send_message(
                pc["uid"],
                f"✅ <b>পেমেন্ট অ্যাপ্রুভড!</b>\n{LINE}\n\n💵 <b>যোগ হয়েছে:</b> <code>{money(pc['amount'])}</code>\n"
                f"💰 <b>নতুন ব্যালেন্স:</b> <code>{money(u['balance'])}</code>\n🔖 <code>{code}</code>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await context.bot.send_message(
                pc["uid"],
                f"❌ <b>পেমেন্ট রিজেক্ট করা হয়েছে</b>\n{LINE}\n\n🔖 <code>{code}</code>\n"
                "সমস্যা হলে সাপোর্টে যোগাযোগ করুন।",
                parse_mode=ParseMode.HTML,
            )
    except TelegramError:
        pass


def pay_request_text(code: str) -> str:
    pc = DB["payment_codes"][code]
    u = DB["users"].get(str(pc["uid"]), {})
    uname = f"@{u['username']}" if u.get("username") else "—"
    return (
        f"💳 <b>নতুন পেমেন্ট রিকোয়েস্ট</b>\n{LINE}\n\n"
        f"👤 <b>User:</b> {esc(u.get('name', '?'))} ({esc(uname)})\n"
        f"🆔 <b>ID:</b> <code>{pc['uid']}</code>\n"
        f"🔖 <b>Code:</b> <code>{code}</code>\n"
        f"💵 <b>Amount:</b> <code>{money(pc['amount'])}</code>\n"
        f"🧾 <b>TrxID:</b> <code>{esc(pc['trx'])}</code>"
    )


def pay_request_markup(code: str):
    return kb([ib("✅ Approve", cb=f"ap:ok:{code}", style="success"), ib("❌ Reject", cb=f"ap:no:{code}", style="danger")])


# ═══════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
def admin_home():
    pend = sum(1 for c in DB["payment_codes"].values() if c["status"] == "submitted")
    text = f"👑 <b>এডমিন প্যানেল</b>\n{LINE}\n\n👇 একটি অপশন বেছে নিন:"
    markup = kb(
        [ib("💳 পেমেন্ট নাম্বার", cb="adm:pay", style="primary"), ib("💲 দাম ঠিক করা", cb="adm:price", style="success")],
        [ib("🛍 বট মার্কেট", cb="adm:mk", style="primary"), ib("➕ মার্কেটে বট এড", cb="adm:tplnew", style="success")],
        [ib("🔒 চ্যানেল লক", cb="adm:ch", style="success")],
        [ib(f"⏳ Pending Payments ({pend})", cb="adm:pending", style="danger")],
        [ib("📞 সাপোর্ট সেট", cb="adm:support"), ib("📊 স্ট্যাটস", cb="adm:stats")],
    )
    return text, markup


async def show_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    t, m = admin_home()
    await send(update, t, m)


def render_pay_admin():
    nums = DB["payment_numbers"]
    text = f"💳 <b>পেমেন্ট নাম্বার</b>\n{LINE}\n\n"
    text += (
        "\n".join(f"{METHOD_EMOJI.get(n['method'], '💠')} <b>{esc(n['method'])}:</b> <code>{esc(n['number'])}</code>" for n in nums)
        if nums
        else "📭 কোনো নাম্বার নেই।"
    )
    rows = [[ib(f"🗑 {n['method']} • {n['number']}", cb=f"adm:payd:{n['id']}", style="danger")] for n in nums]
    rows.append([ib("➕ নাম্বার এড করুন", cb="adm:payadd", style="success")])
    rows.append([ib("⬅️ Back", cb="adm:home")])
    return text, kb(*rows)


def render_price_admin():
    text = (
        f"💲 <b>দাম ঠিক করা</b>\n{LINE}\n\n"
        f"📂 <b>Global Price</b> (নিজের কোড দিয়ে বট রান): <code>{money(DB['settings']['global_price'])}</code>\n\n"
        "🛒 <b>মার্কেট বটের দাম:</b>\n"
    )
    rows = [[ib(f"✏️ Global Price: {money(DB['settings']['global_price'])}", cb="adm:gprice", style="success")]]
    if DB["templates"]:
        for tid, t in DB["templates"].items():
            rows.append([ib(f"🤖 {t['name']} • {money(t['price'])}", cb=f"adm:tp:{tid}", style="primary")])
    else:
        text += "   📭 মার্কেটে কোনো বট নেই\n"
    rows.append([ib("⬅️ Back", cb="adm:home")])
    return text, kb(*rows)


def render_market_admin():
    tpls = DB["templates"]
    text = f"🛍 <b>বট মার্কেট (এডমিন)</b>\n{LINE}\n\n"
    if tpls:
        text += f"🤖 <b>মোট বট:</b> <code>{len(tpls)}</code>\n\n👇 কোড এডিট / ডিলিট করতে বট সিলেক্ট করুন:"
    else:
        text += "📭 মার্কেটে কোনো বট নেই।"
    rows = [[ib(f"🤖 {t['name']}  •  {money(t['price'])}", cb=f"adm:mki:{tid}", style="primary")] for tid, t in tpls.items()]
    rows.append([ib("➕ নতুন বট এড", cb="adm:tplnew", style="success")])
    rows.append([ib("⬅️ Back", cb="adm:home")])
    return text, kb(*rows)


def render_market_item(tid: str):
    t = DB["templates"][tid]
    sold = sum(1 for b in DB["bots"].values() if b.get("template") == tid)
    text = (
        f"🤖 <b>{esc(t['name'])}</b>\n{LINE}\n\n"
        f"💸 <b>দাম:</b> <code>{money(t['price'])}</code>\n"
        f"🛒 <b>বিক্রি:</b> <code>{sold}</code>\n"
        f"📝 {esc(t.get('desc') or '-')}"
    )
    markup = kb(
        [ib("✏️ কোড এডিট", cb=f"adm:mkedit:{tid}", style="primary"), ib("📥 বর্তমান কোড", cb=f"adm:mkget:{tid}")],
        [ib("💲 দাম পরিবর্তন", cb=f"adm:tpprice:{tid}", style="success")],
        [ib("🗑 ডিলিট", cb=f"adm:mkdelask:{tid}", style="danger")],
        [ib("⬅️ Back", cb="adm:mk")],
    )
    return text, markup


def render_channels_admin():
    chs = DB["channel_lock"]
    text = f"🔒 <b>চ্যানেল জয়েন লক</b>\n{LINE}\n\n"
    text += "\n".join(f"📢 {esc(c)}" for c in chs) if chs else "🔓 কোনো লক সেট নেই।"
    text += "\n\n⚠️ <i>বটকে অবশ্যই চ্যানেলের Admin বানাতে হবে।</i>"
    rows = [[ib(f"🗑 {c}", cb=f"adm:chdel:{i}", style="danger")] for i, c in enumerate(chs)]
    rows.append([ib("➕ চ্যানেল এড করুন", cb="adm:chadd", style="success")])
    rows.append([ib("⬅️ Back", cb="adm:home")])
    return text, kb(*rows)


async def admin_callback(update, context, q, data):
    parts = data.split(":")
    act = parts[1]
    await q.answer()

    if act == "home":
        context.user_data.pop("state", None)
        t, m = admin_home()
        await edit(q, t, m)

    elif act == "pay":
        t, m = render_pay_admin()
        await edit(q, t, m)
    elif act == "payadd":
        rows = [[ib(f"{METHOD_EMOJI[m]} {m}", cb=f"adm:payam:{m}", style="primary")] for m in METHOD_EMOJI]
        rows.append([ib("⬅️ Back", cb="adm:pay")])
        await edit(q, "➕ <b>পেমেন্ট মেথড সিলেক্ট করুন:</b>", kb(*rows))
    elif act == "payam":
        method = parts[2]
        context.user_data["state"] = {"name": "adm_pay_num", "method": method}
        await edit(q, f"📲 <b>{esc(method)}</b> এর নাম্বার / ওয়ালেট এড্রেস পাঠান:", CANCEL_KB)
    elif act == "payd":
        DB["payment_numbers"] = [n for n in DB["payment_numbers"] if n["id"] != parts[2]]
        save_data()
        t, m = render_pay_admin()
        await edit(q, t, m)

    elif act == "price":
        t, m = render_price_admin()
        await edit(q, t, m)
    elif act == "gprice":
        context.user_data["state"] = {"name": "adm_global_price"}
        await edit(q, "💲 <b>Global Price</b> লিখুন (নিজের কোড দিয়ে বট রান করার চার্জ):", CANCEL_KB)
    elif act == "tp":
        tid = parts[2]
        t = DB["templates"].get(tid)
        if not t:
            return
        await edit(
            q,
            f"🤖 <b>{esc(t['name'])}</b>\n{LINE}\n\n💸 <b>দাম:</b> <code>{money(t['price'])}</code>\n📝 {esc(t.get('desc') or '-')}",
            kb(
                [ib("✏️ দাম পরিবর্তন", cb=f"adm:tpprice:{tid}", style="success")],
                [ib("🗑 মার্কেট থেকে মুছুন", cb=f"adm:tpdel:{tid}", style="danger")],
                [ib("⬅️ Back", cb="adm:price")],
            ),
        )
    elif act == "tpprice":
        context.user_data["state"] = {"name": "adm_tpl_price_edit", "tid": parts[2]}
        await edit(q, "💲 এই বটের নতুন দাম লিখুন:", CANCEL_KB)
    elif act == "tpdel":
        t = DB["templates"].pop(parts[2], None)
        if t:
            Path(t["file"]).unlink(missing_ok=True)
            save_data()
        t, m = render_price_admin()
        await edit(q, t, m)

    elif act == "mk":
        context.user_data.pop("state", None)
        t, m = render_market_admin()
        await edit(q, t, m)
    elif act == "mki":
        if parts[2] not in DB["templates"]:
            t, m = render_market_admin()
            await edit(q, t, m)
            return
        t, m = render_market_item(parts[2])
        await edit(q, t, m)
    elif act == "mkedit":
        t = DB["templates"].get(parts[2])
        if not t:
            return
        context.user_data["state"] = {"name": "adm_tpl_edit", "tid": parts[2]}
        await edit(
            q,
            f"✏️ <b>কোড এডিট — {esc(t['name'])}</b>\n{LINE}\n\n"
            "📂 নতুন কোড <b>.py ফাইল</b> হিসেবে পাঠান, অথবা <b>কোড লিখে/পেস্ট করে</b> মেসেজ পাঠান "
            "(শেষে <b>✅ কোড সম্পূর্ণ</b> চাপুন)।\n\n"
            "ℹ️ <i>নতুন কোড শুধু ভবিষ্যতে কেনা বটে যাবে; আগে কেনা বট অপরিবর্তিত থাকবে।</i>",
            CANCEL_KB,
        )
    elif act == "mkget":
        t = DB["templates"].get(parts[2])
        if not t or not Path(t["file"]).exists():
            await q.message.chat.send_message("❌ কোড ফাইল পাওয়া যায়নি।")
            return
        fname = re.sub(r"[^A-Za-z0-9_-]", "_", t["name"]) or parts[2]
        with open(t["file"], "rb") as f:
            await q.message.chat.send_document(f, filename=f"{fname}.py", caption=f"📥 {t['name']} — বর্তমান কোড")
    elif act == "mkdelask":
        t = DB["templates"].get(parts[2])
        if not t:
            return
        await edit(
            q,
            f"🗑 <b>{esc(t['name'])}</b> মার্কেট থেকে ডিলিট করবেন?\n\n"
            "⚠️ <i>কোড ফাইল মুছে যাবে। যারা আগে কিনেছে তাদের চালু বট অপরিবর্তিত থাকবে।</i>",
            kb([ib("✅ হ্যাঁ, ডিলিট", cb=f"adm:mkdel:{parts[2]}", style="danger"), ib("❌ না", cb=f"adm:mki:{parts[2]}", style="success")]),
        )
    elif act == "mkdel":
        t = DB["templates"].pop(parts[2], None)
        if t:
            Path(t["file"]).unlink(missing_ok=True)
            save_data()
        t, m = render_market_admin()
        await edit(q, "✅ <b>বট ডিলিট হয়েছে।</b>\n\n" + t, m)

    elif act == "tplnew":
        context.user_data["state"] = {"name": "adm_tpl_name"}
        await edit(q, f"➕ <b>মার্কেটে নতুন বট</b>\n{LINE}\n\n<b>ধাপ ১/৪:</b> বটের <b>নাম</b> লিখুন:", CANCEL_KB)

    elif act == "ch":
        t, m = render_channels_admin()
        await edit(q, t, m)
    elif act == "chadd":
        context.user_data["state"] = {"name": "adm_ch_add"}
        await edit(q, "📢 চ্যানেলের <b>@username</b> পাঠান (যেমন: <code>@mychannel</code>):", CANCEL_KB)
    elif act == "chdel":
        i = int(parts[2])
        if 0 <= i < len(DB["channel_lock"]):
            DB["channel_lock"].pop(i)
            save_data()
        t, m = render_channels_admin()
        await edit(q, t, m)

    elif act == "pending":
        pend = [c for c, v in DB["payment_codes"].items() if v["status"] == "submitted"]
        if not pend:
            await edit(q, "✅ <b>কোনো Pending পেমেন্ট নেই।</b>", kb([ib("⬅️ Back", cb="adm:home")]))
            return
        await edit(q, f"⏳ <b>{len(pend)}টি Pending পেমেন্ট</b> নিচে পাঠানো হলো 👇", kb([ib("⬅️ Back", cb="adm:home")]))
        for code in pend[:15]:
            await q.message.chat.send_message(
                pay_request_text(code), parse_mode=ParseMode.HTML, reply_markup=pay_request_markup(code)
            )

    elif act == "support":
        context.user_data["state"] = {"name": "adm_support"}
        await edit(q, "📞 সাপোর্ট <b>@username</b> বা লিংক পাঠান:", CANCEL_KB)

    elif act == "stats":
        total_bal = sum(u["balance"] for u in DB["users"].values())
        running = sum(1 for b in DB["bots"].values() if b["status"] == "running")
        pend = sum(1 for c in DB["payment_codes"].values() if c["status"] == "submitted")
        await edit(
            q,
            f"📊 <b>স্ট্যাটস</b>\n{LINE}\n\n"
            f"👥 <b>Users:</b> <code>{len(DB['users'])}</code>\n"
            f"🤖 <b>Total Bots:</b> <code>{len(DB['bots'])}</code>\n"
            f"🟢 <b>Running:</b> <code>{running}</code>\n"
            f"🛒 <b>Market Bots:</b> <code>{len(DB['templates'])}</code>\n"
            f"💰 <b>Users' Total Balance:</b> <code>{money(total_bal)}</code>\n"
            f"⏳ <b>Pending Payments:</b> <code>{pend}</code>",
            kb([ib("⬅️ Back", cb="adm:home")]),
        )


# ═══════════════════════════════════════════════════════════════
#  TOKEN PROCESSING (custom + market)
# ═══════════════════════════════════════════════════════════════
async def process_token(update: Update, context: ContextTypes.DEFAULT_TYPE, st: dict):
    user = update.effective_user
    uid = user.id
    token = update.message.text.strip()
    try:
        await update.message.delete()  # সিকিউরিটির জন্য টোকেন মেসেজ ডিলিট
    except TelegramError:
        pass
    if not TOKEN_RE.match(token):
        await send(update, "❌ <b>টোকেন সঠিক নয়!</b> @BotFather থেকে পাওয়া সঠিক টোকেন পাঠান।", CANCEL_KB)
        return
    if any(b["token"] == token for b in DB["bots"].values()):
        await send(update, "⚠️ <b>এই টোকেন দিয়ে আগে থেকেই একটি বট চলছে!</b> অন্য টোকেন দিন।", CANCEL_KB)
        return
    wait = await send(update, "⏳ <b>টোকেন যাচাই করা হচ্ছে...</b>")
    me = await validate_token(token)
    if not me:
        await wait.edit_text("❌ <b>টোকেন ইনভ্যালিড!</b> আবার চেষ্টা করুন।", parse_mode=ParseMode.HTML, reply_markup=CANCEL_KB)
        return

    if st["name"] == "custom_token":
        src, price, source, tid = Path(st["file"]), DB["settings"]["global_price"], "custom", None
    else:
        tpl = DB["templates"].get(st["tid"])
        if not tpl or not Path(tpl["file"]).exists():
            context.user_data.pop("state", None)
            await wait.edit_text("❌ এই বটটি আর মার্কেটে নেই।")
            return
        src, price, source, tid = Path(tpl["file"]), tpl["price"], "market", st["tid"]

    u = DB["users"][str(uid)]
    if u["balance"] < price:
        context.user_data.pop("state", None)
        await wait.edit_text(
            f"⚠️ <b>ব্যালেন্স যথেষ্ট নয়!</b>\n💸 প্রয়োজন: <code>{money(price)}</code> | 💰 আছে: <code>{money(u['balance'])}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([ib("💳 এড মানি", cb="am:new", style="primary")]),
        )
        return

    context.user_data.pop("state", None)
    await wait.edit_text("🚀 <b>বট ডিপ্লয় হচ্ছে... (লাইব্রেরি ইনস্টল হলে একটু সময় লাগতে পারে)</b>", parse_mode=ParseMode.HTML)
    ok, res = await deploy_bot(context, update, uid, token, me, src, source, tid, price)
    if source == "custom":
        src.unlink(missing_ok=True)
    if not ok:
        await wait.edit_text("❌ <b>বট চালু করা যায়নি।</b> টাকা কাটা হয়নি। আবার চেষ্টা করুন।", parse_mode=ParseMode.HTML)
        return
    await wait.edit_text(
        f"✅ <b>বট সফলভাবে ডিপ্লয় হয়েছে!</b>\n{LINE}\n\n"
        f"🤖 <b>Bot:</b> @{esc(me.username)}\n"
        f"💸 <b>চার্জ:</b> <code>{money(price)}</code>\n"
        f"💰 <b>বাকি ব্যালেন্স:</b> <code>{money(u['balance'])}</code>\n"
        f"🟢 <b>Status:</b> Running\n\n"
        "ℹ️ কিছুক্ষণের মধ্যে বট বন্ধ হলে আমি আপনাকে লগসহ জানিয়ে দেব।",
        parse_mode=ParseMode.HTML,
        reply_markup=kb(
            [ib("🔗 বট ওপেন করুন", url=f"https://t.me/{me.username}", style="success")],
            [ib("⚙️ ম্যানেজ", cb=f"bm:{res}", style="primary")],
        ),
    )


# ═══════════════════════════════════════════════════════════════
#  MESSAGE HANDLERS
# ═══════════════════════════════════════════════════════════════
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    get_user(user)
    text = (update.message.text or "").strip()

    # ── Main menu buttons ──
    if text in MENU_LABELS:
        context.user_data.pop("state", None)
        if text == BTN_ADMIN and uid != ADMIN_ID:
            return
        if not await gate(update, context):
            return
        await MENU_ACTIONS[text](update, context)
        return

    st = context.user_data.get("state")
    if not st:
        return
    if not await gate(update, context):
        return
    name = st["name"]

    if name in ("custom_token", "market_token"):
        await process_token(update, context, st)

    elif name in CODE_STATES:
        if name in ADMIN_CODE_STATES and uid != ADMIN_ID:
            return
        await collect_code(update, context, st)

    # ── Add money ──
    elif name == "pay_amount":
        amt = parse_num(text)
        if not amt or amt <= 0:
            await send(update, "❌ সঠিক সংখ্যা লিখুন (যেমন: <code>100</code>)", CANCEL_KB)
            return
        context.user_data["state"] = {"name": "pay_trx", "code": st["code"], "amount": amt}
        await send(update, "🧾 আপনার পেমেন্টের <b>Transaction ID (TrxID)</b> লিখুন:", CANCEL_KB)

    elif name == "pay_trx":
        trx = text.upper()[:40]
        code = st["code"]
        pc = DB["payment_codes"].get(code)
        if not pc or pc["status"] != "created":
            context.user_data.pop("state", None)
            await send(update, "⚠️ এই কোড আগেই ব্যবহার হয়েছে বা এক্সপায়ার!")
            return
        if len(trx) < 4:
            await send(update, "❌ সঠিক TrxID দিন।", CANCEL_KB)
            return
        if any(c.get("trx") == trx and c["status"] in ("submitted", "approved") for c in DB["payment_codes"].values()):
            await send(update, "🚫 <b>এই TrxID আগেই ব্যবহার করা হয়েছে!</b>", CANCEL_KB)
            return
        pc.update({"status": "submitted", "amount": st["amount"], "trx": trx, "submitted": now()})
        save_data()
        context.user_data.pop("state", None)
        await send(
            update,
            f"✅ <b>রিকোয়েস্ট জমা হয়েছে!</b>\n{LINE}\n\n🔖 <code>{code}</code>\n💵 <code>{money(pc['amount'])}</code>\n\n"
            "⏳ এডমিন যাচাই করে ব্যালেন্স যোগ করবেন। অনুগ্রহ করে অপেক্ষা করুন।",
        )
        try:
            await context.bot.send_message(
                ADMIN_ID, pay_request_text(code), parse_mode=ParseMode.HTML, reply_markup=pay_request_markup(code)
            )
        except TelegramError as e:
            log.error("Admin notify failed: %s", e)

    # ── Admin states ──
    elif uid == ADMIN_ID:
        await admin_text_state(update, context, st, text)


CODE_DONE_KB = kb(
    [ib("✅ কোড সম্পূর্ণ", cb="codedone", style="success")],
    [ib("❌ বাতিল করুন", cb="cancel", style="danger")],
)


async def collect_code(update: Update, context: ContextTypes.DEFAULT_TYPE, st: dict):
    """লেখা কোডের অংশ জমা করে; ইউজার '✅ কোড সম্পূর্ণ' চাপলে প্রসেস হয়।"""
    msg = update.message
    buf = st.setdefault("buf", {})
    buf[msg.message_id] = msg.text or ""  # message_id দিয়ে সাজানো হয় — ক্রম ঠিক থাকে
    total = sum(len(v) for v in buf.values())
    old = st.get("status_mid")
    status = await send(
        update,
        f"📝 <b>কোড গ্রহণ হচ্ছে...</b>\n{LINE}\n\n"
        f"📨 <b>অংশ:</b> <code>{len(buf)}</code>  |  🔤 <b>অক্ষর:</b> <code>{total}</code>\n\n"
        "আরও অংশ থাকলে পাঠান। কোড শেষ হলে <b>✅ কোড সম্পূর্ণ</b> চাপুন।",
        CODE_DONE_KB,
    )
    st["status_mid"] = status.message_id
    if old:
        try:
            await context.bot.delete_message(update.effective_chat.id, old)
        except TelegramError:
            pass


async def code_done(update, context, q, uid):
    st = context.user_data.get("state")
    if not st or st["name"] not in CODE_STATES:
        await q.answer("⚠️ কোনো কাজ চলছে না। মেনু থেকে আবার শুরু করুন।", show_alert=True)
        return
    if st["name"] in ADMIN_CODE_STATES and uid != ADMIN_ID:
        await q.answer("⛔ Access denied", show_alert=True)
        return
    buf = st.get("buf") or {}
    if not buf:
        await q.answer("⚠️ আগে কোড লিখে পাঠান।", show_alert=True)
        return
    await q.answer()
    text = "\n".join(buf[k] for k in sorted(buf))
    wait = await q.message.chat.send_message("⏳ <b>কোড যাচাই করা হচ্ছে...</b>", parse_mode=ParseMode.HTML)
    ok, res = await code_from_text(uid, text)
    if not ok:
        st["buf"], st["status_mid"] = {}, None  # ভুল কোড বাদ — নতুন করে পাঠাতে হবে
        await wait.edit_text(res + "\n\nসঠিক কোড আবার পাঠান।", parse_mode=ParseMode.HTML, reply_markup=CANCEL_KB)
        return
    await after_code(context, uid, st, res, wait)


async def admin_text_state(update, context, st, text):
    name = st["name"]
    back = kb([ib("⬅️ এডমিন প্যানেল", cb="adm:home")])

    if name == "adm_pay_num":
        DB["payment_numbers"].append({"id": next_id("pay", "p"), "method": st["method"], "number": text[:120]})
        save_data()
        context.user_data.pop("state", None)
        t, m = render_pay_admin()
        await send(update, "✅ <b>নাম্বার এড হয়েছে!</b>\n\n" + t, m)

    elif name == "adm_global_price":
        v = parse_num(text)
        if v is None:
            await send(update, "❌ সঠিক সংখ্যা লিখুন।", CANCEL_KB)
            return
        DB["settings"]["global_price"] = v
        save_data()
        context.user_data.pop("state", None)
        t, m = render_price_admin()
        await send(update, "✅ <b>Global Price আপডেট হয়েছে!</b>\n\n" + t, m)

    elif name == "adm_tpl_price_edit":
        v = parse_num(text)
        t = DB["templates"].get(st["tid"])
        if v is None or not t:
            await send(update, "❌ সঠিক সংখ্যা লিখুন।", CANCEL_KB)
            return
        t["price"] = v
        save_data()
        context.user_data.pop("state", None)
        tt, m = render_price_admin()
        await send(update, "✅ <b>দাম আপডেট হয়েছে!</b>\n\n" + tt, m)

    elif name == "adm_tpl_name":
        context.user_data["state"] = {"name": "adm_tpl_price", "tname": text[:50]}
        await send(update, "<b>ধাপ ২/৪:</b> এই বটের <b>দাম</b> লিখুন (যেমন: <code>30</code>):", CANCEL_KB)

    elif name == "adm_tpl_price":
        v = parse_num(text)
        if v is None:
            await send(update, "❌ সঠিক সংখ্যা লিখুন।", CANCEL_KB)
            return
        context.user_data["state"] = {"name": "adm_tpl_desc", "tname": st["tname"], "price": v}
        await send(update, "<b>ধাপ ৩/৪:</b> বটের <b>বিবরণ</b> লিখুন (স্কিপ করতে <code>-</code> দিন):", CANCEL_KB)

    elif name == "adm_tpl_desc":
        desc = "" if text == "-" else text[:400]
        context.user_data["state"] = {"name": "adm_tpl_file", "tname": st["tname"], "price": st["price"], "desc": desc}
        await send(update, "<b>ধাপ ৪/৪:</b> বটের কোড <b>.py ফাইল</b> হিসেবে পাঠান, অথবা <b>কোড লিখে/পেস্ট করে</b> "
                           "মেসেজ পাঠান (শেষে <b>✅ কোড সম্পূর্ণ</b> চাপুন):\n\n"
                           "💡 <i>কোডে টোকেনের জায়গায় <code>os.getenv('BOT_TOKEN')</code> ব্যবহার করুন।</i>", CANCEL_KB)

    elif name == "adm_ch_add":
        ch = text.strip()
        if "t.me/" in ch:
            ch = "@" + ch.rstrip("/").split("/")[-1]
        if not ch.startswith("@"):
            ch = "@" + ch
        if not re.match(r"^@[A-Za-z][A-Za-z0-9_]{4,31}$", ch):
            await send(update, "❌ সঠিক @username দিন।", CANCEL_KB)
            return
        if ch in DB["channel_lock"]:
            await send(update, "⚠️ এই চ্যানেল আগেই এড করা আছে।", CANCEL_KB)
            return
        try:
            await context.bot.get_chat(ch)
            me = await context.bot.get_chat_member(ch, context.bot.id)
            if me.status not in ("administrator", "creator"):
                raise TelegramError("not admin")
        except TelegramError:
            await send(update, "❌ চ্যানেল পাওয়া যায়নি, অথবা বট ঐ চ্যানেলের <b>Admin</b> নয়। বটকে Admin বানিয়ে আবার পাঠান।", CANCEL_KB)
            return
        DB["channel_lock"].append(ch)
        save_data()
        context.user_data.pop("state", None)
        t, m = render_channels_admin()
        await send(update, "✅ <b>চ্যানেল লক এড হয়েছে!</b>\n\n" + t, m)

    elif name == "adm_support":
        DB["settings"]["support"] = text[:200]
        save_data()
        context.user_data.pop("state", None)
        await send(update, f"✅ সাপোর্ট সেট হয়েছে: <b>{esc(text[:200])}</b>", back)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    get_user(user)
    st = context.user_data.get("state")
    if not st or st["name"] not in CODE_STATES:
        await send(update, "ℹ️ ফাইল পাঠানোর আগে মেনু থেকে <b>➕ এড বট</b> চাপুন।")
        return
    if st["name"] in ADMIN_CODE_STATES and uid != ADMIN_ID:
        return
    if not await gate(update, context):
        return

    wait = await send(update, "⏳ <b>ফাইল যাচাই করা হচ্ছে...</b>")
    ok, res = await fetch_code_file(context, uid, update.message.document)
    if not ok:
        await wait.edit_text(res + "\n\nআবার সঠিক ফাইল পাঠান।", parse_mode=ParseMode.HTML, reply_markup=CANCEL_KB)
        return
    await after_code(context, uid, st, res, wait)


async def after_code(context, uid: int, st: dict, path: Path, wait):
    """ফাইল বা লেখা — যেভাবেই কোড আসুক, যাচাইয়ের পর এখান থেকে পরের ধাপ চলে।"""
    if st["name"] == "upload_code":
        context.user_data["state"] = {"name": "custom_token", "file": str(path)}
        await wait.edit_text(
            f"✅ <b>কোড গ্রহণ করা হয়েছে!</b>\n{LINE}\n\n"
            "🔑 <b>ধাপ ২:</b> আপনার বটের <b>Bot Token</b> পাঠান (@BotFather থেকে)।",
            parse_mode=ParseMode.HTML,
            reply_markup=CANCEL_KB,
        )

    elif st["name"] == "edit_code":
        bid = st["bid"]
        b = DB["bots"].get(bid)
        context.user_data.pop("state", None)
        if not b or (b["owner"] != uid and uid != ADMIN_ID):
            path.unlink(missing_ok=True)
            await wait.edit_text("❌ বট পাওয়া যায়নি।")
            return
        was_running = b["status"] == "running"
        await stop_bot_process(bid)
        shutil.move(str(path), b["file"])
        patch_token(Path(b["file"]), b["token"])
        await ensure_deps(Path(b["file"]))
        if was_running:
            start_bot_process(bid)
        await wait.edit_text(
            f"✅ <b>কোড আপডেট হয়েছে!</b>\n🤖 @{esc(b['name'])}\n"
            f"{'🟢 বট রিস্টার্ট হয়েছে।' if was_running else '🔴 বট বন্ধ আছে — Start করুন।'}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb(
                [ib("🔗 বট ওপেন করুন", url=bot_url(b), style="success")] if was_running else [],
                [ib("⚙️ ম্যানেজ", cb=f"bm:{bid}", style="primary")],
            ),
        )

    elif st["name"] == "adm_tpl_edit":
        tid = st["tid"]
        t = DB["templates"].get(tid)
        context.user_data.pop("state", None)
        if not t:
            path.unlink(missing_ok=True)
            await wait.edit_text("❌ এই বটটি আর মার্কেটে নেই।")
            return
        TEMPLATES_DIR.mkdir(exist_ok=True)
        shutil.move(str(path), t["file"])
        t["updated"] = now()
        save_data()
        await wait.edit_text(
            f"✅ <b>মার্কেট বটের কোড আপডেট হয়েছে!</b>\n🤖 <b>{esc(t['name'])}</b>\n\n"
            "ℹ️ <i>নতুন কোড শুধু ভবিষ্যতে কেনা বটে যাবে।</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([ib("⬅️ বট মার্কেট", cb=f"adm:mki:{tid}", style="primary")]),
        )

    elif st["name"] == "adm_tpl_file":
        TEMPLATES_DIR.mkdir(exist_ok=True)
        tid = next_id("tpl", "t")
        dest = TEMPLATES_DIR / f"{tid}.py"
        shutil.move(str(path), dest)
        DB["templates"][tid] = {
            "name": st["tname"],
            "price": st["price"],
            "desc": st["desc"],
            "file": str(dest),
            "created": now(),
        }
        save_data()
        context.user_data.pop("state", None)
        await wait.edit_text(
            f"✅ <b>মার্কেটে বট যোগ হয়েছে!</b>\n{LINE}\n\n🤖 <b>{esc(st['tname'])}</b>\n💸 <code>{money(st['price'])}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([ib("🛍 বট মার্কেট", cb="adm:mk", style="primary")], [ib("⬅️ এডমিন প্যানেল", cb="adm:home")]),
        )


# ═══════════════════════════════════════════════════════════════
#  CALLBACK ROUTER
# ═══════════════════════════════════════════════════════════════
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    uid = user.id
    data = q.data or ""
    get_user(user)

    # ── Channel verify ──
    if data == "verify":
        missing = await missing_channels(context.bot, uid) if uid != ADMIN_ID else []
        if missing:
            await q.answer("❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি!", show_alert=True)
            return
        await q.answer("✅ ভেরিফাইড!")
        try:
            await q.message.delete()
        except TelegramError:
            pass
        await send_welcome(update)
        return

    if data == "cancel":
        st = context.user_data.pop("state", None)
        if st and st.get("file"):
            Path(st["file"]).unlink(missing_ok=True)
        await q.answer("বাতিল")
        await edit(q, "❌ <b>বাতিল করা হয়েছে।</b>")
        return

    # Admin callbacks (no channel gate)
    if data.startswith("adm:"):
        if uid != ADMIN_ID:
            await q.answer("⛔ Access denied", show_alert=True)
            return
        await admin_callback(update, context, q, data)
        return
    if data.startswith("ap:"):
        if uid != ADMIN_ID:
            await q.answer("⛔ Access denied", show_alert=True)
            return
        _, act, code = data.split(":", 2)
        await approval(q, context, code, act == "ok")
        return

    # ── User callbacks (channel lock enforced) ──
    if uid != ADMIN_ID and DB["channel_lock"]:
        if await missing_channels(context.bot, uid):
            await q.answer()
            await gate(update, context)
            return

    parts = data.split(":")
    head = parts[0]

    if head == "wallet":
        await q.answer()
        await edit(q, wallet_text(uid), wallet_markup(uid))
    elif head == "addbot":
        await q.answer()
        await show_add_bot(update, context)
    elif head == "market":
        await q.answer()
        await show_market(update, context, q)
    elif head == "mk":
        await q.answer()
        await market_item(q, parts[1], uid)
    elif head == "mkbuy":
        tid = parts[1]
        t = DB["templates"].get(tid)
        if not t:
            await q.answer("❌ বট পাওয়া যায়নি", show_alert=True)
            return
        if DB["users"][str(uid)]["balance"] < t["price"]:
            await q.answer("⚠️ ব্যালেন্স যথেষ্ট নয়! আগে এড মানি করুন।", show_alert=True)
            return
        await q.answer()
        context.user_data["state"] = {"name": "market_token", "tid": tid}
        await q.message.chat.send_message(
            f"🔑 <b>{esc(t['name'])}</b>\n{LINE}\n\nআপনার <b>Bot Token</b> পাঠান (@BotFather থেকে)।\n"
            f"💸 চার্জ: <code>{money(t['price'])}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=CANCEL_KB,
        )
    elif head == "codedone":
        await code_done(update, context, q, uid)
    elif head == "bm":
        bid = parts[1]
        b = DB["bots"].get(bid)
        if not b or (b["owner"] != uid and uid != ADMIN_ID):
            await q.answer("❌ বট পাওয়া যায়নি", show_alert=True)
            return
        await q.answer()
        t, m = bot_view(bid)
        await edit(q, t, m)
    elif head == "ba":
        await bot_action(update, context, q, uid, parts[1], parts[2])
    elif head == "am":
        if parts[1] == "new":
            await q.answer()
            await show_add_money(update, context)
        else:
            await pay_callback(update, context, q, uid, parts)
    else:
        await q.answer()


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Update error: %s", context.error, exc_info=context.error)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = context.user_data.pop("state", None)
    if st and st.get("file"):
        Path(st["file"]).unlink(missing_ok=True)
    await send(update, "❌ <b>বাতিল করা হয়েছে।</b>", main_menu(update.effective_user.id))


MENU_ACTIONS = {
    BTN_ADD: show_add_bot,
    BTN_MARKET: show_market,
    BTN_WALLET: show_wallet,
    BTN_ADDMONEY: show_add_money,
    BTN_SUPPORT: show_support,
    BTN_ADMIN: show_admin,
}


# ═══════════════════════════════════════════════════════════════
#  LIFECYCLE
# ═══════════════════════════════════════════════════════════════
async def post_init(app: Application):
    for d in (BOTS_DIR, TEMPLATES_DIR, LOGS_DIR, TMP_DIR):
        d.mkdir(exist_ok=True)
    for f in TMP_DIR.glob("*.py"):  # পুরনো টেম্প ফাইল ক্লিন
        f.unlink(missing_ok=True)

    # আগের রানের এতিম প্রসেস থাকলে মেরে ফেলো
    for b in DB["bots"].values():
        pid = b.get("pid")
        if pid and _pid_is_ours(pid, b["file"]):
            try:
                os.killpg(pid, signal.SIGTERM)
            except Exception:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
    await asyncio.sleep(1)

    # প্ল্যাটফর্ম রিস্টার্টে আগে যেগুলো চালু ছিল সেগুলো আবার চালু
    restarted = 0
    for bid, b in list(DB["bots"].items()):
        if b["status"] == "running":
            if Path(b["file"]).exists() and start_bot_process(bid):
                restarted += 1
            else:
                b["status"] = "stopped"
    save_data()
    log.info("Auto-restarted %d bot(s)", restarted)
    app.bot_data["monitor"] = asyncio.create_task(monitor_loop(app))


async def post_shutdown(app: Application):
    task = app.bot_data.get("monitor")
    if task:
        task.cancel()
    # DB তে status "running" রেখে দেওয়া হয় — পরের রানে অটো চালু হবে
    for bid, proc in list(PROCS.items()):
        if proc.poll() is None:
            await asyncio.to_thread(_kill_proc, proc)
    PROCS.clear()


def start_web_server() -> None:
    """Render Web Service এর জন্য ছোট HTTP সার্ভার (PORT env থাকলেই চালু হয়)।
    UptimeRobot/cron-job.org দিয়ে এই URL পিং করলে সার্ভিস ঘুমিয়ে পড়ে না।"""
    port = os.getenv("PORT")
    if not port:
        return
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Health(BaseHTTPRequestHandler):
        def _ok(self, body: bool):
            data = b"OK - hosting platform is running"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if body:
                self.wfile.write(data)

        def do_GET(self):
            self._ok(True)

        def do_HEAD(self):
            self._ok(False)

        def log_message(self, *args):
            pass

    try:
        server = ThreadingHTTPServer(("0.0.0.0", int(port)), Health)
    except Exception as e:
        log.warning("Web server start failed: %s", e)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("🌐 Health server listening on port %s", port)


def main():
    if BOT_TOKEN.startswith("PUT_YOUR"):
        sys.exit("❌ BOT_TOKEN সেট করুন (bot.py এর উপরে অথবা env variable)।")
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("admin", show_admin))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text))
    app.add_error_handler(on_error)
    start_web_server()
    log.info("🚀 Hosting platform started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
