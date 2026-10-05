import os
import telebot
import yt_dlp
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running!"

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 Welcome! Link পাঠান, Download করে দিবো।")

@bot.message_handler(func=lambda m: "http" in m.text)
def download(m):
    url = m.text.strip()
    wait = bot.reply_to(m, "⏳ Downloading...")
    opts = {'format': 'best[ext=mp4]/best','outtmpl': 'video.%(ext)s','noplaylist': True,'quiet': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file = ydl.prepare_filename(info)
        with open(file, 'rb') as f:
            bot.send_video(m.chat.id, f, caption=info.get('title'))
        bot.delete_message(m.chat.id, wait.message_id)
        os.remove(file)
    except Exception as e:
        bot.edit_message_text(f"❌ {e}", m.chat.id, wait.message_id)

def run_bot():
    bot.infinity_polling()

threading.Thread(target=run_bot).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
