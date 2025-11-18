import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak

async def heatmap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    try:
        # 1️⃣ Fetch top 50 coins by market cap
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 50,
            "page": 1,
            "sparkline": "false"
        }
        response = requests.get(url, params=params)
        coins = response.json()

        # 2️⃣ Create image
        img = Image.new("RGB", (1080, 720), color="black")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 42)
            small_font = ImageFont.truetype("arial.ttf", 32)
        except:
            font = ImageFont.load_default()
            small_font = font

        cols = 5
        cell_w = img.width // cols
        cell_h = img.height // (len(coins) // cols + 1)

        # ✅ Helper function to get text width & height safely
        def get_text_size(text, font):
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
            except AttributeError:  # For older Pillow versions
                w, h = draw.textsize(text, font=font)
            return w, h

        for i, coin in enumerate(coins):
            x = (i % cols) * cell_w
            y = (i // cols) * cell_h

            price_change = coin["price_change_percentage_24h"]
            color = (
                (0, 180, 0) if price_change > 0 else
                (200, 0, 0) if price_change < 0 else
                (100, 100, 100)
            )

            box_margin = 5
            draw.rectangle(
                [x + box_margin, y + box_margin, x + cell_w - box_margin, y + cell_h - box_margin],
                fill=color
            )

            # Text content
            symbol = coin["symbol"].upper()
            pct = f"{price_change:+.1f}%" if price_change else "0.0%"

            # Center alignment using textbbox
            symbol_w, symbol_h = get_text_size(symbol, font)
            pct_w, pct_h = get_text_size(pct, small_font)

            symbol_x = x + (cell_w - symbol_w) / 2
            symbol_y = y + (cell_h / 2) - symbol_h
            pct_x = x + (cell_w - pct_w) / 2
            pct_y = symbol_y + symbol_h + 5

            draw.text((symbol_x, symbol_y), symbol, fill="white", font=font)
            draw.text((pct_x, pct_y), pct, fill="white", font=small_font)

        # 3️⃣ Send image
        image_stream = BytesIO()
        img.save(image_stream, format="PNG")
        image_stream.seek(0)

        await update.message.reply_photo(
            photo=InputFile(image_stream, filename="heatmap.png"),
            caption="💹 *Market Heatmap of Top 50 Coins* — 24h % change",
            parse_mode="Markdown"
        )

    except Exception as e:
        print("Heatmap error:", e)
        await update.message.reply_text("⚠️ Couldn't generate heatmap. Try again later.")