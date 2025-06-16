
from datetime import datetime 
from telegram import Bot 
from models.db import get_connection 
from config import TELEGRAM_BOT_TOKEN

bot = Bot(token=TELEGRAM_BOT_TOKEN)


async def check_expired_pro_users(context):
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.utcnow()
    cursor.execute("""
        SELECT user_id, plan, expiry_date FROM users
        WHERE plan LIKE 'pro%' AND expiry_date IS NOT NULL
    """)
    rows = cursor.fetchall()

    for user_id, plan, expiry_str in rows:
        try:
            expiry = datetime.fromisoformat(expiry_str)
            if now >= expiry:
                # Downgrade the user
                cursor.execute("UPDATE users SET plan = 'free', expiry_date = NULL WHERE user_id = ?", (user_id,))
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Your Pro plan has expired. You’ve been downgraded to the Free plan.\nUse /upgrade to reactivate your benefits 💎"
                )
                print(f"✅ Downgraded user {user_id} from {plan} to Free.")
        except Exception as e:
            print(f"❌ Error processing user {user_id}: {e}")

    conn.commit()
    conn.close()
