from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
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
        
         "⌨️ *Command Usage — Last 24h*\n"
        f"• Top: {format_command_list(stats.get('top_commands_24h'))}\n"
        f"• Least: {format_command_list(stats.get('least_commands_24h'))}\n\n"

        "⌨️ *Command Usage — Last 7 days*\n"
        f"• Top: {format_command_list(stats.get('top_commands_7d'))}\n"
        f"• Least: {format_command_list(stats.get('least_commands_7d'))}\n\n"

        "⌨️ *Command Usage — Last 30 days*\n"
        f"• Top: {format_command_list(stats.get('top_commands_30d'))}\n"
        f"• Least: {format_command_list(stats.get('least_commands_30d'))}\n\n"
    
        "🎯 *Engagement Stats*\n"
        f"• Total Referrals: `{stats['total_referrals']}`\n"
        f"• Top Referrer: `{stats['top_referrer'] or 'N/A'}` "
        f"({stats['top_referral_count']} referrals)\n\n"

       
    )
        

    await update.message.reply_text(msg, parse_mode="Markdown")


def register_stats_handler(app):
    app.add_handler(CommandHandler("stats", show_stats))