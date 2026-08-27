import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
DB_PATH = os.getenv("DB_PATH", "bot.db")

IMAP_EMAIL = os.getenv("IMAP_EMAIL")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

CODE_TIMEOUT = int(os.getenv("CODE_TIMEOUT", "180"))
POLL_INTERVAL = 10
SPAM_LIMIT = int(os.getenv("SPAM_LIMIT", "3"))
SPAM_WINDOW = int(os.getenv("SPAM_WINDOW", str(30 * 60)))

# Прокси для доступа к Telegram Bot API (нужен, если сервер в РФ).
# Формат: socks5://host:port или socks5://user:pass@host:port
# Пусто/не задано -- бот подключается к Telegram напрямую, без прокси.
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip() or None

# GGsel / Digiseller Seller API -- для проверки номера заказа перед выдачей кода.
# id продавца: https://my.digiseller.com/inside/my_info.asp
# api-ключ:    https://my.digiseller.com/inside/api_keys.asp
GGSEL_SELLER_ID = os.getenv("GGSEL_SELLER_ID", "").strip() or None
GGSEL_API_KEY = os.getenv("GGSEL_API_KEY", "").strip() or None
