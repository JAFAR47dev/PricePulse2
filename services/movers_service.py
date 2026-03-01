import os
import aiohttp
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

class MoversService:
    """Service for fetching top movers from CoinGecko"""
    
    def __init__(self):
        self.api_key = os.getenv("COINGECKO_API_KEY")
        self.base_url = "https://api.coingecko.com/api/v3"
        self._session = None
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes cache
    
    async def _get_session(self):
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_top_movers(self, timeframe: str = "1h", limit: int = 100) -> Optional[Dict]:
        """
        Fetch top movers (pumps and dumps) from CoinGecko
        
        Args:
            timeframe: "1h" or "24h"
            limit: Number of coins to scan (default 100)
        
        Returns:
            dict with pumping/dumping coins and market summary
        """
        try:
            # Check cache
            cache_key = f"movers_{timeframe}_{limit}"
            if cache_key in self._cache:
                cached_time, cached_data = self._cache[cache_key]
                if asyncio.get_event_loop().time() - cached_time < self._cache_ttl:
                    logger.info(f"Returning cached movers data for {timeframe}")
                    return cached_data
            
            # Fetch data from CoinGecko
            session = await self._get_session()
            
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h",
                "x_cg_demo_api_key": self.api_key
            }
            
            async with session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Process data
                    movers_data = self._process_movers_data(data, timeframe)
                    
                    # Cache result
                    current_time = asyncio.get_event_loop().time()
                    self._cache[cache_key] = (current_time, movers_data)
                    
                    logger.info(f"Fetched {len(data)} coins for movers ({timeframe})")
                    return movers_data
                
                elif response.status == 429:
                    logger.error("CoinGecko rate limit hit")
                    return None
                else:
                    logger.error(f"CoinGecko API error: {response.status}")
                    return None
        
        except asyncio.TimeoutError:
            logger.error("Timeout fetching movers data")
            return None
        except Exception as e:
            logger.exception(f"Error fetching movers data")
            return None
    
    def _process_movers_data(self, coins: List[Dict], timeframe: str) -> Dict:
        """
        Process raw CoinGecko data into movers format
        
        Args:
            coins: List of coin data from CoinGecko
            timeframe: "1h" or "24h"
        
        Returns:
            dict with processed movers data
        """
        
        # Select the right price change field
        change_field = "price_change_percentage_1h_in_currency" if timeframe == "1h" else "price_change_percentage_24h_in_currency"
        
        # Filter out coins without price change data
        valid_coins = []
        for coin in coins:
            change = coin.get(change_field)
            if change is not None:
                valid_coins.append({
                    'symbol': coin['symbol'].upper(),
                    'name': coin['name'],
                    'current_price': coin['current_price'],
                    'price_change_percentage': change,
                    'market_cap': coin.get('market_cap', 0),
                    'total_volume': coin.get('total_volume', 0),
                    'volume_change': self._calculate_volume_change(coin),
                    'image': coin.get('image', '')
                })
        
        # Sort by price change
        sorted_coins = sorted(valid_coins, key=lambda x: x['price_change_percentage'], reverse=True)
        
        # Get top pumpers and dumpers
        top_pumping = [c for c in sorted_coins if c['price_change_percentage'] > 0][:5]
        top_dumping = [c for c in reversed(sorted_coins) if c['price_change_percentage'] < 0][:5]
        
        # Calculate market summary
        gainers = len([c for c in valid_coins if c['price_change_percentage'] > 0])
        losers = len([c for c in valid_coins if c['price_change_percentage'] < 0])
        neutral = len([c for c in valid_coins if c['price_change_percentage'] == 0])
        
        # Get current timestamp
        timestamp = datetime.utcnow().strftime("%H:%M UTC")
        
        return {
            'pumping': top_pumping,
            'dumping': top_dumping,
            'market_summary': {
                'gainers': gainers,
                'losers': losers,
                'neutral': neutral,
                'total': len(valid_coins)
            },
            'timestamp': timestamp
        }
    
    def _calculate_volume_change(self, coin: Dict) -> float:
        """Calculate volume change percentage"""
        try:
            volume_24h = coin.get('total_volume', 0)
            market_cap = coin.get('market_cap', 1)
            
            if market_cap > 0:
                # Volume/MCap ratio as proxy for volume change
                volume_ratio = (volume_24h / market_cap) * 100
                return volume_ratio
            
            return 0
        except:
            return 0