# Communication skills

| Tool | Module |
|---|---|
| send_message, send_template, send_media, mark_as_read | skills/communication/whatsapp.py (`WhatsAppClient` - Meta WhatsApp Business Cloud API) |
| send_message, send_photo, send_document, get_updates, get_chat_id_from_updates | skills/communication/telegram.py (`TelegramClient` - outbound REST wrapper) |
| send_sms, get_message_status, list_recent_messages | skills/communication/sms.py (`SMSClient` - Twilio) |

`telegram.py` is a lightweight *outbound* wrapper (push a notification/report
from any skill). It's separate from `plugins/installed/telegram/telegram_bot.py`,
which runs the full two-way bot Application for controlling Ultron remotely -
use that one for interactive remote control, this one for one-off pushes.
