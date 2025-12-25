import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from models.user_activity import update_last_active

# === File paths ===
WHALE_DATA_DIR = "whales/data"
USER_TRACK_FILE = "whales/user_tracking.json"

# === Initialization ===
def initialize_directories():
    """Ensure required directories and files exist."""
    try:
        os.makedirs(WHALE_DATA_DIR, exist_ok=True)
        
        if not os.path.exists(USER_TRACK_FILE):
            with open(USER_TRACK_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error initializing directories: {e}")
        return False

# Initialize on module load
initialize_directories()


# === Helper functions ===
def load_json_file(path: str) -> Optional[Dict[str, Any]]:
    """
    Safely load a JSON file with proper error handling.
    Returns None if file doesn't exist or contains invalid JSON.
    """
    if not os.path.exists(path):
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return None
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"JSON decode error in {path}: {e}")
        return None
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None


def load_user_tracking() -> Dict[str, Any]:
    """Load user tracking data with fallback to empty dict."""
    data = load_json_file(USER_TRACK_FILE)
    return data if data is not None else {}


def save_user_tracking(data: Dict[str, Any]) -> bool:
    """
    Safely save user tracking data with atomic write operation.
    Returns True on success, False on failure.
    """
    temp_file = USER_TRACK_FILE + ".tmp"
    try:
        # Write to temporary file first
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Atomic rename (overwrites destination on POSIX systems)
        os.replace(temp_file, USER_TRACK_FILE)
        return True
    except Exception as e:
        print(f"Error saving user tracking: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        return False


def validate_token_symbol(token: str) -> Optional[str]:
    """
    Validate and normalize token symbol.
    Returns normalized token or None if invalid.
    """
    if not token or not isinstance(token, str):
        return None
    
    # Remove whitespace and convert to uppercase
    token = token.strip().upper()
    
    # Check for valid characters (alphanumeric only)
    if not token.isalnum():
        return None
    
    # Reasonable length check (most tokens are 2-10 characters)
    if len(token) < 1 or len(token) > 20:
        return None
    
    return token


# === /track Command Handler ===
async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /track [token] [no_of_whales]
    Example: /track ETH 20
    """
    # Ensure update and message exist
    if not update or not update.effective_user or not update.message:
        return
    
    user_id = str(update.effective_user.id)
    
    try:
        await update_last_active(user_id, command_name="/track")
    except Exception as e:
        print(f"Error updating last active for user {user_id}: {e}")
    
    # --- Parse command arguments ---
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "⚠️ Usage: `/track [token] [no_of_whales]`\nExample: `/track ETH 20`",
            parse_mode="Markdown",
        )
        return
    
    # Validate token symbol
    token = validate_token_symbol(context.args[0])
    if not token:
        await update.message.reply_text(
            "⚠️ Invalid token symbol. Please use alphanumeric characters only.\nExample: `/track ETH 20`",
            parse_mode="Markdown",
        )
        return
    
    # Parse limit with validation
    limit = 100  # default
    if len(context.args) >= 2:
        try:
            limit = int(context.args[1])
            if limit <= 0 or limit > 10000:  # reasonable upper bound
                await update.message.reply_text(
                    "⚠️ Number of whales must be between 1 and 10000.\nExample: `/track ETH 20`",
                    parse_mode="Markdown",
                )
                return
        except (ValueError, OverflowError):
            await update.message.reply_text(
                "⚠️ Invalid number format. Please use a valid integer.\nExample: `/track ETH 10`",
                parse_mode="Markdown",
            )
            return
    
    # --- Validate whale data file ---
    whale_file = os.path.join(WHALE_DATA_DIR, f"{token}.json")
    if not os.path.exists(whale_file):
        await update.message.reply_text(
            f"❌ Whale data for *{token}* not found.\nPlease ensure it's among the top 100 ERC20 tokens.",
            parse_mode="Markdown",
        )
        return
    
    whale_data = load_json_file(whale_file)
    if whale_data is None:
        await update.message.reply_text(
            f"⚠️ Could not read whale data for *{token}*. Please try again later.",
            parse_mode="Markdown",
        )
        return
    
    # --- Check if it's a valid ERC20 token ---
    if whale_data.get("unsupported", False):
        reason = whale_data.get("reason", "Unsupported token type.")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 View Supported Tokens", callback_data="whale_supported_tokens")]
        ])
        
        await update.message.reply_text(
            f"⚠️ *{token}* cannot be tracked.\nReason: {reason}",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return
    
    # --- Load or create user tracking data ---
    tracking_data = load_user_tracking()
    user_data = tracking_data.get(user_id, {"tracked": []})
    
    # Ensure tracked is a list
    if not isinstance(user_data.get("tracked"), list):
        user_data["tracked"] = []
    
    # Prevent duplicate tracking (case-insensitive comparison)
    if any(t.get("token", "").upper() == token for t in user_data["tracked"]):
        await update.message.reply_text(
            f"⚠️ You're already tracking *{token}* whales.",
            parse_mode="Markdown",
        )
        return
    
    # --- Add tracking record ---
    user_data["tracked"].append({
        "token": token,
        "limit": limit,
        "added_at": datetime.utcnow().isoformat() + "Z"
    })
    tracking_data[user_id] = user_data
    
    # Save with error handling
    if not save_user_tracking(tracking_data):
        await update.message.reply_text(
            "⚠️ Error saving tracking data. Please try again.",
            parse_mode="Markdown",
        )
        return
    
    # ✅ Success message
    await update.message.reply_text(
        f"✅ You're now tracking the top {limit} *{token}* whales.",
        parse_mode="Markdown",
    )


async def whale_supported_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display list of supported tokens for whale tracking."""
    if not update or not update.callback_query:
        return
    
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception as e:
        print(f"Error answering callback query: {e}")
        return
    
    supported = []
    
    try:
        # Check if directory exists
        if not os.path.exists(WHALE_DATA_DIR):
            await query.message.reply_text(
                "⚠️ Whale data directory not found.",
                parse_mode="Markdown"
            )
            return
        
        # List all JSON files
        files = [f for f in os.listdir(WHALE_DATA_DIR) if f.endswith(".json")]
        
        for file in files:
            filepath = os.path.join(WHALE_DATA_DIR, file)
            data = load_json_file(filepath)
            
            if data is None:
                continue
            
            # Only list supported tokens
            if not data.get("unsupported", False):
                symbol = data.get("token", file.replace(".json", "")).upper()
                if symbol and symbol not in supported:  # Avoid duplicates
                    supported.append(symbol)
        
        if not supported:
            await query.message.reply_text(
                "⚠️ No supported tokens found.",
                parse_mode="Markdown"
            )
            return
        
        # Sort alphabetically for consistency
        supported.sort()
        
        # Arrange tokens in rows of 5
        rows = []
        row_size = 5
        
        for i in range(0, len(supported), row_size):
            chunk = supported[i:i + row_size]
            rows.append(" | ".join(chunk))
        
        supported_list = "\n".join(rows)
        
        msg = (
            "📜 *Supported Tokens for Whale Tracking*\n\n"
            f"{supported_list}\n\n"
            f"Total: {len(supported)} tokens"
        )
        
        await query.message.reply_text(msg, parse_mode="Markdown")
    
    except Exception as e:
        print(f"Error in whale_supported_tokens_callback: {e}")
        await query.message.reply_text(
            "⚠️ Error loading supported tokens. Please try again later.",
            parse_mode="Markdown"
        )


def register_track_handler(app):
    """Register command and callback handlers."""
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CallbackQueryHandler(
        whale_supported_tokens_callback, 
        pattern="^whale_supported_tokens$"
    ))