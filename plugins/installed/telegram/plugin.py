"""
Plugin wrapper so the loader/manager can discover the Telegram bot.
The bot itself still runs as its own polling process - see
telegram_bot.py's main(). register() just confirms config is present;
it does not start polling (that would block the main Ultron process).
"""

from plugins.sdk.base import UltronPlugin
from config import TELEGRAM_BOT_TOKEN


class TelegramPlugin(UltronPlugin):
    name = "telegram"

    def register(self, brain) -> None:
        if not TELEGRAM_BOT_TOKEN:
            print(
                "[telegram plugin] TELEGRAM_BOT_TOKEN not set - run "
                "plugins/installed/telegram/telegram_bot.py directly once configured."
            )
            return
        print(
            "[telegram plugin] Configured. Run " "'python plugins/installed/telegram/telegram_bot.py' to start polling."
        )


PLUGIN = TelegramPlugin()
