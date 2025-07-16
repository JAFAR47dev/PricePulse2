# handlers/heatmap.py
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InputFile
from telegram.ext import ContextTypes

async def heatmap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # 1. Fetch top 100 coins by market cap
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 50,  # Only top 50 for visual simplicity
            "page": 1,
            "sparkline": "false"
        }
        response = requests.get(url, params=params)
        coins = response.json()

        # 2. Create image
        img = Image.new("RGB", (1080, 720), color="black")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()

        cols = 5
        cell_w = img.width // cols
        cell_h = img.height // (len(coins) // cols + 1)

        for i, coin in enumerate(coins):
            x = (i % cols) * cell_w
            y = (i // cols) * cell_h

            price_change = coin["price_change_percentage_24h"]
            color = (
                (0, 200, 0) if price_change > 0 else
                (200, 0, 0) if price_change < 0 else
                (100, 100, 100)
            )

            box_margin = 5
            draw.rectangle(
                [x + box_margin, y + box_margin, x + cell_w - box_margin, y + cell_h - box_margin],
                fill=color
            )

            symbol = coin["symbol"].upper()
            pct = f"{price_change:+.1f}%" if price_change else "0.0%"
            label = f"{symbol}\n{pct}"

            draw.text((x + 12, y + 10), label, fill="white", font=font)

        # 3. Send image
        image_stream = BytesIO()
        img.save(image_stream, format="PNG")
        image_stream.seek(0)

        await update.message.reply_photo(photo=InputFile(image_stream, filename="heatmap.png"),
                                         caption="💹 *Market Heatmap of Top 50 Coins* — 24h % change",
                                         parse_mode="Markdown")

    except Exception as e:
        print("Heatmap error:", e)
        await update.message.reply_text("⚠️ Couldn't generate heatmap. Try again later.")