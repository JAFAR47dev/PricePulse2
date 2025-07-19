# handlers/gasfees.py
import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

async def gasfees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = "https://api.etherscan.io/api"
        params = {
            "module": "gastracker",
            "action": "gasoracle",
            "apikey": ETHERSCAN_API_KEY
        }

        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        if data["status"] != "1":
            raise Exception("Etherscan error")

        result = data["result"]
        low = result["SafeGasPrice"]
        avg = result["ProposeGasPrice"]
        high = result["FastGasPrice"]

        text = (
            f"⛽ *Ethereum Gas Fees*\n\n"
            f"• Low: `{low}` Gwei (safe, slow)\n"
            f"• Standard: `{avg}` Gwei (avg)\n"
            f"• High: `{high}` Gwei (fast)\n\n"
            f"🔍 _Powered by Etherscan_"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Gas fees error:", e)
        await update.message.reply_text("⚠️ Couldn't fetch gas fees. Try again later.")