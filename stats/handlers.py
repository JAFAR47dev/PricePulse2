from telegram import Update
from telegram.ext import ContextTypes
from stats.models import get_stats
import os
from dotenv import load_dotenv
load_dotenv()

ADMIN_ID = int(os.getenv("ADMIN_ID"))

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 This command is for admins only.")
        return

    stats = get_stats()
    msg = (
        "*📊 Bot Statistics:*\n\n"
        f"👤 Total Users: {stats['total_users']}\n"
        f"💎 Pro Users: {stats['pro_users']}\n"
        f"🆓 Free Users: {stats['free_users']}\n\n"

        f"🔔 Alerts:\n"
        f"• Price: {stats['alerts']}\n"
        f"• Percent: {stats['percent_alerts']}\n"
        f"• Volume: {stats['volume_alerts']}\n"
        f"• Risk: {stats['risk_alerts']}\n"
        f"• Custom: {stats['custom_alerts']}\n"
        f"• Portfolio: {stats['portfolio_alerts']}\n"
        f"• Watchlist: {stats['watchlist']}\n\n"

        f"🧠 Tasks Completed: {stats['task_completers']}\n"
        f"🤝 Total Referrals: {stats['total_referrals']}\n"
        f"🏆 Top Referrer: {stats['top_referrer']} ({stats['top_referral_count']} referrals)"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")