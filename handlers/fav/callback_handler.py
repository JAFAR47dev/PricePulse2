# handlers/fav/callback_handler.py
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from handlers.fav.utils.db_favorites import add_favorite, remove_favorite, get_favorites
from handlers.fav.utils.fav_prices import get_fav_prices 
from telegram.error import BadRequest
from models.user import get_user_plan
from utils.auth import is_pro_plan

async def safe_edit(query, text=None, reply_markup=None, parse_mode="Markdown"):
    """
    Instead of editing the original message (which removes the menu),
    this function now REPLIES with a new message so the menu stays visible.
    """
    try:
        await query.answer()  # Removes the "loading…" spinner

        # Always reply with a new message (NO editing)
        if text:
            await query.message.reply_text(
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
        elif reply_markup:
            await query.message.reply_text(
                "Select an option:",
                reply_markup=reply_markup
            )

    except Exception as e:
        print("safe_edit error:", e)
        
            
async def fav_callback_handler(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    
        
    # Step 1 — User chose "Add Favorite"
    if data == "fav_add":
        user_id = update.effective_user.id
        plan = get_user_plan(user_id)

        # Get existing favorites count
        current_favs = get_favorites(user_id)
        fav_count = len(current_favs)

        # Restrict Free users to max 5 favorites
        if not is_pro_plan(plan) and fav_count >= 5:
            await query.message.reply_text(
                "🔒 *Favorite Limit Reached*\n\n"
                "Free users can only save up to *5 favorites*.\n"
                "Upgrade to Pro to unlock unlimited favorites.\n\n"
                "👉 /upgrade",
                parse_mode="Markdown"
            )
            return

        # Continue normally
        await query.message.reply_text(
            "Send the coin symbol to *add* (e.g., BTC):",
            parse_mode="Markdown"
        )
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

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # --- Step 1: Fetch full market data for ALL favorites ---
        full_results = await get_fav_prices(favs)

        sorted_favs = sorted(
            favs,
            key=lambda sym: full_results.get(sym, {}).get("rank", 999999)
        )

        # --- Step 3: Pagination after sorting ---
        page = 0
        per_page = 3
        total = len(sorted_favs)

        start = page * per_page
        end = start + per_page
        page_items = sorted_favs[start:end]

        max_page = (total - 1) // per_page

        msg = (
            f"💰 *Favorite Coin Prices*\n"
            f"_Page {page + 1} of {max_page + 1}_\n\n"
        )

        for sym in page_items:
            coin = full_results.get(sym)

            if not coin:
                msg += f"*{sym.upper()}*\n• ❌ Error fetching data\n\n"
                continue

            price = coin["price"]
            percent = coin["percent"]
            trend = coin["trend"]
            rank = coin["rank"]

            emoji = "🟢" if percent >= 0 else "🔴"

            msg += (
                f"*{sym.upper()}*\n"
                f"• Price: ${price}\n"
                f"• 24h: {emoji} {percent}%\n"
                f"• Trend: {trend}\n"
                f"• Rank: #{rank}\n\n"
            )
        

        # Pagination buttons
        buttons = []
        if end < total:
            buttons.append(
                InlineKeyboardButton("Next ➡", callback_data="fav_prices_page_1")
            )

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

        # Replace the "Loading" message with the actual prices
        await safe_edit(
            query,
            msg,
            parse_mode="Markdown",
            reply_markup=keyboard
        )



    # =============================
    # PAGINATION HANDLER
    # =============================
    elif data.startswith("fav_prices_page_"):

        page = int(data.split("_")[-1])
        per_page = 3

        favs = get_favorites(user_id)
        total = len(favs)

        if total == 0:
            await safe_edit(query, "❌ No favorites saved.")
            return

        start = page * per_page
        end = start + per_page
        page_items = favs[start:end]

        results = await get_fav_prices(page_items)

        max_page = (total - 1) // per_page

        msg = (
            f"💰 *Favorite Coin Prices*\n"
            f"_Page {page + 1} of {max_page + 1}_\n\n"
        )

        for sym in page_items:
            coin = results.get(sym)

            if not coin:
                msg += f"*{sym.upper()}*\n• ❌ Error fetching data\n\n"
                continue

            price = coin["price"]
            percent = coin["percent"]
            trend = coin["trend"]
            rank = coin["rank"]

            emoji = "🟢" if percent >= 0 else "🔴"

            msg += (
                f"*{sym.upper()}*\n"
                f"• Price: ${price}\n"
                f"• 24h: {emoji} {percent}%\n"
                f"• Trend: {trend}\n"
                f"• Rank: #{rank}\n\n"
         
            )

        # Pagination buttons
        buttons = []
        if start > 0:
            buttons.append(
                InlineKeyboardButton("⬅ Prev", callback_data=f"fav_prices_page_{page - 1}")
            )
        if end < total:
            buttons.append(
                InlineKeyboardButton("Next ➡", callback_data=f"fav_prices_page_{page + 1}")
            )

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

       
        await query.edit_message_text(
            text=msg,
            parse_mode="Markdown",
            reply_markup=keyboard
        )