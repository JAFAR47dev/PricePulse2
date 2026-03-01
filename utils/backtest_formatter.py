"""
Formatting utilities for backtest results
"""

def format_strategy_output(symbol: str, period: str, stats: dict, start_date: str, 
                           end_date: str, strategy_name: str) -> str:
    """
    Format individual strategy backtest results
    
    Args:
        symbol: Trading symbol (e.g., 'BTC')
        period: Time period (e.g., '30d')
        stats: Performance statistics dict
        start_date: Start date string
        end_date: End date string
        strategy_name: Name of the strategy (e.g., 'MA Crossover (10/30)')
    
    Returns:
        Formatted message string
    """
    profit_emoji = "✅" if stats['total_return'] > 0 else "❌"
    vs_emoji = "🎯" if stats['beat_market'] > 0 else "📉"
    
    initial_capital = 10000
    final_capital = initial_capital * (1 + stats['total_return'] / 100)
    profit_loss = final_capital - initial_capital
    
    message = (
        f"🔍 *Backtest: {symbol}*\n"
        f"📅 {start_date} → {end_date} ({period})\n"
        f"📊 Strategy: {strategy_name}\n\n"
        
        f"💵 *RESULTS*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Starting Capital: ${initial_capital:,.0f}\n"
        f"Final Balance: ${final_capital:,.0f}\n"
        f"Profit/Loss: {'+' if profit_loss >= 0 else ''}{profit_loss:,.0f} ({stats['total_return']:+.1f}%) {profit_emoji}\n\n"
        
        f"🆚 *VS. JUST HOLDING*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Your Strategy: {stats['total_return']:+.1f}%\n"
        f"Buy & HODL: {stats['buy_hold_return']:+.1f}%\n"
        f"Difference: {stats['beat_market']:+.1f}% {'better' if stats['beat_market'] > 0 else 'worse'} {vs_emoji}\n\n"
        
        f"⚠️ *RISK*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Biggest Drop: {stats['max_drawdown']:.1f}%\n"
        f"(Max you were down from peak)\n\n"
        
        f"📈 *TRADES*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Signals: {stats['trades']} trades\n"
        f"Profitable: {stats['wins']} ({stats['win_rate']:.1f}%)\n"
        f"Unprofitable: {stats['losses']} ({100 - stats['win_rate']:.1f}%)\n\n"
        
        f"💡 *BREAKDOWN*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Avg Win: +{stats['avg_gain']:.2f}%\n"
        f"Avg Loss: -{stats['avg_loss']:.2f}%\n\n"
        
        f"⚙️ Fees Included: 0.1% per trade\n"
        f"⏱️ Slippage: 0.05% (realistic fills)\n\n"
        
        f"⚠️ *Disclaimer:* Past results don't guarantee future profits. This is for educational purposes only.\n\n"
    )
    
    return message


def format_comparison_output(symbol: str, period: str, sma_stats: dict, rsi_stats: dict, 
                             start_date: str, end_date: str) -> str:
    """
    Format side-by-side comparison of both strategies
    
    Args:
        symbol: Trading symbol
        period: Time period
        sma_stats: SMA strategy statistics
        rsi_stats: RSI strategy statistics
        start_date: Start date string
        end_date: End date string
    
    Returns:
        Formatted comparison message
    """
    # Determine winners
    better_return = "MA" if sma_stats['total_return'] > rsi_stats['total_return'] else "RSI"
    better_winrate = "MA" if sma_stats['win_rate'] > rsi_stats['win_rate'] else "RSI"
    better_trades = "MA" if sma_stats['trades'] > rsi_stats['trades'] else "RSI"
    safer = "MA" if sma_stats['max_drawdown'] > rsi_stats['max_drawdown'] else "RSI"
    
    # Crown emoji for overall winner
    crown_ma = "👑 " if better_return == "MA" else ""
    crown_rsi = "👑 " if better_return == "RSI" else ""
    
    message = (
        f"⚔️ *STRATEGY SHOWDOWN: {symbol}*\n"
        f"📅 {start_date} → {end_date} ({period})\n\n"
        
        f"═══════════════════════\n"
        f"{crown_ma}*MA CROSSOVER (10/30)*\n"
        f"═══════════════════════\n"
        f"Total Return: {sma_stats['total_return']:+.1f}%\n"
        f"Win Rate: {sma_stats['win_rate']:.1f}%\n"
        f"Total Trades: {sma_stats['trades']}\n"
        f"Max Drawdown: {sma_stats['max_drawdown']:.1f}%\n"
        f"vs HODL: {sma_stats['beat_market']:+.1f}%\n\n"
        
        f"═══════════════════════\n"
        f"{crown_rsi}*RSI REVERSION (14)*\n"
        f"═══════════════════════\n"
        f"Total Return: {rsi_stats['total_return']:+.1f}%\n"
        f"Win Rate: {rsi_stats['win_rate']:.1f}%\n"
        f"Total Trades: {rsi_stats['trades']}\n"
        f"Max Drawdown: {rsi_stats['max_drawdown']:.1f}%\n"
        f"vs HODL: {rsi_stats['beat_market']:+.1f}%\n\n"
        
        f"🏆 *HEAD-TO-HEAD*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Best Return: *{better_return}* ({max(sma_stats['total_return'], rsi_stats['total_return']):+.1f}%)\n"
        f"Best Win Rate: *{better_winrate}* ({max(sma_stats['win_rate'], rsi_stats['win_rate']):.1f}%)\n"
        f"More Trades: *{better_trades}* ({max(sma_stats['trades'], rsi_stats['trades'])} signals)\n"
        f"Safer (less drawdown): *{safer}*\n\n"
        
        f"💡 *INSIGHTS*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    # Add dynamic insights
    if abs(sma_stats['total_return'] - rsi_stats['total_return']) < 2:
        message += "• Both strategies performed similarly\n"
    elif better_return == "MA":
        message += f"• MA outperformed by {abs(sma_stats['total_return'] - rsi_stats['total_return']):.1f}%\n"
    else:
        message += f"• RSI outperformed by {abs(sma_stats['total_return'] - rsi_stats['total_return']):.1f}%\n"
    
    if sma_stats['trades'] > rsi_stats['trades'] * 1.5:
        message += "• MA traded more frequently (higher activity)\n"
    elif rsi_stats['trades'] > sma_stats['trades'] * 1.5:
        message += "• RSI traded more frequently (higher activity)\n"
    
    if min(sma_stats['max_drawdown'], rsi_stats['max_drawdown']) > -15:
        message += "• Both strategies managed risk well\n"
    
    message += (
        f"\n⚠️ *Disclaimer:* Past performance doesn't guarantee future results.\n"
        f"Use this for educational purposes only.\n"
    )
    
    return message