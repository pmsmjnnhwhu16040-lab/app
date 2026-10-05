import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Welcome to Media Downloader Bot!\n\n"
        "Just send me any YouTube / TikTok / Facebook / Instagram link."
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "http" not in url:
        await update.message.reply_text("❌ Please send a valid link.")
        return

    wait_msg = await update.message.reply_text("⏳ Downloading... Please wait")

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

        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=open(file, 'rb'),
            caption=f"✅ {info.get('title')}"
        )
        await wait_msg.delete()
        os.remove(file)

    except Exception as e:
        await wait_msg.edit_text(f"❌ Failed: {e}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
app.run_polling()
