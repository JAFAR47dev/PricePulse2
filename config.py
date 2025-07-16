import os
from dotenv import load_dotenv
load_dotenv()

ADMIN_ID = int(os.getenv("ADMIN_ID"))
TAAPI_KEY = os.getenv("TAAPI_KEY")
CRYPTO_PANIC_API_KEY = os.getenv("CRYPTO_PANIC_API_KEY")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")
TELEGRAM_BOT_TOKEN= os.getenv("TELEGRAM_BOT_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")


DB_FILE = "data/alerts.db"