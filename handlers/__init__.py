from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)



from .alert_handlers import register_alert_handlers
from .chart import show_chart
from .portfolio import (
    view_portfolio, remove_asset, clear_portfolio,
    set_portfolio_loss_limit, set_portfolio_profit_target
)
from .admin import (
set_plan,
 pro_user_list
)
from .upgrade import (
    upgrade_menu, handle_plan_selection, back_to_plans,
    show_payment_instructions, confirm_payment
)
from .best_gainers import best_gainers
from .calendar import calendar_command
from .coin_alias_handler import (
    handle_chart_button, handle_add_alert_button,
    coin_alias_handler, coin_command_router 
)
from .compare import compare_command
from .convert import convert_command
from .daily_coin import coin_of_the_day
from .funfact import funfact_command
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
from .referral import referral
from .start import (
start_command, handle_upgrade_menu,
handle_how_it_helps, handle_view_commands,
handle_join_community, handle_back_to_start
)
from .trend import trend_command
from .worst_losers import worst_losers
from .fx import fx_command
from .fxconv import fxconv_command
from .fxcal import fxcal_command
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
from .trackwallet import (
    trackwallet_conv_handler, 
    trackwallet_callback_handler
    )


def register_all_handlers(app):
        
       register_alert_handlers(app)
       
       
       app.add_handler(CommandHandler("start", start_command))
       app.add_handler(CommandHandler("help", help_command))
       app.add_handler(CallbackQueryHandler(handle_help_pagination, pattern=r"^help_"))
       app.add_handler(CallbackQueryHandler(handle_upgrade_menu, pattern="^upgrade_menu$"))    
       app.add_handler(CallbackQueryHandler(handle_how_it_helps, pattern="^how_it_helps$"))
       app.add_handler(CallbackQueryHandler(handle_view_commands, pattern="^view_commands$"))
       app.add_handler(CallbackQueryHandler(handle_join_community, pattern="^join_community$"))
       app.add_handler(CallbackQueryHandler(handle_back_to_start, pattern="^back_to_start$"))
       app.add_handler(CommandHandler("prolist", pro_user_list))
       app.add_handler(CommandHandler("upgrade", upgrade_menu))       
       app.add_handler(CallbackQueryHandler(handle_plan_selection,                   pattern=r"^plan_(monthly|yearly|lifetime)$"))
       app.add_handler(CallbackQueryHandler(show_payment_instructions, pattern=r"^pay_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
       app.add_handler(CallbackQueryHandler(back_to_plans, pattern="^back_to_plans$"))
       app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^back_to_crypto_(monthly|yearly|lifetime)$"))
       app.add_handler(CallbackQueryHandler(confirm_payment, pattern=r"^confirm_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
       app.add_handler(CommandHandler("c", show_chart))
       app.add_handler(CommandHandler("portfolio", view_portfolio))
       app.add_handler(CommandHandler("removeasset", remove_asset))
       app.add_handler(CommandHandler("portfoliolimit", set_portfolio_loss_limit))
       app.add_handler(CommandHandler("portfoliotarget", set_portfolio_profit_target))
       app.add_handler(CommandHandler("clearportfolio", clear_portfolio))
       app.add_handler(CommandHandler("setplan", set_plan))
       app.add_handler(CommandHandler("cod", coin_of_the_day))
       app.add_handler(CommandHandler("cal", calendar_command))
       app.add_handler(CommandHandler("hmap", heatmap_command))
       app.add_handler(CommandHandler("conv", convert_command))
       app.add_handler(CommandHandler("learn", learn_command))
       app.add_handler(CallbackQueryHandler(learn_page_callback, pattern=r"^learn_page_\d+$"))
       app.add_handler(CallbackQueryHandler(learn_term_callback, pattern=r"^learn_\d+_\d+$"))
       app.add_handler(CallbackQueryHandler(learn_random_callback, pattern="^learn_random$"))
       app.add_handler(CommandHandler("markets", markets_command))
       app.add_handler(CommandHandler("comp", compare_command))
       app.add_handler(CommandHandler("links", links_command))
       app.add_handler(CommandHandler("gas", gasfees_command))
       app.add_handler(CommandHandler("funfact", funfact_command))
       app.add_handler(CommandHandler("fx", fx_command))
       app.add_handler(CommandHandler("fxconv", fxconv_command))
       app.add_handler(CommandHandler("fxcal", fxcal_command))
       app.add_handler(CommandHandler("fxsessions", fxsessions_command))
       app.add_handler(CommandHandler("best", best_gainers))    
       app.add_handler(CommandHandler("worst", worst_losers))
       app.add_handler(CommandHandler("trend", trend_command))
       app.add_handler(CommandHandler("news", crypto_news))       
       app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("aistrat", strategy_command)],
        states={
            AWAITING_STRATEGY_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_strategy_input)
            ]
        },
        fallbacks=[]
    ))

       app.add_handler(CallbackQueryHandler(confirm_strategy_callback, pattern="^confirm_strategy$"))
       app.add_handler(CallbackQueryHandler(cancel_strategy_callback, pattern="^cancel_strategy$"))
       app.add_handler(CommandHandler("bt", backtest_command))
       app.add_handler(CommandHandler("aiscan", aiscan_command))
       app.add_handler(CommandHandler("screen", screener_command))
       app.add_handler(CallbackQueryHandler(screener_callback, pattern=r"^screener_"))               
       app.add_handler(trackwallet_conv_handler)
       app.add_handler(trackwallet_callback_handler)
       app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^/[a-zA-Z]{2,10}$"), 
        coin_command_router
    ))
        


        
                          
       
        
