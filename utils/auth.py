from models.user import get_user_plan

def is_pro_plan(plan: str) -> bool:
    return plan in {"pro_monthly", "pro_yearly", "pro_lifetime"}