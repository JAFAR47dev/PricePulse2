"""
RSI Mean Reversion Strategy
Buys when RSI is oversold (<30) and sells when RSI is overbought (>70)
"""

def calculate_rsi(prices: list, period: int = 14) -> list:
    """
    Calculate Relative Strength Index (RSI)
    
    Args:
        prices: List of closing prices
        period: RSI period (default 14)
    
    Returns:
        List of RSI values (None for initial period)
    """
    if len(prices) < period + 1:
        return [None] * len(prices)
    
    rsi_values = [None] * period
    
    # Calculate initial average gain and loss
    gains = []
    losses = []
    
    for i in range(1, period + 1):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    # Calculate first RSI
    if avg_loss == 0:
        rsi_values.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100 - (100 / (1 + rs)))
    
    # Calculate remaining RSI values using smoothed averages
    for i in range(period + 1, len(prices)):
        change = prices[i] - prices[i - 1]
        
        gain = change if change > 0 else 0
        loss = abs(change) if change < 0 else 0
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi_values.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
    
    return rsi_values


def simulate_rsi_strategy(candles, rsi_period=14, oversold=30, overbought=70, 
                          stop_loss_pct=5, take_profit_pct=10):
    """
    Simulate RSI mean reversion strategy:
    - Buy when RSI crosses below oversold threshold (default 30)
    - Sell when RSI crosses above overbought threshold (default 70)
    - Includes stop-loss and take-profit
    
    Args:
        candles: List of dicts with 'close' prices
        rsi_period: RSI calculation period (default 14)
        oversold: Oversold threshold (default 30)
        overbought: Overbought threshold (default 70)
        stop_loss_pct: Stop loss percentage (default 5%)
        take_profit_pct: Take profit percentage (default 10%)
    
    Returns:
        dict: Performance statistics
    """
    from statistics import mean
    
    if not candles or len(candles) < rsi_period + 1:
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
    
    # Calculate RSI
    rsi_values = calculate_rsi(closes, rsi_period)
    
    wins = 0
    losses = 0
    entry_price = None
    returns = []
    buy_hold_start = closes[rsi_period]  # Start after RSI is valid
    buy_hold_end = closes[-1]
    
    # Simulate trading
    for i in range(rsi_period + 1, len(candles)):
        if rsi_values[i] is None or rsi_values[i-1] is None:
            continue
        
        close = closes[i]
        
        # === BUY SIGNAL: RSI crosses below oversold ===
        if (entry_price is None and 
            rsi_values[i-1] >= oversold and 
            rsi_values[i] < oversold):
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
            
            # === SELL SIGNAL: RSI crosses above overbought ===
            elif (rsi_values[i-1] <= overbought and 
                  rsi_values[i] > overbought):
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