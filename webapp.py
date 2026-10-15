# -*- coding: utf-8 -*-
"""
webapp.py — bot.py এর Telegram Mini App ব্যাকএন্ড (bot.py এর পাশেই রাখো, index.html ও একই ফোল্ডারে)।
• লগইন: Telegram initData (HMAC দিয়ে যাচাই) → ইউজার আইডি দিয়ে অটো লগইন, পাসওয়ার্ড লাগে না
• এডমিন: bot.py এর ADMIN_ID যার, সেই এডমিন
• ডাটা: bot.py এর DB (data.json) ই ব্যবহার হয় — বট ও ওয়েব দুই জায়গায় একই ব্যালেন্স/বট
"""
import hashlib, hmac, json, re, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

M = None  # bot.py module
LOCK = threading.RLock()
HERE = Path(__file__).resolve().parent


class Err(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Err(msg)


def tg(method, token=None, **p):
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token or M.BOT_TOKEN}/{method}",
            json.dumps(p).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=15)).get("result")
    except Exception as e:
        M.log.warning("tg %s failed: %s", method, e)
        return None


def verify(init):
    try:
        d = dict(urllib.parse.parse_qsl(init, keep_blank_values=True))
        h = d.pop("hash")
        chk = "\n".join(f"{k}={d[k]}" for k in sorted(d))
        key = hmac.new(b"WebAppData", M.BOT_TOKEN.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(key, chk.encode(), hashlib.sha256).hexdigest(), h):
            return None
        if time.time() - int(d["auth_date"]) > 86400:
            return None
        return json.loads(d["user"])
    except Exception:
        return None


def missing(uid):
    if uid == M.ADMIN_ID:
        return []
    out = []
    for ch in M.DB["channel_lock"]:
        r = tg("getChatMember", chat_id=ch, user_id=uid)
        if r and (r["status"] in ("left", "kicked") or (r["status"] == "restricted" and not r.get("is_member", True))):
            out.append(ch)
    return out


def stop(bid):
    p = M.PROCS.pop(bid, None)
    if p and p.poll() is None:
        M._kill_proc(p)
    b = M.DB["bots"].get(bid)
    if b:
        b["status"], b["pid"] = "stopped", None
        M.save_data()


def deps(b):
    pk = M._missing_packages(Path(b["file"]))
    if pk:
        M._pip_install(pk)


def check_code(text):
    src = M.clean_code_text(text or "")
    need(src.strip(), "কোড দিন")
    need(len(src.encode()) <= M.MAX_CODE_BYTES, "❌ কোড ২MB এর বেশি")
    try:
        compile(src, "code.py", "exec")
    except SyntaxError as e:
        raise Err(f"❌ Syntax Error (line {e.lineno}): {e.msg}")
    return src


def admin_id_of(d):
    v = str(d.get("admin", "")).strip()
    return int(v) if v.isdigit() else None


def launch(uid, token, src, source, tid, price, admin_id):
    need(M.TOKEN_RE.match(token or ""), "❌ টোকেন ফরম্যাট সঠিক নয়")
    me = tg("getMe", token=token)
    need(me, "❌ টোকেন সঠিক নয় — @BotFather থেকে যাচাই করুন")
    u = M.DB["users"][str(uid)]
    need(u["balance"] >= price, "⚠️ ব্যালেন্স যথেষ্ট নয় — আগে এড মানি করুন")
    name = re.sub(r"[^A-Za-z0-9_]", "", me.get("username") or f"bot{me['id']}")
    M.BOTS_DIR.mkdir(exist_ok=True)
    dest = M.BOTS_DIR / f"{uid}_{name}.py"
    dest.write_text(src, encoding="utf-8")
    M.patch_token(dest, token)
    if admin_id:
        M.patch_admin(dest, admin_id)
    with LOCK:
        need(u["balance"] >= price, "⚠️ ব্যালেন্স যথেষ্ট নয়")
        bid = M.next_id("bot", "b")
        u["balance"] = round(u["balance"] - price, 2)
        M.DB["bots"][bid] = {"owner": uid, "name": name, "username": me.get("username"), "file": str(dest),
                             "token": token, "status": "stopped", "source": source, "template": tid,
                             "admin_id": admin_id, "pid": None, "created": M.now()}
        M.save_data()
    deps(M.DB["bots"][bid])
    if not M.start_bot_process(bid):
        with LOCK:
            u["balance"] = round(u["balance"] + price, 2)
            M.DB["bots"].pop(bid, None)
            M.save_data()
        raise Err("❌ বট চালু করা যায়নি — টাকা ফেরত দেওয়া হয়েছে")


def decide(code, ok):
    with LOCK:
        pc = M.DB["payment_codes"].get(code)
        need(pc and pc["status"] == "submitted", "⚠️ আগেই প্রসেস করা হয়েছে")
        tu = M.DB["users"].get(str(pc["uid"]))
        pc["status"] = "approved" if ok else "rejected"
        if ok:
            tu["balance"] = round(tu["balance"] + pc["amount"], 2)
        pc["resolved"] = M.now()
        M.save_data()
    msg = (f"✅ <b>পেমেন্ট অ্যাপ্রুভড!</b>\n💵 যোগ হয়েছে: <code>{M.money(pc['amount'])}</code>\n"
           f"💰 নতুন ব্যালেন্স: <code>{M.money(tu['balance'])}</code>\n🔖 <code>{code}</code>") if ok else \
          f"❌ <b>পেমেন্ট রিজেক্ট করা হয়েছে</b>\n🔖 <code>{code}</code>\nসমস্যা হলে সাপোর্টে যোগাযোগ করুন।"
    tg("sendMessage", chat_id=pc["uid"], text=msg, parse_mode="HTML")


def act(uid, d):
    a, DB = d.get("a"), M.DB
    adm = uid == M.ADMIN_ID
    out = None

    def mine(bid):
        b = DB["bots"].get(bid)
        need(b and (b["owner"] == uid or adm), "বট পাওয়া যায়নি")
        return b

    def mypay(code):
        pc = DB["payment_codes"].get(code)
        need(pc and pc["uid"] == uid and pc["status"] == "created", "⚠️ কোডটি ব্যবহৃত বা এক্সপায়ার")
        return pc

    if a != "me" and a in ("pay_decide", "num_add", "num_del", "price_set", "tpl_add", "tpl_del", "tpl_price",
                           "ch_add", "ch_del", "support_set"):
        need(adm, "শুধু এডমিন পারবেন")

    if a == "me":
        pass
    elif a == "bot":
        bid, x = d.get("bid"), d.get("act")
        b = mine(bid)
        if x in ("stop", "restart", "del"):
            stop(bid)
        if x in ("start", "restart"):
            deps(b)
            need(M.start_bot_process(bid), "❌ চালু করা যায়নি")
        if x == "del":
            Path(b["file"]).unlink(missing_ok=True)
            DB["bots"].pop(bid, None)
            M.save_data()
    elif a == "logs":
        mine(d.get("bid"))
        out = M.tail_log(d["bid"], 3000)[-3300:] or "কোনো লগ নেই"
    elif a == "getcode":
        out = Path(mine(d.get("bid"))["file"]).read_text("utf-8", errors="replace")
    elif a == "savecode":
        b = mine(d.get("bid"))
        src, was = check_code(d.get("code")), b["status"] == "running"
        stop(d["bid"])
        f = Path(b["file"])
        f.write_text(src, encoding="utf-8")
        M.patch_token(f, b["token"])
        if b.get("admin_id"):
            M.patch_admin(f, b["admin_id"])
        deps(b)
        if was:
            M.start_bot_process(d["bid"])
    elif a == "deploy":
        launch(uid, str(d.get("token", "")).strip(), check_code(d.get("code")), "custom", None,
               DB["settings"]["global_price"], admin_id_of(d))
    elif a == "buy":
        t = DB["templates"].get(d.get("tid"))
        need(t and Path(t["file"]).exists(), "বট পাওয়া যায়নি")
        launch(uid, str(d.get("token", "")).strip(), Path(t["file"]).read_text("utf-8"), "market", d["tid"],
               t["price"], admin_id_of(d))
    elif a == "pay_new":
        need(DB["payment_numbers"], "⚠️ এখনো পেমেন্ট নাম্বার সেট করা হয়নি")
        for c in DB["payment_codes"].values():
            if c["uid"] == uid and c["status"] == "created":
                c["status"] = "expired"
        DB["payment_codes"][M.gen_pay_code()] = {"uid": uid, "status": "created", "amount": None, "trx": None,
                                                 "created": M.now()}
        M.save_data()
    elif a == "pay_cancel":
        mypay(d.get("code"))["status"] = "cancelled"
        M.save_data()
    elif a == "pay_submit":
        pc, code = mypay(d.get("code")), d["code"]
        amt, trx = M.parse_num(str(d.get("amount", ""))), str(d.get("trx", "")).strip()
        need(amt and amt > 0, "সঠিক পরিমাণ লিখুন")
        need(2 < len(trx) <= 64, "Transaction ID দিন")
        need(not any(c.get("trx") == trx and c["status"] in ("submitted", "approved")
                     for c in DB["payment_codes"].values()), "⚠️ এই TrxID আগেই ব্যবহৃত হয়েছে")
        pc.update({"status": "submitted", "amount": amt, "trx": trx, "submitted": M.now()})
        M.save_data()
        tg("sendMessage", chat_id=M.ADMIN_ID, text=M.pay_request_text(code), parse_mode="HTML",
           reply_markup={"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"ap:ok:{code}"},
                                              {"text": "❌ Reject", "callback_data": f"ap:no:{code}"}]]})
    elif a == "pay_decide":
        decide(d.get("code"), bool(d.get("ok")))
    elif a == "num_add":
        m_, n_ = str(d.get("method", "")).strip(), str(d.get("number", "")).strip()
        need(m_ and n_, "মেথড ও নাম্বার দিন")
        DB["payment_numbers"].append({"id": f"w{time.time_ns() % 10**9}", "method": m_[:20], "number": n_[:80]})
        M.save_data()
    elif a == "num_del":
        DB["payment_numbers"][:] = [n for n in DB["payment_numbers"] if n["id"] != d.get("id")]
        M.save_data()
    elif a == "price_set":
        p = M.parse_num(str(d.get("price", "")))
        need(p is not None, "সঠিক দাম লিখুন")
        DB["settings"]["global_price"] = p
        M.save_data()
    elif a == "tpl_add":
        name, p = str(d.get("name", "")).strip(), M.parse_num(str(d.get("price", "")))
        need(name and p is not None, "নাম ও দাম দিন")
        src = check_code(d.get("code"))
        M.TEMPLATES_DIR.mkdir(exist_ok=True)
        tid = M.next_id("tpl", "t")
        dest = M.TEMPLATES_DIR / f"{tid}.py"
        dest.write_text(src, encoding="utf-8")
        DB["templates"][tid] = {"name": name[:60], "price": p, "desc": str(d.get("desc", "")).strip()[:300],
                                "file": str(dest), "created": M.now()}
        M.save_data()
    elif a == "tpl_del":
        t = DB["templates"].pop(d.get("tid"), None)
        need(t, "বট পাওয়া যায়নি")
        Path(t["file"]).unlink(missing_ok=True)
        M.save_data()
    elif a == "tpl_price":
        p = M.parse_num(str(d.get("price", "")))
        need(p is not None and d.get("tid") in DB["templates"], "সঠিক দাম লিখুন")
        DB["templates"][d["tid"]]["price"] = p
        M.save_data()
    elif a == "ch_add":
        ch = str(d.get("ch", "")).strip()
        ch = ch if ch.startswith("@") else "@" + ch
        need(re.fullmatch(r"@\w{4,}", ch), "@channel ফরম্যাটে দিন")
        if ch not in DB["channel_lock"]:
            DB["channel_lock"].append(ch)
        M.save_data()
    elif a == "ch_del":
        DB["channel_lock"][:] = [c for c in DB["channel_lock"] if c != d.get("ch")]
        M.save_data()
    elif a == "support_set":
        DB["settings"]["support"] = str(d.get("support", "")).strip()[:100]
        M.save_data()
    else:
        raise Err("অজানা অ্যাকশন")
    return out


def state(uid):
    DB, adm = M.DB, uid == M.ADMIN_ID
    u = DB["users"][str(uid)]
    s = {
        "me": {"id": uid, "name": u["name"], "balance": u["balance"], "admin": adm},
        "price": DB["settings"]["global_price"], "support": DB["settings"].get("support", ""),
        "channels": DB["channel_lock"], "nums": DB["payment_numbers"],
        "bots": [{"id": i, "name": b["name"], "status": b["status"], "source": b["source"], "created": b["created"]}
                 for i, b in DB["bots"].items() if b["owner"] == uid],
        "tpls": [{"id": i, "name": t["name"], "price": t["price"], "desc": t.get("desc", ""),
                  "sold": sum(1 for b in DB["bots"].values() if b.get("template") == i)}
                 for i, t in DB["templates"].items()],
        "pays": [{"code": c, "status": p["status"], "amount": p.get("amount"), "created": p["created"]}
                 for c, p in DB["payment_codes"].items() if p["uid"] == uid and p["status"] != "expired"][-15:],
    }
    if adm:
        bots = DB["bots"].values()
        s["adm"] = {
            "users": len(DB["users"]), "bots": len(DB["bots"]),
            "running": sum(1 for b in bots if b["status"] == "running"),
            "deposit": sum(p["amount"] for p in DB["payment_codes"].values() if p["status"] == "approved"),
            "pending": [{"code": c, "name": DB["users"].get(str(p["uid"]), {}).get("name", "?"), "uid": p["uid"],
                         "amount": p["amount"], "trx": p["trx"]}
                        for c, p in DB["payment_codes"].items() if p["status"] == "submitted"],
        }
    return s


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype, head=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _get(self, head):
        if self.path.split("?")[0] in ("/", "/index.html", "/app"):
            f = HERE / "index.html"
            if f.exists():
                return self._send(200, f.read_bytes(), "text/html; charset=utf-8", head)
        self._send(200, b"OK - hosting platform is running", "text/plain; charset=utf-8", head)

    def do_GET(self):
        self._get(False)

    def do_HEAD(self):
        self._get(True)

    def do_POST(self):
        if self.path.split("?")[0] != "/api":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > 3_000_000:
            return self._json(413, {"error": "ডাটা অনেক বড়"})
        raw = self.rfile.read(n)
        user = verify(self.headers.get("X-Init-Data", ""))
        if not user:
            return self._json(401, {"error": "auth"})
        try:
            d = json.loads(raw or b"{}")
            uid = int(user["id"])
            with LOCK:
                M.get_user(SimpleNamespace(id=uid, username=user.get("username"),
                                           full_name=(user.get("first_name", "") + " " + user.get("last_name", "")).strip() or str(uid)))
            gate = missing(uid)
            if gate:
                return self._json(200, {"gate": gate})
            out = act(uid, d)
            self._json(200, {"ok": True, "data": out, "state": state(uid)})
        except Err as e:
            self._json(400, {"error": str(e)})
        except Exception:
            M.log.exception("api error")
            self._json(500, {"error": "সার্ভারে সমস্যা হয়েছে, আবার চেষ্টা করুন"})

    def log_message(self, *a):
        pass


def start(bot_module) -> bool:
    """Render এর PORT এ সার্ভার চালু করে। চালু হলে True।"""
    global M
    import os
    M = bot_module
    port = os.getenv("PORT")
    if not port:
        return False
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", int(port)), H)
    except Exception as e:
        M.log.warning("webapp start failed: %s", e)
        return False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    M.log.info("🌐 Web App listening on port %s", port)
    return True
