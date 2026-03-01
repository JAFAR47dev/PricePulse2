"""
SMA Crossover Strategy
Buys when short SMA crosses above long SMA, sells on reverse crossover
"""

from statistics import mean

def calculate_sma(prices: list, period: int) -> list:
    """Calculate Simple Moving Average"""
    sma_values = []
    for i in range(len(prices)):
        if i < period - 1:
            sma_values.append(None)
        else:
            window = prices[i - period + 1:i + 1]
            sma_values.append(sum(window) / period)
    return sma_values


def simulate_sma_strategy(candles, short_period=10, long_period=30, stop_loss_pct=5, take_profit_pct=10):
    """
    Simulate SMA crossover strategy:
    - Buy when short SMA crosses above long SMA
    - Sell when short SMA crosses below long SMA
    - Includes stop-loss and take-profit
    
    Args:
        candles: List of dicts with 'close' prices
        short_period: Short SMA period (default 10)
        long_period: Long SMA period (default 30)
        stop_loss_pct: Stop loss percentage (default 5%)
        take_profit_pct: Take profit percentage (default 10%)
    
    Returns:
        dict: Performance statistics
    """
    if not candles or len(candles) < long_period:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_return": 0,
            "avg_gain": 0,
            "avg_loss": 0,
            "max_drawdown": 0,
            "buy_hold_return": 0,
            "beat_market": 0
        }
    
    # Extract closing prices
    closes = [c['close'] for c in candles]
    
    # Calculate SMAs
    sma_short = calculate_sma(closes, short_period)
    sma_long = calculate_sma(closes, long_period)
    
    wins = 0
    losses = 0
    entry_price = None
    returns = []
    buy_hold_start = closes[long_period]  # Start after SMAs are valid
    buy_hold_end = closes[-1]
    
    # Simulate trading
    for i in range(long_period, len(candles)):
        if sma_short[i] is None or sma_long[i] is None:
            continue
        
        close = closes[i]
        
        # === BUY SIGNAL: Short crosses above Long ===
        if (entry_price is None and 
            i > long_period and
            sma_short[i-1] <= sma_long[i-1] and 
            sma_short[i] > sma_long[i]):
            entry_price = close
        
        # === TRADE MANAGEMENT ===
        elif entry_price is not None:
            change_pct = ((close - entry_price) / entry_price) * 100
            
            # Stop-loss hit
            if change_pct <= -stop_loss_pct:
                returns.append(change_pct)
                losses += 1
                entry_price = None
            
            # Take-profit hit
            elif change_pct >= take_profit_pct:
                returns.append(change_pct)
                wins += 1
                entry_price = None
            
            # === SELL SIGNAL: Short crosses below Long ===
            elif (i > long_period and
                  sma_short[i-1] >= sma_long[i-1] and 
                  sma_short[i] < sma_long[i]):
                returns.append(change_pct)
                if change_pct > 0:
                    wins += 1
                else:
                    losses += 1
                entry_price = None
    
    # Close any remaining position
    if entry_price is not None:
        final_ret = ((closes[-1] - entry_price) / entry_price) * 100
        returns.append(final_ret)
        if final_ret > 0:
            wins += 1
        else:
            losses += 1
    
    # Calculate statistics
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades else 0
    total_return = sum(returns) if returns else 0
    
    winning_returns = [r for r in returns if r > 0]
    losing_returns = [r for r in returns if r < 0]
    
    avg_gain = mean(winning_returns) if winning_returns else 0
    avg_loss = abs(mean(losing_returns)) if losing_returns else 0
    max_drawdown = min(returns) if returns else 0
    
    buy_hold_return = ((buy_hold_end - buy_hold_start) / buy_hold_start) * 100
    
    return {
        "trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_return": round(total_return, 2),
        "avg_gain": round(avg_gain, 2),
        "avg_loss": round(avg_loss, 2),
        "max_drawdown": round(max_drawdown, 2),
        "buy_hold_return": round(buy_hold_return, 2),
        "beat_market": round(total_return - buy_hold_return, 2)
    }