# handlers/fav/fav_handler.py
import traceback
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, filters
from handlers.fav.utils.db_favorites import add_favorite, remove_favorite, get_favorites
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

async def fav_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/fav")
    await handle_streak(update, context)
    
    
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
        
        
        fav_mode = context.user_data.get("fav_mode")
    
        # Early return if not in fav mode or if alert flow is active
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
            
            # ✅ ADDED: Clear fav_mode after processing
            context.user_data.pop("fav_mode", None)
        
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
                        f"✅ Removed *{symbol}* from favorites!",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ *{symbol}* is not in your favorites.",
                        parse_mode="Markdown"
                    )
            
            # ✅ ADDED: Clear fav_mode after processing
            context.user_data.pop("fav_mode", None)
            context.user_data.pop("fav_mode_since", None)

        # -------------------------
        # UNKNOWN MODE (SAFETY)
        # -------------------------
        else:
            # Clear invalid mode
            context.user_data.pop("fav_mode", None)
            await update.message.reply_text(
                "❌ Invalid favorite mode. Please use /fav to start over."
            )
    
    except Exception as e:
        print("ERROR in fav_text_handler:", e)
        traceback.print_exc()
        # Clear mode on unexpected errors
        context.user_data.pop("fav_mode", None)
        context.user_data.pop("fav_mode_since", None)
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again with /fav"
        )
