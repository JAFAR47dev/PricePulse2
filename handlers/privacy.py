# handlers/privacy.py
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
import asyncio

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display bot's privacy policy and terms of use (split into parts)"""
    
    # Part 1: Introduction & Data Collection
    part1 = (
        "🔒 <b>PricePulseBot - Privacy Policy &amp; Terms</b>\n\n"
        
        "<b>📋 IMPORTANT - PLEASE READ</b>\n\n"
        
        "By using PricePulseBot (the \"Bot\"), you agree to these terms and our data practices. "
        "If you don't agree, please discontinue use immediately.\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>1️⃣ Information We Collect</b>\n\n"
        
        "We collect only essential data to provide our services:\n"
        "• Telegram User ID (for account identification)\n"
        "• Username (if publicly available)\n"
        "• Command usage data (analytics only)\n"
        "• Alert preferences and settings\n"
        "• Subscription status (Free/Pro)\n\n"
        
        "We <b>DO NOT</b> collect:\n"
        "• Private messages or chat history\n"
        "• Wallet addresses or private keys\n"
        "• Personal identification documents\n"
        "• Financial account information\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>2️⃣ How We Use Your Data</b>\n\n"
        
        "Your data is used exclusively to:\n"
        "• Deliver price alerts and notifications\n"
        "• Maintain your preferences and settings\n"
        "• Improve bot performance and features\n"
        "• Provide customer support when requested\n"
        "• Process subscription payments (via third-party processors)\n\n"
        
        "We <b>NEVER</b>:\n"
        "• Sell your data to third parties\n"
        "• Share data with advertisers\n"
        "• Use data for purposes beyond bot functionality"
    )
    
    # Part 2: Security & Rights
    part2 = (
        "<b>3️⃣ Data Storage &amp; Security</b>\n\n"
        
        "• Data is stored in encrypted databases\n"
        "• Regular backups ensure data safety\n"
        "• Access is restricted to authorized personnel only\n"
        "• We retain data only as long as necessary\n"
        "• Analytics data is auto-deleted after 31 days\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>4️⃣ Your Rights (GDPR Compliance)</b>\n\n"
        
        "You have the right to:\n"
        "• Delete your data: Use /removeall to clear alerts\n"
        "• Opt-out of notifications: Use /notifications\n"
        "• Withdraw consent: Stop using the bot anytime\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>5️⃣ Third-Party Services</b>\n\n"
        
        "We integrate with trusted services:\n"
        "• CoinGecko API (market data)\n"
        "• Twelve Data API (technical indicators)\n"
        "• Payment processors (subscription handling)\n\n"
        
        "These services have their own privacy policies. "
        "We recommend reviewing them if concerned."
    )
    
    # Part 3: Disclaimers
    part3 = (
        "<b>6️⃣ Disclaimer - NOT FINANCIAL ADVICE</b>\n\n"
        
        "⚠️ <b>IMPORTANT:</b> PricePulseBot provides <b>informational data only</b>.\n\n"
        
        "We are <b>NOT</b>:\n"
        "• Financial advisors\n"
        "• Investment consultants\n"
        "• Brokers or portfolio managers\n"
        "• Tax or legal advisors\n\n"
        
        "<b>Trading cryptocurrency carries risk.</b> You may lose some or all of your capital. "
        "Always conduct your own research (DYOR) before making investment decisions.\n\n"
        
        "We are not responsible for:\n"
        "• Trading losses or missed opportunities\n"
        "• Data inaccuracies from third-party APIs\n"
        "• Market volatility or unexpected events\n"
        "• Technical issues or service interruptions\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>7️⃣ Affiliate Disclosure</b>\n\n"
        
        "Some links shared by the bot may be affiliate links. "
        "If you sign up through these links, we may earn a commission at <b>no extra cost to you</b>. "
        "This helps support bot development and maintenance.\n\n"
        
        "Affiliate relationships do not influence our data or recommendations."
    )
    
    # Part 4: Terms & Policies
    part4 = (
        "<b>8️⃣ Age Restriction</b>\n\n"
        
        "You must be <b>18 years or older</b> to use this bot. "
        "If you're between 13-17, you need parental consent. "
        "Users under 13 are not permitted to use our services.\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>9️⃣ Acceptable Use Policy</b>\n\n"
        
        "You agree <b>NOT</b> to:\n"
        "• Use the bot for illegal activities\n"
        "• Spam commands or abuse the service\n"
        "• Attempt to reverse-engineer or hack the bot\n"
        "• Share your Pro account with others\n"
        "• Impersonate bot staff or administrators\n\n"
        
        "Violations may result in account suspension or termination.\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>🔟 Refund Policy</b>\n\n"
        
        "Due to the digital nature of our services:\n"
        "• All purchases are final\n"
        "• We do NOT offer refunds under any circumstances\n"
        "• Please review features carefully before upgrading\n"
        "• Chargebacks or payment disputes will result in a permanent ban\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>1️⃣1️⃣ Changes to Privacy Policy</b>\n\n"
        
        "We may update this policy from time to time. "
        "Continued use of the bot after changes constitutes acceptance. "
        "Major changes will be announced via broadcast message."
    )
    
    # Part 5: Contact & Footer
    part5 = (
        "<b>1️⃣2️⃣ Contact &amp; Support</b>\n\n"
        
        "Questions about privacy or data?\n"
        "• General support: /support\n"
        "• Feedback: /feedback\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "<b>📅 Last Updated:</b> January 2026\n"
        "<b>🤖 Bot Version:</b> 2.0\n\n"
        
        "By continuing to use PricePulseBot, you acknowledge that you have read, "
        "understood, and agree to this Privacy Policy and Terms of Use.\n\n"
        
        "Thank you for trusting PricePulseBot! 🚀"
    )
    
    # Send all parts with small delays
    try:
        await update.message.reply_text(part1, parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)
        
        await update.message.reply_text(part2, parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)
        
        await update.message.reply_text(part3, parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)
        
        await update.message.reply_text(part4, parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)
        
        await update.message.reply_text(part5, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"Error sending privacy policy: {e}")
        await update.message.reply_text(
            "⚠️ Error displaying privacy policy. Please try again or contact /support",
            parse_mode=ParseMode.HTML
        )


def register_privacy_handler(app):
    """Register the privacy command handler"""
    app.add_handler(CommandHandler("privacy", privacy_command))
