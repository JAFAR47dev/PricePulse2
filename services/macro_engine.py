# ----------------------------------------------------------------------------
# services/macro_engine.py (UPDATED)
# ----------------------------------------------------------------------------
"""
Engine for fetching and analyzing macro market data
Now uses standalone macro_data.py for data fetching
"""

from utils.macro_data import fetch_macro_asset, MacroDataError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MacroError(Exception):
    """Custom exception for macro data errors"""
    pass


class MacroEngine:
    """
    Engine for macro market analysis
    
    Fetches current prices for:
    - Crypto: BTC, ETH
    - Metals: Gold (XAU/USD), Silver (XAG/USD)
    - Macro: DXY (Dollar Index), S&P 500 (SPX)
    
    Calculates:
    - 24h price changes
    - Key ratios (Gold/BTC, Silver/Gold)
    - Market sentiment
    """
    
    def __init__(self):
        """Initialize macro engine"""
        self.assets = {
            # Crypto
            "BTC": {"symbol": "BTC/USD", "name": "Bitcoin"},
            "ETH": {"symbol": "ETH/USD", "name": "Ethereum"},
            
            # Precious Metals
            "GOLD": {"symbol": "XAU/USD", "name": "Gold"},
            "SILVER": {"symbol": "XAG/USD", "name": "Silver"},
            
            # Macro Indicators
            "DXY": {"symbol": "DXY", "name": "US Dollar Index"},
            "SPX": {"symbol": "SPX", "name": "S&P 500"},
        }
    
    async def get_macro_snapshot(self) -> dict:
        """
        Get current macro market snapshot
        
        Returns:
            Dictionary with all asset prices, changes, ratios, and sentiment
        
        Raises:
            MacroError: If data fetch fails
        """
        
        logger.info("Fetching macro market snapshot")
        
        try:
            # Fetch current prices for all assets
            asset_data = {}
            
            for asset_key, asset_info in self.assets.items():
                try:
                    # Fetch last 2 daily candles (current + previous for 24h change)
                    candles = await fetch_macro_asset(
                        symbol=asset_info["symbol"],
                        interval="1day",
                        limit=2
                    )
                    
                    if len(candles) < 2:
                        # If only 1 candle, use it but show 0% change
                        logger.warning(f"Only 1 candle for {asset_key}, assuming 0% change")
                        current_price = candles[-1]["close"]
                        previous_price = current_price
                    else:
                        current_price = candles[-1]["close"]
                        previous_price = candles[-2]["close"]
                    
                    # Calculate 24h change
                    if previous_price > 0:
                        change_24h = ((current_price - previous_price) / previous_price) * 100
                    else:
                        change_24h = 0.0
                    
                    asset_data[asset_key] = {
                        "price": current_price,
                        "change_24h": change_24h,
                        "previous_price": previous_price,
                        "name": asset_info["name"]
                    }
                    
                    logger.info(f"Fetched {asset_key}: ${current_price:,.2f} ({change_24h:+.1f}%)")
                    
                except MacroDataError as e:
                    logger.error(f"Failed to fetch {asset_key}: {str(e)}")
                    raise MacroError(f"Failed to fetch {asset_key} data: {str(e)}")
                except Exception as e:
                    logger.error(f"Unexpected error for {asset_key}: {str(e)}")
                    raise MacroError(f"Failed to fetch {asset_key} data")
            
            # Calculate key ratios
            ratios = self._calculate_ratios(asset_data)
            
            # Determine market sentiment
            sentiment = self._determine_sentiment(asset_data)
            
            # Build response
            result = {
                "assets": asset_data,
                "ratios": ratios,
                "sentiment": sentiment,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            }
            
            logger.info("Macro snapshot complete")
            return result
            
        except MacroError:
            raise
        except Exception as e:
            logger.error(f"Macro snapshot error: {str(e)}", exc_info=True)
            raise MacroError(f"Failed to generate macro snapshot: {str(e)}")
    
    def _calculate_ratios(self, asset_data: dict) -> dict:
        """
        Calculate key market ratios
        
        Args:
            asset_data: Dictionary of asset prices
        
        Returns:
            Dictionary of calculated ratios
        """
        
        btc_price = asset_data["BTC"]["price"]
        gold_price = asset_data["GOLD"]["price"]
        silver_price = asset_data["SILVER"]["price"]
        
        # Validate prices are positive
        if btc_price <= 0 or gold_price <= 0 or silver_price <= 0:
            logger.error("Invalid prices for ratio calculation")
            return {
                "gold_btc": 0.0,
                "silver_gold_ratio": 0.0,
                "btc_gold": 0.0,
            }
        
        return {
            "gold_btc": gold_price / btc_price,  # oz of gold per BTC
            "silver_gold_ratio": gold_price / silver_price,  # oz of gold per oz of silver
            "btc_gold": btc_price / gold_price,  # How many oz of gold = 1 BTC
        }
    
    def _determine_sentiment(self, asset_data: dict) -> dict:
        """
        Determine overall market sentiment based on asset movements
        
        Logic:
        - Risk-On: BTC up, SPX up, DXY down
        - Risk-Off: BTC down, Gold up, SPX down
        - Inflation Hedge: BTC up, Gold up (both safe havens)
        - Strong Dollar: DXY up significantly (>1%)
        - Mixed: No clear pattern
        
        Args:
            asset_data: Dictionary of asset prices with changes
        
        Returns:
            Dictionary with sentiment status and description
        """
        
        btc_up = asset_data["BTC"]["change_24h"] > 0
        gold_up = asset_data["GOLD"]["change_24h"] > 0
        spx_up = asset_data["SPX"]["change_24h"] > 0
        dxy_down = asset_data["DXY"]["change_24h"] < 0
        
        # Risk-On: Growth assets up, dollar down
        if btc_up and spx_up and dxy_down:
            return {
                "status": "🟢 Risk-On",
                "description": "Bullish environment for crypto and equities"
            }
        
        # Risk-Off: Safe havens up, growth assets down
        if not btc_up and gold_up and not spx_up:
            return {
                "status": "🔴 Risk-Off",
                "description": "Defensive positioning — capital fleeing to safety"
            }
        
        # Inflation Hedge Mode: Both BTC and Gold rising
        if btc_up and gold_up:
            return {
                "status": "⚠️ Inflation Hedge Mode",
                "description": "Uncertainty driving flows to alternative assets"
            }
        
        # Strong Dollar: DXY up significantly
        if asset_data["DXY"]["change_24h"] > 1.0:
            return {
                "status": "💵 Dollar Strength",
                "description": "Strong USD typically pressures crypto and commodities"
            }
        
        # Mixed Signals
        return {
            "status": "↔️ Mixed Signals",
            "description": "Choppy environment with no clear directional bias"
        }