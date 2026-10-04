import os
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# -------------------------------------------------------------
# ১. লগিং কনফিগারেশন
# -------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# ২. Render Health Check Server (বট সচল রাখার জন্য)
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("Render Telegram Bot is active and running!".encode('utf-8'))

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Web server running on port {port}")
    server.serve_forever()

# -------------------------------------------------------------
# ৩. প্রোডাক্ট ও রিসেলার ডাটা (স্যাম্পল)
# -------------------------------------------------------------
PRODUCTS = {
    "1": {"name": "ডিজিটাল এআই কোর্স", "price": 500, "commission": 100},
    "2": {"name": "প্রিমিয়াম অ্যাকাউন্ট", "price": 300, "commission": 50}
}

# -------------------------------------------------------------
# ৪. বটের হ্যান্ডলারসমূহ
# -------------------------------------------------------------

# /start কমান্ড
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    
    keyboard = [
        [
            InlineKeyboardButton("🤖 AI চ্যাটবট", callback_data='ai_mode'),
            InlineKeyboardButton("🛍️ শপ / ডিজিটাল সেলার", callback_data='shop_mode')
        ],
        [
            InlineKeyboardButton("💼 রিসেলিং প্যানেল", callback_data='resell_mode'),
            InlineKeyboardButton("ℹ️ বট তথ্য", callback_data='info_mode')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"স্বাগতম {user_name}! 👋\n\nএটি আপনার Render-এ চালিত All-in-One টেস্ট বট। নিচের অপশনগুলো থেকে টেস্ট করুন:",
        reply_markup=reply_markup
    )

# ইনলাইন বাটন হ্যান্ডলার
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'ai_mode':
        await query.edit_message_text(
            "🤖 **AI চ্যাটবট মোড চালু আছে!**\n\n"
            "আমাকে যেকোনো প্রশ্ন লিখে মেসেজ পাঠান, আমি উত্তর দেব।"
        )
    
    elif query.data == 'shop_mode':
        keyboard = [
            [InlineKeyboardButton("📘 ডিজিটাল কোর্স (৫০০ টাকা)", callback_data='buy_1')],
            [InlineKeyboardButton("⭐ প্রিমিয়াম অ্যাকাউন্ট (৩০০ টাকা)", callback_data='buy_2')],
            [InlineKeyboardButton("🔙 প্রধান মেনু", callback_data='main_menu')]
        ]
        await query.edit_message_text(
            "🛒 **ডিজিটাল শপ ক্যাটালগ:**\n\nযে পণ্যটি সম্পর্কে জানতে চান বা কিনতে চান তা সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'resell_mode':
        text = (
            "💼 **রিসেলিং প্যানেল:**\n\n"
            "আমাদের ডিজিটাল প্রোডাক্ট রিসেল করে কমিশন পান:\n"
            "• ডিজিটাল কোর্স: ১০০ টাকা কমিশন\n"
            "• প্রিমিয়াম অ্যাকাউন্ট: ৫০ টাকা কমিশন\n\n"
            "আপনার রেফারেল আইডি থেকে সেল হলে পয়েন্ট যোগ হবে।"
        )
        keyboard = [[InlineKeyboardButton("🔙 প্রধান মেনু", callback_data='main_menu')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith('buy_'):
        prod_id = query.data.split('_')[1]
        prod = PRODUCTS.get(prod_id)
        if prod:
            msg = f"✅ **অর্ডার নির্বাচন করা হয়েছে:**\n\nপণ্য: {prod['name']}\nমূল্য: {prod['price']} টাকা\n\nপেমেন্ট সম্পন্ন করতে এডমিনের সাথে যোগাযোগ করুন।"
            keyboard = [[InlineKeyboardButton("🔙 শপে ফিরে যান", callback_data='shop_mode')]]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'info_mode':
        await query.edit_message_text("ℹ️ **বট তথ্য:**\n\nহোস্টিং: Render Free Tier\nভাষা: Python 3\nলাইব্রেরি: python-telegram-bot v20+")

    elif query.data == 'main_menu':
        keyboard = [
            [
                InlineKeyboardButton("🤖 AI চ্যাটবট", callback_data='ai_mode'),
                InlineKeyboardButton("🛍️ শপ / ডিজিটাল সেলার", callback_data='shop_mode')
            ],
            [
                InlineKeyboardButton("💼 রিসেলিং প্যানেল", callback_data='resell_mode'),
                InlineKeyboardButton("ℹ️ বট তথ্য", callback_data='info_mode')
            ]
        ]
        await query.edit_message_text("প্রধান মেনু:", reply_markup=InlineKeyboardMarkup(keyboard))

# টেক্সট মেসেজ ও এআই রেসপন্স
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    # টেস্ট এআই উত্তর (এখানে আসল OpenAI/Gemini API যুক্ত করা যাবে)
    ai_reply = f"🤖 [AI Test Response]: আপনি বলেছেন '{user_text}'। বটটি Render-এ সঠিকভাবে কাজ করছে!"
    await update.message.reply_text(ai_reply)

# ছবি প্রসেসিং
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 চমৎকার! আপনার পাঠানো ছবিটি রিসিভ করা হয়েছে।")

# এরর হ্যান্ডলার
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception occurred:", exc_info=context.error)

# -------------------------------------------------------------
# ৫. মূল প্রোগ্রাম শুরু
# -------------------------------------------------------------
def main():
    token = os.environ.get("BOT_TOKEN")
    
    if not token:
        logger.error("Error: BOT_TOKEN Environment Variable সেট করা নেই!")
        return

    # ব্যাকগ্রাউন্ড ওয়েব সার্ভার
    Thread(target=run_web_server, daemon=True).start()

    # অ্যাপ্লিকেশন তৈরি
    app = ApplicationBuilder().token(token).build()

    # হ্যান্ডলার যুক্ত করা
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    app.add_error_handler(error_handler)

    logger.info("Bot starting on Render...")
    app.run_polling()

if __name__ == '__main__':
    main()
