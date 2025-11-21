# utils/streaks.py
from datetime import datetime
from models.db import get_connection

# Commands/messages to ignore for streak increment
IGNORED_COMMANDS = ["/start", "/help", "/tasks"]

MILESTONES = [3, 4, 7, 12]  # days for milestone messages

def should_count_for_streak(message_text: str) -> bool:
    """Return True if user activity counts toward streak."""
    if not message_text:
        return False
    message_text = message_text.strip().split()[0]  # first word
    return message_text not in IGNORED_COMMANDS