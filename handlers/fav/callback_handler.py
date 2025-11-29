# handlers/fav/callback_handler.py

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from handlers.fav.utils.db_favorites import add_favorite, remove_favorite, get_favorites
from handlers.fav.utils.fav_prices import get_fav_prices 

async def fav_callback_handler(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # Step 1 — User chose "Add Favorite"
    if data == "fav_add":
        await query.message.reply_text("Send the coin symbol to *add* (e.g., BTC):", parse_mode="Markdown")
        context.user_data["fav_mode"] = "add"
        return
    
    if data == "fav_remove":
        await query.message.reply_text("Send the coin symbol to *remove* (e.g., ETH):", parse_mode="Markdown")
        context.user_data["fav_mode"] = "remove"
        return

    if data == "fav_list":
        favs = get_favorites(user_id)
        if not favs:
            await query.message.reply_text("⭐ You have no favorites yet.")
        else:
            msg = "⭐ *Your Favorite Coins:*\n" + "\n".join(f"• {x}" for x in favs)
            await query.message.reply_text(msg, parse_mode="Markdown")
        return

    # =============================
    # FAVORITES PRICE LIST HANDLER
    # =============================
    if data == "fav_prices":
        favs = get_favorites(user_id)

        if not favs:
            await query.message.reply_text("❌ No favorites saved.")
            return

        # Start with page 0
        await query.message.edit_text(
            "⏳ Loading your favorite prices...",
            parse_mode="Markdown"
        )

        await query.message.edit_reply_markup(None)

        # Trigger pagination callback
        await query.message.bot.send_message(
            chat_id=user_id,
            text="💰 *Favorite Coin Prices:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 View Prices", callback_data="fav_prices_page_0")]
            ])
        )



    # =============================
    # PAGINATION HANDLER
    # =============================
    elif data.startswith("fav_prices_page_"):

        page = int(data.split("_")[-1])
        per_page = 3 # 3 coins per page

        favs = get_favorites(user_id)
        total = len(favs)

        if total == 0:
            await query.message.edit_text("❌ No favorites saved.")
            return

        # Slice
        start = page * per_page
        end = start + per_page
        page_items = favs[start:end]

        # --- Fetch all prices in one batch ---
        results = get_fav_prices(page_items)

        # Build message
        max_page = (total - 1) // per_page
        msg = f"💰 *Favorite Coin Prices*\n_Page {page + 1} of {max_page + 1}_\n\n"

        for sym in page_items:
            coin = results.get(sym)

            if not coin:
                msg += f"*{sym.upper()}*\n• ❌ Error fetching data\n\n"
                continue

            price = coin["price"]
            percent = coin["percent"]
            trend = coin["trend"]
            rank = coin["rank"]
            rsi = coin["rsi"]

            emoji = "🟢" if percent >= 0 else "🔴"

            msg += (
                f"*{sym.upper()}*\n"
                f"• Price: ${price}\n"
                f"• 24h: {emoji} {percent}%\n"
                f"• Trend: {trend}\n"
                f"• Rank: #{rank}\n"
                f"• RSI: {rsi}\n\n"
            )

        # Pagination buttons
        buttons = []

        # Previous page
        if start > 0:
            buttons.append(
                InlineKeyboardButton("⬅ Prev", callback_data=f"fav_prices_page_{page - 1}")
            )

        # Next page
        if end < total:
            buttons.append(
                InlineKeyboardButton("Next ➡", callback_data=f"fav_prices_page_{page + 1}")
            )

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

        await query.message.edit_text(
            msg,
            parse_mode="Markdown",
        reply_markup=keyboard
        )
        
       