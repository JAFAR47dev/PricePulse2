from .schemas.users import init_users_table
from .schemas.alerts import init_alert_tables
from .schemas.portfolio import init_portfolio_tables
from .schemas.watchlist import init_watchlist_table
from .schemas.ai_alerts import init_ai_alerts_table
from .schemas.tracked_wallets import init_tracked_wallets_table

def init_db():
    init_users_table()
    init_alert_tables()
    init_portfolio_tables()
    init_watchlist_table()
    init_ai_alerts_table()
    init_tracked_wallets_table()