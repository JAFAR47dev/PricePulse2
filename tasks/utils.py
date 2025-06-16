from datetime import datetime, timedelta
from models.db import get_connection
from models.user import set_user_plan  # already used elsewhere

def check_and_grant_reward(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    # Check if all 3 tasks were approved
    cursor.execute("""
        SELECT task1_done, task2_done, task3_done, reward_given
        FROM task_progress
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return

    task1_done, task2_done, task3_done, reward_given = row

    # If already rewarded, skip
    if reward_given:
        print(f"User {user_id} already received reward.")
        conn.close()
        return

    # All tasks approved → grant reward
    if task1_done and task2_done and task3_done:
        expiry_date = (datetime.utcnow() + timedelta(days=30)).isoformat()

        # Upgrade user
        cursor.execute("""
            UPDATE users SET plan = 'pro', pro_expiry = ? WHERE user_id = ?
        """, (expiry_date, user_id))

        # Mark reward as given
        cursor.execute("""
            UPDATE task_progress SET reward_given = 1 WHERE user_id = ?
        """, (user_id,))

        conn.commit()
        conn.close()
        print(f"✅ Pro access granted to user {user_id} until {expiry_date}")

        return True  # Optionally return flag if you want to DM the user later

    conn.close()