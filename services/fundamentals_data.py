# services/coingecko_service.py

import aiohttp
import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# TOP 100 COIN VALIDATION
# ============================================================================

def load_top_100_coins():
    """
    Load top 100 CoinGecko coins from JSON.
    Returns:
        dict: {SYMBOL: coingecko_id}
    """
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("top100_coingecko_ids.json must be a dict")

            # Normalize symbols to uppercase
            coins = {symbol.upper(): cg_id for symbol, cg_id in data.items()}

            logger.info(f"Loaded {len(coins)} coins from top 100 list")
            return coins

    except FileNotFoundError:
        logger.error("top100_coingecko_ids.json not found")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in top100_coingecko_ids.json: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading top 100 CoinGecko coins: {e}")
        return {}

# Load top 100 coins at module level
TOP_100_COINS = load_top_100_coins()

def validate_coin_symbol(symbol: str) -> bool:
    """Check if coin is in top 100 CoinGecko list"""
    return symbol.upper() in TOP_100_COINS

def get_coingecko_id(symbol: str) -> Optional[str]:
    """Get CoinGecko ID from symbol"""
    return TOP_100_COINS.get(symbol.upper())

# ============================================================================
# COINGECKO SERVICE
# ============================================================================

class CoinGeckoService:
    """Wrapper for CoinGecko API"""
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self._session = None
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes cache
        self.top_100_coins = TOP_100_COINS
    
    async def _get_session(self):
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def is_top_100(self, symbol: str) -> bool:
        """Check if coin is in top 100"""
        return validate_coin_symbol(symbol)
    
    async def search_coin(self, query: str) -> Optional[str]:
        """
        Search for a coin by symbol or name.
        Only returns coins in top 100.
        
        Returns: CoinGecko coin ID or None
        """
        try:
            # Normalize query
            normalized_query = query.upper().strip()
            
            # First, check if it's in our top 100 list (fastest)
            if normalized_query in self.top_100_coins:
                coin_id = self.top_100_coins[normalized_query]
                logger.info(f"Found {normalized_query} in top 100: {coin_id}")
                return coin_id
            
            # If not found in top 100, search by name
            # (user might have typed full name like "bitcoin" instead of "BTC")
            query_lower = query.lower().strip()
            
            # Check if query matches any coin ID in top 100
            for symbol, coin_id in self.top_100_coins.items():
                if coin_id == query_lower:
                    logger.info(f"Found {query} by coin ID: {coin_id}")
                    return coin_id
            
            # Search via API as fallback (but still validate against top 100)
            session = await self._get_session()
            url = f"{self.BASE_URL}/search"
            params = {"query": query}
            
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    coins = data.get("coins", [])
                    
                    # Find first match that's in our top 100
                    for coin in coins:
                        coin_id = coin.get("id")
                        coin_symbol = coin.get("symbol", "").upper()
                        
                        # Check if this coin is in our top 100
                        if coin_symbol in self.top_100_coins:
                            if self.top_100_coins[coin_symbol] == coin_id:
                                logger.info(f"Found {coin_symbol} via API search: {coin_id}")
                                return coin_id
                
                elif response.status == 429:
                    logger.warning("Rate limited by CoinGecko API")
                else:
                    logger.warning(f"CoinGecko search returned status {response.status}")
            
            # Not found in top 100
            logger.info(f"Coin '{query}' not found in top 100")
            return None
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout searching for coin: {query}")
            return None
        except Exception as e:
            logger.error(f"Error searching coin '{query}': {e}")
            return None
    
    async def get_coin_data(self, coin_id: str) -> Optional[dict]:
        """
        Fetch comprehensive coin data from CoinGecko.
        
        Args:
            coin_id: CoinGecko coin ID (e.g., "bitcoin", "ethereum")
        
        Returns:
            dict with coin data or None if error
        """
        try:
            # Validate that this coin is in top 100
            is_valid = False
            for symbol, cg_id in self.top_100_coins.items():
                if cg_id == coin_id:
                    is_valid = True
                    break
            
            if not is_valid:
                logger.warning(f"Coin ID '{coin_id}' not in top 100")
                return None
            
            # Check cache
            cache_key = f"coin_data_{coin_id}"
            if cache_key in self._cache:
                cached_time, cached_data = self._cache[cache_key]
                current_time = asyncio.get_event_loop().time()
                
                if current_time - cached_time < self._cache_ttl:
                    logger.info(f"Returning cached data for {coin_id}")
                    return cached_data
            
            # Fetch from API
            session = await self._get_session()
            url = f"{self.BASE_URL}/coins/{coin_id}"
            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "false",
                "sparkline": "false"
            }
            
            async with session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract relevant data
                    market_data = data.get("market_data", {})
                    
                    coin_info = {
                        "id": data.get("id"),
                        "symbol": data.get("symbol", "").upper(),
                        "name": data.get("name"),
                        "categories": data.get("categories", []),
                        
                        # Market data
                        "current_price": market_data.get("current_price", {}).get("usd", 0),
                        "market_cap": market_data.get("market_cap", {}).get("usd", 0),
                        "market_cap_rank": market_data.get("market_cap_rank", 0),
                        "fully_diluted_valuation": market_data.get("fully_diluted_valuation", {}).get("usd", 0),
                        "total_volume": market_data.get("total_volume", {}).get("usd", 0),
                        
                        # Supply
                        "circulating_supply": market_data.get("circulating_supply", 0) or 0,
                        "total_supply": market_data.get("total_supply", 0) or 0,
                        "max_supply": market_data.get("max_supply", 0) or 0,
                        
                        # Price history
                        "ath": market_data.get("ath", {}).get("usd", 0),
                        "ath_change_percentage": market_data.get("ath_change_percentage", {}).get("usd", 0),
                        "ath_date": market_data.get("ath_date", {}).get("usd", "N/A"),
                        "atl": market_data.get("atl", {}).get("usd", 0),
                        "atl_change_percentage": market_data.get("atl_change_percentage", {}).get("usd", 0),
                        "atl_date": market_data.get("atl_date", {}).get("usd", "N/A"),
                        
                        # Price changes
                        "price_change_24h": market_data.get("price_change_24h", 0),
                        "price_change_percentage_24h": market_data.get("price_change_percentage_24h", 0),
                        "price_change_percentage_7d": market_data.get("price_change_percentage_7d", 0),
                        "price_change_percentage_30d": market_data.get("price_change_percentage_30d", 0),
                        
                        # Community
                        "community_data": data.get("community_data", {}),
                        
                        # Links
                        "homepage": data.get("links", {}).get("homepage", []),
                        "blockchain_site": data.get("links", {}).get("blockchain_site", []),
                    }
                    
                    # Cache result
                    current_time = asyncio.get_event_loop().time()
                    self._cache[cache_key] = (current_time, coin_info)
                    
                    logger.info(f"Successfully fetched data for {coin_id}")
                    return coin_info
                
                elif response.status == 429:
                    logger.error("Rate limited by CoinGecko")
                    return None
                elif response.status == 404:
                    logger.error(f"Coin not found: {coin_id}")
                    return None
                else:
                    logger.error(f"Error fetching coin data: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching data for {coin_id}")
            return None
        except Exception as e:
            logger.error(f"Error in get_coin_data for {coin_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_coin_data_by_symbol(self, symbol: str) -> Optional[dict]:
        """
        Fetch coin data by symbol (e.g., "BTC", "ETH").
        Convenience method that looks up coin ID first.
        
        Args:
            symbol: Coin symbol (e.g., "BTC")
        
        Returns:
            dict with coin data or None
        """
        coin_id = await self.search_coin(symbol)
        if not coin_id:
            return None
        
        return await self.get_coin_data(coin_id)
    
    async def get_top_coins(self, limit: int = 100) -> list:
        """
        Fetch top coins by market cap.
        
        Args:
            limit: Number of coins to fetch (max 250)
        
        Returns:
            list of coin data dicts
        """
        try:
            # Check cache
            cache_key = f"top_coins_{limit}"
            if cache_key in self._cache:
                cached_time, cached_data = self._cache[cache_key]
                current_time = asyncio.get_event_loop().time()
                
                if current_time - cached_time < self._cache_ttl:
                    return cached_data
            
            session = await self._get_session()
            url = f"{self.BASE_URL}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": min(limit, 250),  # API max is 250
                "page": 1,
                "sparkline": "false"
            }
            
            async with session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Cache result
                    current_time = asyncio.get_event_loop().time()
                    self._cache[cache_key] = (current_time, data)
                    
                    logger.info(f"Fetched {len(data)} top coins")
                    return data
                else:
                    logger.error(f"Error fetching top coins: {response.status}")
                    return []
            
        except asyncio.TimeoutError:
            logger.error("Timeout fetching top coins")
            return []
        except Exception as e:
            logger.error(f"Error fetching top coins: {e}")
            return []
    
    def get_supported_coins(self) -> dict:
        """
        Get all supported coins (top 100).
        
        Returns:
            dict: {SYMBOL: coingecko_id}
        """
        return self.top_100_coins.copy()
    
    def get_coin_id_by_symbol(self, symbol: str) -> Optional[str]:
        """
        Get CoinGecko ID from symbol without API call.
        
        Args:
            symbol: Coin symbol (e.g., "BTC")
        
        Returns:
            CoinGecko ID or None
        """
        return get_coingecko_id(symbol)