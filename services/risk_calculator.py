
class RiskCalculator:
    """Calculate optimal position sizing using Kelly Criterion and risk management"""
    
    def calculate_position_size(
        self,
        account_size: float,
        risk_percent: float,
        entry_price: float,
        stop_loss: float,
        max_risk_percent: float = 5.0
    ) -> dict:
        """
        Calculate position size using fixed fractional method
        
        Args:
            account_size: Total account size in USD
            risk_percent: Percentage of account to risk (1-5%)
            entry_price: Entry price
            stop_loss: Stop loss price
            max_risk_percent: Maximum allowed risk per trade (default 5%)
        
        Returns:
            dict with position sizing details
        """
        
        # Validate inputs
        if risk_percent > max_risk_percent:
            risk_percent = max_risk_percent
        
        # Calculate risk amount in USD
        risk_amount = account_size * (risk_percent / 100)
        
        # Calculate stop loss distance (%)
        stop_distance_pct = abs((stop_loss - entry_price) / entry_price) * 100
        
        # Calculate position size
        # Position Size = Risk Amount / Stop Distance (in decimal)
        position_size = risk_amount / (stop_distance_pct / 100)
        
        # Calculate number of units/coins
        units = position_size / entry_price
        
        # Calculate potential profit at take profits
        # (This would be passed from setup_analyzer)
        
        return {
            'position_size_usd': position_size,
            'units': units,
            'risk_amount': risk_amount,
            'risk_percent': risk_percent,
            'stop_distance_pct': stop_distance_pct,
            'leverage': 1,  # No leverage by default
            'max_position_size': account_size * (max_risk_percent / 100) / (stop_distance_pct / 100)
        }
    
    def calculate_kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        max_kelly: float = 0.25
    ) -> float:
        """
        Calculate optimal bet size using Kelly Criterion
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade %
            avg_loss: Average losing trade % (positive number)
            max_kelly: Maximum Kelly % to use (default 25% of full Kelly)
        
        Returns:
            Optimal position size as % of account
        """
        
        if win_rate <= 0 or win_rate >= 1:
            return 0.02  # Default to 2%
        
        # Kelly Formula: (Win% * AvgWin - Loss% * AvgLoss) / AvgWin
        loss_rate = 1 - win_rate
        
        kelly = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
        
        # Apply fractional Kelly (usually 25-50% of full Kelly)
        fractional_kelly = kelly * max_kelly
        
        # Cap between 1% and 5%
        return max(0.01, min(fractional_kelly, 0.05))
