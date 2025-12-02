# handlers/fav/fav_handler.py
import traceback
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, filters
from handlers.fav.utils.db_favorites import add_favorite, remove_favorite, get_favorites

async def fav_command(update, context):
    
    context.user_data.pop("alert_flow", None)
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Prices", callback_data="fav_prices"),
            InlineKeyboardButton("➕ Add Favorite", callback_data="fav_add")
        ],
        [
            InlineKeyboardButton("📋 List Favorites", callback_data="fav_list"),
            InlineKeyboardButton("➖ Remove Favorite", callback_data="fav_remove")
        ]
    ]

    await update.message.reply_text(
        "⭐ *Favorites Menu* — choose an action:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def fav_text_handler(update, context):
    try:
        
        print("DEBUG fav_text_handler called; user_data:", context.user_data)

        
        fav_mode = context.user_data.get("fav_mode")
    
        if context.user_data.get("alert_flow") or fav_mode is None:
            return
        
        symbol = update.message.text.strip().upper()
        user_id = update.effective_user.id

        # -------------------------
        # ADD FAVORITE
        # -------------------------
        if fav_mode == "add":
            try:
                success = add_favorite(user_id, symbol)
            except Exception as e:
                print("ERROR adding favorite:", e)
                traceback.print_exc()
                await update.message.reply_text(
                    "❌ Could not add favorite due to an internal error. Try again later."
                )
            else:
                if success:
                    await update.message.reply_text(
                        f"✅ Added *{symbol}* to favorites!",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ *{symbol}* is already in your favorites.",
                        parse_mode="Markdown"
                    )

        # -------------------------
        # REMOVE FAVORITE
        # -------------------------
        elif fav_mode == "remove":
            try:
                success = remove_favorite(user_id, symbol)
            except Exception as e:
                print("ERROR removing favorite:", e)
                traceback.print_exc()
                await update.message.reply_text(
                    "❌ Could not remove favorite due to an internal error. Try again later."
                )
            else:
                if success:
                    await update.message.reply_text(
                        f"❌ Removed *{symbol}* from favorites.",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ *{symbol}* was not in your favorites.",
                        parse_mode="Markdown"
                    )

        # Clear after processing
        context.user_data.pop("fav_mode", None)
        context.user_data.pop("fav_mode_since", None)

    except Exception as e:
        print("Unexpected error in fav_text_handler:", e)
        traceback.print_exc()
        try:
            await update.message.reply_text("❌ Unexpected error. Try again later.")
        except Exception:
            pass

        # Always clear mode on exception also
        context.user_data.pop("fav_mode", None)
        context.user_data.pop("fav_mode_since", None)