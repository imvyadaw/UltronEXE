"""
Telegram Bot for Ultron
========================
Control Ultron remotely via Telegram messages.
Run standalone: python plugins/installed/telegram/telegram_bot.py
"""

import tempfile
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from ai.router import get_client
from config import TELEGRAM_BOT_TOKEN


class TelegramUltron:
    """Telegram bot interface for Ultron."""

    def __init__(self):
        self.client = get_client()
        self.voice_enabled = True

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "ULTRON Online\n\n"
            "Good day, Sir. I'm now connected and ready to assist.\n\n"
            "Simply send me a message and I'll help you control your system.\n\n"
            "Commands:\n"
            "/voice - Toggle voice responses\n"
            "/clear - Clear conversation history",
            parse_mode="Markdown",
        )

    async def voice_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.voice_enabled = not self.voice_enabled
        status = "enabled" if self.voice_enabled else "disabled"
        await update.message.reply_text(f"Voice responses {status}, Sir.")

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.client.clear_history()
        await update.message.reply_text("Conversation history cleared, Sir.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_message = update.message.text

        if not user_message:
            return

        await update.message.chat.send_action("typing")

        try:
            response = self.client.chat_with_tools(user_message)
            await update.message.reply_text(f"{response}")

            if self.voice_enabled and response:
                await self._send_voice(update, response)

        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")

    async def _send_voice(self, update: Update, text: str):
        try:
            import edge_tts

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+0%")
            await communicate.save(tmp_path)

            with open(tmp_path, "rb") as audio:
                await update.message.reply_voice(audio)

            os.unlink(tmp_path)

        except Exception as e:
            print(f"Voice error: {e}")


def main():
    """Run the Telegram bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not found in .env file!")
        print("Add: TELEGRAM_BOT_TOKEN=your_token_here")
        return

    print("Starting Ultron Telegram Bot...")

    ultron = TelegramUltron()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", ultron.start_command))
    app.add_handler(CommandHandler("voice", ultron.voice_command))
    app.add_handler(CommandHandler("clear", ultron.clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ultron.handle_message))

    print("ULTRON Telegram Bot is online!")
    print("Send a message to your bot to get started.")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
