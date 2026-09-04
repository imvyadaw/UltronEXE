"""Communication automations: WhatsApp, Telegram, Signal, Slack, Discord, Messenger, Skype."""

from apps.communication.whatsapp import WhatsAppApp
from apps.communication.telegram import TelegramApp
from apps.communication.signal import SignalApp
from apps.communication.slack import SlackApp
from apps.communication.discord import DiscordApp
from apps.communication.messenger import MessengerApp
from apps.communication.skype import SkypeApp

__all__ = ["WhatsAppApp", "TelegramApp", "SignalApp", "SlackApp", "DiscordApp", "MessengerApp", "SkypeApp"]
