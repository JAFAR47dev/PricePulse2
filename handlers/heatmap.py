import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

async def heatmap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/hmap")
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
        response = requests.get(url, params=params, timeout=10)
        coins = response.json()

        # Filter out broken API entries
        coins = [c for c in coins if "symbol" in c and c.get("price_change_percentage_24h") is not None]

        # 2️⃣ HD Image Canvas
        WIDTH = 680
        HEIGHT = 450
        img = Image.new("RGB", (WIDTH, HEIGHT), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)

        # 3️⃣ Safe Font Loader
        def load_font(size):
            try:
                return ImageFont.truetype("arial.ttf", size)
            except:
                return ImageFont.load_default()

        font_large = load_font(60)
        font_small = load_font(40)

        cols = 5
        rows = 10  # Because 50 coins, 5 per row
        cell_w = WIDTH // cols
        cell_h = HEIGHT // rows

        # Text size helper
        def get_text_size(text, font):
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except:
                return draw.textsize(text, font=font)

        for i, coin in enumerate(coins):
            x = (i % cols) * cell_w
            y = (i // cols) * cell_h

            price_change = coin["price_change_percentage_24h"]

            # Stronger color gradient
            if price_change > 8:
                color = (0, 200, 0)
            elif price_change > 0:
                color = (0, 140, 0)
            elif price_change < -8:
                color = (220, 0, 0)
            elif price_change < 0:
                color = (160, 0, 0)
            else:
                color = (80, 80, 80)

            # Draw cell box
            margin = 6
            draw.rectangle(
                [x + margin, y + margin, x + cell_w - margin, y + cell_h - margin],
                fill=color
            )

            # Text
            symbol = coin["symbol"].upper()
            pct = f"{price_change:+.1f}%"

            # Center alignment
            symbol_w, symbol_h = get_text_size(symbol, font_large)
            pct_w, pct_h = get_text_size(pct, font_small)

            symbol_x = x + (cell_w - symbol_w) // 2
            symbol_y = y + (cell_h // 2) - symbol_h

            pct_x = x + (cell_w - pct_w) // 2
            pct_y = symbol_y + symbol_h + 5

            # Draw text
            draw.text((symbol_x, symbol_y), symbol, fill="white", font=font_large)
            draw.text((pct_x, pct_y), pct, fill="white", font=font_small)

        # 4️⃣ Send image
        image_stream = BytesIO()
        img.save(image_stream, format="PNG")
        image_stream.seek(0)

        await update.message.reply_photo(
            photo=InputFile(image_stream, filename="heatmap.png"),
            caption="💹 *Market Heatmap of Top 50 Coins* — 24h Change",
            parse_mode="Markdown"
        )

    except Exception as e:
        print("Heatmap error:", e)
        await update.message.reply_text("⚠️ Couldn't generate heatmap. Try again later.")