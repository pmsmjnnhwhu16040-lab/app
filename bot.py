import os
import telebot
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 Welcome!\nYouTube / TikTok / FB link পাঠান, আমি ডাউনলোড করে দিবো।")

@bot.message_handler(func=lambda m: "http" in m.text)
def download(m):
    url = m.text.strip()
    wait = bot.reply_to(m, "⏳ Downloading...")
    
    opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'video.%(ext)s',
        'noplaylist': True,
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file = ydl.prepare_filename(info)
        
        with open(file, 'rb') as f:
            bot.send_video(m.chat.id, f, caption=info.get('title'))
        
        bot.delete_message(m.chat.id, wait.message_id)
        os.remove(file)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", m.chat.id, wait.message_id)

print("Bot Running...")
bot.infinity_polling()
