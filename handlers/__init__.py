from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

from handlers.broadcast import register_broadcast_handlers
from handlers.set_alert.flow_manager import register_set_handlers
from .alert_handlers import register_alert_handlers
from .chart import show_chart
from .portfolio import (
    view_portfolio, add_asset, remove_asset, clear_portfolio,
    set_portfolio_loss_limit, set_portfolio_profit_target
)
from .admin import (
set_plan,
 pro_user_list
)
from .fav.fav_handler import (
fav_command,
fav_text_handler
)
from .fav.callback_handler import fav_callback_handler
from .upgrade import (
    upgrade_menu, handle_plan_selection, back_to_plans,
    show_payment_instructions, confirm_payment
)
from .best_gainers import best_gainers, best_callback_handler
from .calendar import calendar_command
from .coin_alias_handler import (
    handle_chart_button, handle_add_alert_button,
    coin_alias_handler, coin_command_router 
)
from .compare import compare_command
from .convert import convert_command
from .calc import calc_command
from .daily_coin import coin_of_the_day
from .funfact import funfact_command, funfact_random_callback
from .gasfees import gasfees_command
from .heatmap import heatmap_command
from .help import (
help_command, handle_help_pagination
)
from .learn import (
learn_command, learn_term_callback, learn_page_callback, learn_random_callback,
send_learn_page
)
from .links import links_command
from .markets import markets_command
from .news import crypto_news
from .prediction import predict_command
from .referral import referral_command
from .start import (
    start_command, 
    handle_upgrade_menu,
    handle_how_it_helps, 
    handle_alerts,
    handle_markets,
    handle_trade,
    handle_portfolio,
    handle_ai,
    handle_learn,
    handle_account,
    handle_back_to_start
)
from .trend import trend_command
from .worst_losers import worst_losers, worst_callback_handler
from .fx import fx_command
from .fxchart import fxchart_command
from .fxsessions import fxsessions_command
from .strategy_builder import (
    strategy_command,
    handle_strategy_input,
    confirm_strategy_callback,
    cancel_strategy_callback,
    AWAITING_STRATEGY_INPUT
)
from .backtest import backtest_command
from .aiscan import aiscan_command
from .screener import (
    screener_command, 
    screener_callback
)
from .prediction import predict_command
from whales.handlers.track import register_track_handler
from whales.handlers.mywhales import register_mywhales_handler
from whales.handlers.untrack import register_untrack_handler
#from .insights import insights_command
from .global_data import register_global_handler
from .feedback import register_feedback_handler
from stats.handlers import register_stats_handler
from tasks import register_task_handlers
from notifications.handlers.notify_menu import register_notify_handlers
from .add_to_group import add_to_group
from .myplan import myplan
from .signals import signals_command


def register_all_handlers(app):
        
       register_alert_handlers(app)
       register_track_handler(app)
       register_mywhales_handler(app)
       register_untrack_handler(app)
       register_global_handler(app) 
       register_feedback_handler(app)
       register_stats_handler(app)
       register_task_handlers(app)
       register_notify_handlers(app) 
       register_set_handlers(app)
       register_broadcast_handlers(app)
       
       app.add_handler(CommandHandler("start", start_command))
       app.add_handler(CallbackQueryHandler(handle_upgrade_menu, pattern="^upgrade_menu$"))
       app.add_handler(CallbackQueryHandler(handle_how_it_helps, pattern="^how_it_helps$"))
       app.add_handler(CallbackQueryHandler(handle_alerts, pattern="^alerts$"))
       app.add_handler(CallbackQueryHandler(handle_markets, pattern="^markets$"))
       app.add_handler(CallbackQueryHandler(handle_trade, pattern="^trade$"))
       app.add_handler(CallbackQueryHandler(handle_portfolio, pattern="^portfolio$"))
       app.add_handler(CallbackQueryHandler(handle_ai, pattern="^ai$"))
       app.add_handler(CallbackQueryHandler(handle_learn, pattern="^learn$"))
       app.add_handler(CallbackQueryHandler(handle_account, pattern="^account$"))
       app.add_handler(CallbackQueryHandler(handle_back_to_start, pattern="^back_to_start$"))
       app.add_handler(CommandHandler("help", help_command))
       app.add_handler(CallbackQueryHandler(handle_help_pagination, pattern=r"^help_"))
       app.add_handler(CommandHandler("referral", referral_command))
       app.add_handler(CommandHandler("prolist", pro_user_list))
       app.add_handler(CommandHandler("myplan", myplan))
       app.add_handler(CommandHandler("upgrade", upgrade_menu))              
       app.add_handler(CallbackQueryHandler(upgrade_menu, pattern="^upgrade_menuu$"))
       app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^plan_(monthly|yearly|lifetime)$"))
       app.add_handler(CallbackQueryHandler(show_payment_instructions, pattern=r"^pay_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
       app.add_handler(CallbackQueryHandler(back_to_plans, pattern="^back_to_plans$"))
       app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^back_to_crypto_(monthly|yearly|lifetime)$"))
       app.add_handler(CallbackQueryHandler(confirm_payment, pattern=r"^confirm_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
       app.add_handler(CommandHandler("c", show_chart))
       app.add_handler(CommandHandler(["portfolio", "pf"], view_portfolio))

       app.add_handler(CommandHandler(["addasset", "add"], add_asset))

       app.add_handler(CommandHandler("removeasset", remove_asset))

       app.add_handler(CommandHandler(
           ["portfoliolimit", "pflimit"],
           set_portfolio_loss_limit
       ))

       app.add_handler(CommandHandler(
           ["portfoliotarget", "pftarget"],
           set_portfolio_profit_target
       ))

       app.add_handler(CommandHandler(
           ["clearportfolio", "clearpf"],
           clear_portfolio
       ))
       app.add_handler(CommandHandler("setplan", set_plan))
       app.add_handler(CommandHandler("cod", coin_of_the_day))
       app.add_handler(CommandHandler("cal", calendar_command))
       app.add_handler(CommandHandler("hmap", heatmap_command))
       app.add_handler(CommandHandler("conv", convert_command))
       app.add_handler(CommandHandler("calc", calc_command))
       app.add_handler(CommandHandler("learn", learn_command))
       app.add_handler(CallbackQueryHandler(learn_page_callback, pattern=r"^learn_page_\d+$"))
       app.add_handler(CallbackQueryHandler(learn_term_callback, pattern=r"^learn_\d+_\d+$"))
       app.add_handler(CallbackQueryHandler(learn_random_callback, pattern="^learn_random$"))
       app.add_handler(CommandHandler("markets", markets_command))
       app.add_handler(CommandHandler("comp", compare_command))
       app.add_handler(CommandHandler("links", links_command))
       app.add_handler(CommandHandler("gas", gasfees_command))
       app.add_handler(CommandHandler("funfact", funfact_command))
       app.add_handler(CallbackQueryHandler(funfact_random_callback, pattern="funfact_random"))
       app.add_handler(CommandHandler("fx", fx_command))
       app.add_handler(CommandHandler("fxchart", fxchart_command))
       app.add_handler(CommandHandler("fxsessions", fxsessions_command))
       app.add_handler(CommandHandler("best", best_gainers))
       app.add_handler(CallbackQueryHandler(best_callback_handler, pattern="^best_"))    
       app.add_handler(CommandHandler("worst", worst_losers))
       app.add_handler(CallbackQueryHandler(worst_callback_handler, pattern="^worst_"))
       app.add_handler(CommandHandler("trend", trend_command))
       app.add_handler(CommandHandler("news", crypto_news)) 
       #app.add_handler(CommandHandler("insights", insights_command))
       app.add_handler(CommandHandler("fav", fav_command))
       app.add_handler(CallbackQueryHandler(fav_callback_handler, pattern="^fav_"))
       app.add_handler(CommandHandler("addtogroup", add_to_group)) 
       app.add_handler(CommandHandler("signals", signals_command))    
       #app.add_handler(ConversationHandler(
#        entry_points=[CommandHandler("aistrat", strategy_command)],
#        states={
#            AWAITING_STRATEGY_INPUT: [
#                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_strategy_input)
#            ]
#        },
#        fallbacks=[]
#    ))

#       app.add_handler(CallbackQueryHandler(confirm_strategy_callback, pattern="^confirm_strategy$"))
#       app.add_handler(CallbackQueryHandler(cancel_strategy_callback, pattern="^cancel_strategy$"))
       app.add_handler(CommandHandler("bt", backtest_command))
       app.add_handler(CommandHandler("aiscan", aiscan_command))
       app.add_handler(CommandHandler("screen", screener_command))
       app.add_handler(CommandHandler("prediction", predict_command)) 
       app.add_handler(CallbackQueryHandler(screener_callback, pattern=r"^screener_"))               
       app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/[a-zA-Z]{2,10}$"), 
        coin_command_router
    ))
       app.add_handler(CallbackQueryHandler(handle_chart_button, pattern=r"^chart_"))
       app.add_handler(CallbackQueryHandler(handle_add_alert_button, pattern=r"^addalert_"))
        