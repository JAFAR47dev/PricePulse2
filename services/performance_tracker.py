# services/performance_tracker.py

from datetime import datetime, timedelta
from database.setup_db import get_connection

class PerformanceTracker:
    """Track and analyze historical setup performance"""
    
    async def get_similar_setups(self, symbol: str, timeframe: str, score: int) -> dict:
        """
        Find historical performance of similar setups
        
        Args:
            symbol: Trading symbol
            timeframe: Chart timeframe
            score: Current setup score
        
        Returns:
            dict with performance metrics or None
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Find similar setups in last 30 days
            # Score range: ±5 points
            cursor.execute("""
                SELECT outcome, profit_pct, risk_reward 
                FROM trade_setups
                WHERE symbol = ?
                AND timeframe = ?
                AND score BETWEEN ? AND ?
                AND created_at > datetime('now', '-30 days')
                AND outcome IS NOT NULL
            """, (symbol, timeframe, score - 5, score + 5))
            
            results = cursor.fetchall()
            conn.close()
            
            if not results or len(results) < 5:
                # Not enough data
                return None
            
            # Calculate performance metrics
            wins = [r for r in results if r[0] == 'win']
            losses = [r for r in results if r[0] == 'loss']
            
            total = len(results)
            win_count = len(wins)
            loss_count = len(losses)
            
            win_rate = (win_count / total) * 100
            
            avg_win = sum(r[1] for r in wins) / win_count if win_count > 0 else 0
            avg_loss = sum(r[1] for r in losses) / loss_count if loss_count > 0 else 0
            
            # Calculate expectancy
            # Expectancy = (Win% * AvgWin) + (Loss% * AvgLoss)
            expectancy = (win_rate/100 * avg_win) + ((1-win_rate/100) * avg_loss)
            
            # Average R:R ratio
            avg_rr = sum(r[2] for r in results) / total if total > 0 else 0
            
            return {
                'total_setups': total,
                'win_rate': win_rate,
                'wins': win_count,
                'losses': loss_count,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'expectancy': expectancy,
                'avg_risk_reward': avg_rr
            }
            
        except Exception as e:
            print(f"❌ Performance tracker error: {e}")
            return None
    
    async def track_setup(self, user_id: int, symbol: str, timeframe: str, setup_data: dict) -> bool:
        """
        Save setup for future tracking
        
        Args:
            user_id: Telegram user ID
            symbol: Trading symbol
            timeframe: Chart timeframe
            setup_data: Setup analysis data
        
        Returns:
            bool: Success status
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO trade_setups (
                    user_id, symbol, timeframe, score, direction,
                    entry_price, stop_loss, take_profit_1, take_profit_2,
                    risk_reward, created_at, outcome, profit_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """, (
                user_id,
                symbol,
                timeframe,
                setup_data['score'],
                setup_data['direction'],
                setup_data['current_price'],
                setup_data['stop_loss'],
                setup_data['take_profit_1'],
                setup_data['take_profit_2'],
                setup_data['risk_reward'],
                datetime.now()
            ))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            print(f"❌ Track setup error: {e}")
            return False