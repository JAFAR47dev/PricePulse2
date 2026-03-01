from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
from stats.models import get_stats
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID"))

def format_command_list(cmd_list):
    """
    Convert list of tuples [(command, count), ...] 
    into a human-readable string "command1 (count), command2 (count), ..."
    """
    if not cmd_list:
        return "N/A"
    return ", ".join(f"{cmd} ({cnt})" for cmd, cnt in cmd_list)
    
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Admin-only restriction
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 This command is for admins only.")
        return

    stats = get_stats()

    # Format message with HTML
    msg = (
        "📊 <b>PricePulseBot Statistics</b>\n\n"

        "👥 <b>Users Summary</b>\n"
        f"• Total Users: <code>{stats['total_users']}</code>\n"
        f"• Pro Users: <code>{stats['pro_users']}</code>\n"
        f"• Free Users: <code>{stats['free_users']}</code>\n\n"

        "📈 <b>Active Users</b>\n"
        f"• Last 24h: <code>{stats.get('active_24h', 0)}</code>\n"
        f"• Last 7d: <code>{stats.get('active_7d', 0)}</code>\n"
        f"• Last 30d: <code>{stats.get('active_30d', 0)}</code>\n\n"

        "🔔 <b>Alerts by Type</b>\n"
        f"• Price: <code>{stats['alerts']}</code>\n"
        f"• Percent: <code>{stats['percent_alerts']}</code>\n"
        f"• Volume: <code>{stats['volume_alerts']}</code>\n"
        f"• Risk: <code>{stats['risk_alerts']}</code>\n"
        f"• Indicator: <code>{stats['indicator_alerts']}</code>\n"
        f"• Portfolio: <code>{stats['portfolio_alerts']}</code>\n"
        f"• Watchlist: <code>{stats['watchlist']}</code>\n\n"
        
        "⌨️ <b>Command Usage — Last 24h</b>\n"
        f"• Top: {format_command_list(stats.get('top_commands_24h'))}\n"
        f"• Least: {format_command_list(stats.get('least_commands_24h'))}\n\n"

        "⌨️ <b>Command Usage — Last 7 days</b>\n"
        f"• Top: {format_command_list(stats.get('top_commands_7d'))}\n"
        f"• Least: {format_command_list(stats.get('least_commands_7d'))}\n\n"

        "⌨️ <b>Command Usage — Last 30 days</b>\n"
        f"• Top: {format_command_list(stats.get('top_commands_30d'))}\n"
        f"• Least: {format_command_list(stats.get('least_commands_30d'))}\n\n"
    
        "🎯 <b>Engagement Stats</b>\n"
        f"• Total Referrals: <code>{stats['total_referrals']}</code>\n"
        f"• Top Referrer: <code>{stats['top_referrer'] or 'N/A'}</code> "
        f"({stats['top_referral_count']} referrals)\n\n"
    )

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


def register_stats_handler(app):
    app.add_handler(CommandHandler("stats", show_stats))