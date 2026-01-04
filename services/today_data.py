import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MarketDataService:
    """Fetches and processes BTC market data"""

    def __init__(self, api_key: Optional[str] = None):
        # Load API key from .env if not provided
        self.api_key = api_key or os.getenv("COINGECKO_API_KEY")
        self.cache = {}
        self.cache_duration = 1800  # 30 minutes in seconds
        
        # CoinGecko API endpoints
        if self.api_key:
            # Demo/Pro API endpoint
            self.base_url = "https://api.coingecko.com/api/v3"
            self.headers = {
                "x-cg-demo-api-key": self.api_key,
                "accept": "application/json"
            }
        else:
            # Free public API endpoint (no key required)
            self.base_url = "https://api.coingecko.com/api/v3"
            self.headers = {"accept": "application/json"}
            print("Warning: No CoinGecko API key found. Using public endpoint (rate limited).")
    
    def get_btc_data(self) -> Optional[Dict]:
        """
        Get comprehensive BTC market data with caching
        Returns dict with price, MAs, volatility, etc.
        """
        cache_key = "btc_market_data"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            # Fetch current price and 24h data
            current_data = self._fetch_coingecko_current()
            
            # Fetch market chart data for MA calculation
            # Use 90 days to get enough data for 200-period MA on daily candles
            market_data = self._fetch_coingecko_market_chart(days=90)
            
            # Convert to candle format
            candles = self._convert_to_candles(market_data)
            
            # Calculate indicators
            current_price = current_data['market_data']['current_price']['usd']
            ma_50 = self._calculate_ma(candles, period=50)
            ma_200 = self._calculate_ma(candles, period=200) if len(candles) >= 200 else self._calculate_ma(candles, period=len(candles))
            
            # Calculate volatility (24h range)
            high_24h = current_data['market_data']['high_24h']['usd']
            low_24h = current_data['market_data']['low_24h']['usd']
            volatility_pct = ((high_24h - low_24h) / current_price) * 100
            
            # Price change 24h
            change_24h = current_data['market_data']['price_change_percentage_24h']
            
            # Determine regime
            regime = self._determine_regime(candles, current_price, ma_200)
            
            # Determine volatility level
            volatility_level = self._classify_volatility(volatility_pct)
            
            data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "price": current_price,
                "ma_50": round(ma_50, 2),
                "ma_200": round(ma_200, 2),
                "change_24h": round(change_24h, 2),
                "volatility_pct": round(volatility_pct, 2),
                "volatility_level": volatility_level,
                "regime": regime,
                "high_24h": high_24h,
                "low_24h": low_24h
            }
            
            # Cache result
            self.cache[cache_key] = (data, time.time())
            return data
            
        except Exception as e:
            print(f"Error fetching market data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _fetch_coingecko_current(self) -> Dict:
        """Fetch current BTC data from CoinGecko"""
        url = f"{self.base_url}/coins/bitcoin"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false"
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _fetch_coingecko_market_chart(self, days: int = 90) -> Dict:
        """
        Fetch market chart data from CoinGecko
        This gives us price data points that we can use to calculate MAs
        """
        url = f"{self.base_url}/coins/bitcoin/market_chart"
        params = {
            "vs_currency": "usd",
            "days": days,  # 1, 7, 14, 30, 90, 180, 365, or max
            "interval": "daily"  # Get daily data points
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _convert_to_candles(self, market_data: Dict) -> list:
        """
        Convert CoinGecko market chart data to candle format
        Market chart gives us prices array: [[timestamp, price], ...]
        We'll create pseudo-candles where OHLC are based on the price
        """
        if not market_data or 'prices' not in market_data:
            return []
        
        prices = market_data['prices']
        candles = []
        
        for i, price_point in enumerate(prices):
            timestamp, price = price_point
            
            # Create a pseudo-candle (open=close=high=low=price for daily data)
            # This is acceptable for MA calculations
            candle = [
                timestamp,  # timestamp
                price,      # open
                price,      # high (we'll use the price itself)
                price,      # low (we'll use the price itself)
                price,      # close
                0           # volume (not used)
            ]
            candles.append(candle)
        
        return candles
    
    def _calculate_ma(self, candles: list, period: int) -> float:
        """Calculate simple moving average from candles"""
        if len(candles) < period:
            # If we don't have enough data, use what we have
            period = len(candles)
        
        if period == 0:
            return 0.0
        
        closes = [float(candle[4]) for candle in candles[-period:]]
        return sum(closes) / len(closes)
    
    def _determine_regime(self, candles: list, current_price: float, ma_200: float) -> str:
        """
        Determine market regime: Bullish, Bearish, or Neutral
        """
        if len(candles) < 5:
            return "Neutral"
        
        # Get last 5 candles for trend detection
        recent_closes = [float(candle[4]) for candle in candles[-5:]]
        
        # Check if price is making higher highs
        higher_highs = all(recent_closes[i] >= recent_closes[i-1] for i in range(1, len(recent_closes)))
        lower_highs = all(recent_closes[i] <= recent_closes[i-1] for i in range(1, len(recent_closes)))
        
        # Distance from 200 MA
        if ma_200 == 0:
            return "Neutral"
        
        distance_from_ma = ((current_price - ma_200) / ma_200) * 100
        
        if current_price > ma_200 and higher_highs:
            return "Bullish"
        elif current_price < ma_200 and lower_highs:
            return "Bearish"
        elif abs(distance_from_ma) <= 2.5:  # Within 2.5% of 200MA
            return "Neutral"
        else:
            return "Neutral"
    
    def _classify_volatility(self, volatility_pct: float) -> str:
        """Classify volatility as Low, Medium, or High"""
        if volatility_pct < 3:
            return "Low"
        elif volatility_pct <= 6:
            return "Medium"
        else:
            return "High"