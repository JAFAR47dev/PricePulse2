from db.schemas.users import init_users_table
from db.schemas.alerts import init_alert_tables
from db.schemas.portfolio import init_portfolio_tables
from db.schemas.watchlist import init_watchlist_table
from db.schemas.ai_alerts import init_ai_alerts_table
from db.schemas.tracked_wallets import init_tracked_wallets_table

def init_db():
    init_users_table()
    init_alert_tables()
    init_portfolio_tables()
    init_watchlist_table()
    init_ai_alerts_table()
    init_tracked_wallets_table()