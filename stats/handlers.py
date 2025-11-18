from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from stats.models import get_stats
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID"))

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Admin-only restriction
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 This command is for admins only.")
        return

    stats = get_stats()

    # Format message
    msg = (
        "*📊 PricePulseBot Statistics*\n\n"
        
        "👥 *Users Summary*\n"
        f"• Total Users: `{stats['total_users']}`\n"
        f"• Pro Users: `{stats['pro_users']}`\n"
        f"• Free Users: `{stats['free_users']}`\n\n"

        "📈 *Active Users*\n"
        f"• Last 24h: `{stats.get('active_24h', 0)}`\n"
        f"• Last 7d: `{stats.get('active_7d', 0)}`\n"
        f"• Last 30d: `{stats.get('active_30d', 0)}`\n\n"

        "🔔 *Alerts by Type*\n"
        f"• Price: `{stats['alerts']}`\n"
        f"• Percent: `{stats['percent_alerts']}`\n"
        f"• Volume: `{stats['volume_alerts']}`\n"
        f"• Risk: `{stats['risk_alerts']}`\n"
        f"• Custom: `{stats['custom_alerts']}`\n"
        f"• Portfolio: `{stats['portfolio_alerts']}`\n"
        f"• Watchlist: `{stats['watchlist']}`\n\n"

        "🎯 *Engagement Stats*\n"
        f"• Tasks Completed: `{stats['task_completers']}`\n"
        f"• Total Referrals: `{stats['total_referrals']}`\n"
        f"• Top Referrer: `{stats['top_referrer'] or 'N/A'}` "
        f"({stats['top_referral_count']} referrals)"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")
    
def register_stats_handler(app):
        
    app.add_handler(CommandHandler("stats", show_stats))